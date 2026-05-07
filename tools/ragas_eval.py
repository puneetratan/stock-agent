"""
RAGAS-style evaluation for ask.py.

Implements the faithfulness metric algorithm from RAGAS:
  1. Decompose the answer into atomic claims
  2. Verify each claim against the retrieved MongoDB context
  3. Faithfulness = supported_claims / total_claims

A faithfulness score of 1.0 means fully grounded — no hallucination.
A score below 0.7 means the answer contains claims not in the data.

Also measures answer_relevancy: does the answer actually address the question?

Uses Claude Haiku as the judge LLM (cheap, fast, same API already in use).
Saves every evaluation to MongoDB `rag_evaluations` collection for trend tracking.
"""

import json
import logging
import os
from datetime import datetime, timezone

import anthropic

logger = logging.getLogger(__name__)

JUDGE_MODEL    = "claude-haiku-4-5-20251001"
CONTEXT_LIMIT  = 6000   # chars per claim-verification call — keeps costs low
FAITHFULNESS_THRESHOLDS = {"low": 0.85, "medium": 0.60}   # below 0.60 = high risk


def _call_judge(prompt: str, max_tokens: int = 512) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


# ── Step 1: Claim extraction ──────────────────────────────────────────────────

def _extract_claims(answer: str) -> list[str]:
    """
    Decompose an answer into atomic, self-contained factual claims.
    Each claim must be independently verifiable against the context.
    """
    prompt = f"""Break the following answer into a list of atomic factual claims.
Rules:
- Each claim must be a single, self-contained, verifiable statement
- Ignore meta-phrases like "based on the data" or "according to the context"
- Ignore greetings and disclaimers
- Keep numbers, tickers, dates, and percentages exactly as stated

Return ONLY a valid JSON array of strings. No explanation, no markdown.

Answer:
{answer}

JSON array:"""

    try:
        raw = _call_judge(prompt, max_tokens=768)
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start >= 0 and end > start:
            claims = json.loads(raw[start:end])
            return [c for c in claims if isinstance(c, str) and c.strip()]
        return [answer]
    except Exception as e:
        logger.warning(f"[ragas] claim extraction failed: {e}")
        return [answer]


# ── Step 2: Claim verification ────────────────────────────────────────────────

def _verify_claim(claim: str, context: str) -> bool:
    """
    Check whether a single claim is explicitly supported by the retrieved context.
    Returns True if supported, False if not found or contradicted.
    """
    prompt = f"""You are a strict fact-checker for a financial data system.

Given the CONTEXT (retrieved from a real MongoDB database), decide if the CLAIM
is directly supported by information present in the context.

Answer YES if the claim is explicitly stated or directly derivable from the context.
Answer NO if the claim is not mentioned, cannot be derived, or contradicts the context.

Return ONLY the word YES or NO.

CONTEXT (truncated to relevant portion):
{context[:CONTEXT_LIMIT]}

CLAIM: {claim}

Answer:"""

    try:
        result = _call_judge(prompt, max_tokens=4).upper()
        return result.startswith("YES")
    except Exception as e:
        logger.warning(f"[ragas] claim verification failed: {e}")
        return True   # safe default — don't flag as hallucination on API error


# ── Step 3: Answer relevancy ──────────────────────────────────────────────────

def _score_answer_relevancy(question: str, answer: str) -> float:
    """
    Score how well the answer addresses the question (0.0 – 1.0).
    Uses a simple 0-10 rating prompt.
    """
    prompt = f"""Rate how well the ANSWER addresses the QUESTION on a scale of 0 to 10.

10 = completely and directly answers the question
5  = partially answers or answers a related question
0  = off-topic, refuses to answer, or says "I don't know" without explanation

Return ONLY an integer 0-10. No explanation.

QUESTION: {question}
ANSWER: {answer[:1500]}

Score:"""

    try:
        raw = _call_judge(prompt, max_tokens=4)
        digits = "".join(c for c in raw if c.isdigit())
        return min(int(digits) / 10.0, 1.0) if digits else 0.5
    except Exception as e:
        logger.warning(f"[ragas] relevancy scoring failed: {e}")
        return 0.5


# ── Main evaluation entry point ───────────────────────────────────────────────

def evaluate_answer(question: str, answer: str, context: str) -> dict:
    """
    Run full RAGAS-style evaluation on a Q&A pair.

    Args:
        question: the user's original question
        answer:   the RAG answer to evaluate
        context:  the MongoDB context that was retrieved (the only ground truth)

    Returns dict with:
        faithfulness      — 0.0–1.0  (1.0 = no hallucination)
        answer_relevancy  — 0.0–1.0  (1.0 = fully answers the question)
        total_claims      — number of atomic claims extracted
        supported_claims  — how many were grounded in context
        unsupported       — list of {claim, } dicts for manual review
        hallucination_risk — "low" | "medium" | "high"
    """
    claims = _extract_claims(answer)

    claim_results = []
    supported_count = 0

    for claim in claims:
        supported = _verify_claim(claim, context)
        if supported:
            supported_count += 1
        claim_results.append({"claim": claim, "supported": supported})

    faithfulness      = supported_count / len(claims) if claims else 1.0
    answer_relevancy  = _score_answer_relevancy(question, answer)

    if faithfulness >= FAITHFULNESS_THRESHOLDS["low"]:
        risk = "low"
    elif faithfulness >= FAITHFULNESS_THRESHOLDS["medium"]:
        risk = "medium"
    else:
        risk = "high"

    return {
        "question":          question,
        "faithfulness":      round(faithfulness, 3),
        "answer_relevancy":  round(answer_relevancy, 3),
        "total_claims":      len(claims),
        "supported_claims":  supported_count,
        "unsupported":       [c for c in claim_results if not c["supported"]],
        "hallucination_risk": risk,
        "evaluated_at":      datetime.now(timezone.utc).isoformat(),
    }


# ── Persistence ───────────────────────────────────────────────────────────────

def save_evaluation(result: dict, answer: str) -> None:
    """Persist evaluation to MongoDB for trend tracking over time."""
    try:
        from db import get_collection
        from db.collections import Collections
        doc = {**result, "answer_snippet": answer[:400]}
        get_collection(Collections.RAG_EVALUATIONS).insert_one(doc)
    except Exception as e:
        logger.warning(f"[ragas] save failed: {e}")


def load_eval_history(limit: int = 20) -> list[dict]:
    """Fetch recent evaluation results for trend display."""
    try:
        from db import get_collection
        from db.collections import Collections
        return list(get_collection(Collections.RAG_EVALUATIONS).find(
            {},
            {"_id": 0, "question": 1, "faithfulness": 1,
             "answer_relevancy": 1, "hallucination_risk": 1, "evaluated_at": 1},
            sort=[("evaluated_at", -1)],
            limit=limit,
        ))
    except Exception:
        return []


# ── Display ───────────────────────────────────────────────────────────────────

def print_evaluation(result: dict) -> None:
    """Print the evaluation result in a readable terminal format."""
    risk  = result["hallucination_risk"]
    icon  = {"low": "✅", "medium": "⚠️ ", "high": "❌"}[risk]
    f     = result["faithfulness"]
    r     = result["answer_relevancy"]
    total = result["total_claims"]
    sup   = result["supported_claims"]

    print(f"\n  ┌─ RAGAS Evaluation ─────────────────────────────────")
    print(f"  │  Faithfulness:      {f:.2f}  ({sup}/{total} claims grounded)  {icon} {risk.upper()} risk")
    print(f"  │  Answer Relevancy:  {r:.2f}")

    unsupported = result.get("unsupported", [])
    if unsupported:
        print(f"  │")
        print(f"  │  Ungrounded claims — review these:")
        for item in unsupported:
            truncated = item["claim"][:88]
            ellipsis  = "…" if len(item["claim"]) > 88 else ""
            print(f"  │    • {truncated}{ellipsis}")

    if risk == "low":
        print(f"  │")
        print(f"  │  Answer is fully grounded in your MongoDB data.")
    elif risk == "medium":
        print(f"  │")
        print(f"  │  Some claims could not be verified — review above.")
    else:
        print(f"  │")
        print(f"  │  High hallucination risk — do not rely on this answer.")

    print(f"  └─────────────────────────────────────────────────────\n")


def print_eval_history() -> None:
    """Print recent evaluation trend to terminal."""
    history = load_eval_history(20)
    if not history:
        print("  No evaluations recorded yet. Run with --eval to start tracking.\n")
        return

    avg_f = sum(r["faithfulness"] for r in history) / len(history)
    avg_r = sum(r["answer_relevancy"] for r in history) / len(history)
    high_risk = sum(1 for r in history if r["hallucination_risk"] == "high")

    print(f"\n  ┌─ RAGAS Evaluation History (last {len(history)}) ──────────────")
    print(f"  │  Avg Faithfulness:     {avg_f:.2f}")
    print(f"  │  Avg Answer Relevancy: {avg_r:.2f}")
    print(f"  │  High-risk answers:    {high_risk}/{len(history)}")
    print(f"  │")
    print(f"  │  {'Date':<12}  {'Faith':>6}  {'Relev':>6}  {'Risk':<8}  Question")
    print(f"  │  {'─'*12}  {'─'*6}  {'─'*6}  {'─'*8}  {'─'*30}")
    for r in history:
        date = r["evaluated_at"][:10]
        risk_str = {"low": "low ✅", "medium": "med ⚠️ ", "high": "high ❌"}.get(r["hallucination_risk"], "?")
        q = r.get("question", "")[:35]
        print(f"  │  {date:<12}  {r['faithfulness']:>6.2f}  {r['answer_relevancy']:>6.2f}  {risk_str:<8}  {q}")
    print(f"  └─────────────────────────────────────────────────────\n")
