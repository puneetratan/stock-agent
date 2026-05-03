"""
ask.py — RAG terminal interface to your 180-day signal data.

Conversational agent grounded in YOUR MongoDB data.
No hallucination — every answer traceable to real data.

Usage:
    uv run python ask.py
"""

import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

SYSTEM_PROMPT = """
You are a personal investment intelligence analyst with access to the user's full MongoDB database.
The database contains: signals, world themes, causal theses, screener results, narrative cycle
phases, sentiment history, market technical data, fundamentals, and geo/macro risk reports.
Each document has a run_id and timestamp — multiple runs exist across different days.

RULES (non-negotiable):
1. Never make up signals, returns, or dates.
2. If the data context does not contain the answer, say so clearly and explain what data IS available.
3. Always cite specific tickers, dates, run_ids, and numbers from the context provided.
4. Be concise — bullet points preferred over paragraphs.
5. For TREND questions: compare documents across different run_ids/dates to show how things evolved.
   Group by date/run to make the trend readable.
6. For THEME questions: use world_themes and causal_theses, not just signals.
7. For SCREENER questions: use screener_results to show which tickers were selected and why.
8. For SENTIMENT questions: use sentiment_history to show fear/greed evolution over time.
9. When asked "what happened" to a ticker: cite the actual signal, date, confidence,
   technical report, and verified return if available.
10. Never invent data not in the context.

CONTEXT IS YOUR ONLY SOURCE OF TRUTH.
"""

CONVERSATION_HISTORY = []
MAX_HISTORY = 10


def _get_mongo_context(question: str) -> str:
    """
    Pull relevant documents from MongoDB based on the question.
    Routes to different collections depending on what the user is asking about.
    """
    from db import get_collection
    from db.collections import Collections

    context_parts = []
    q = question.lower()

    import re
    tickers_mentioned = re.findall(r'\b([A-Z]{2,5})\b', question.upper())

    # ── Keyword routing ──────────────────────────────────────────────────────

    is_trend       = any(k in q for k in ["trend", "last", "days", "week", "evolv", "chang", "over time", "history", "pattern", "progress"])
    is_theme       = any(k in q for k in ["theme", "macro", "world", "geopolit", "causal", "thesis", "narrative", "hype", "cycle", "phase"])
    is_screener    = any(k in q for k in ["screen", "candidate", "pick", "select", "short list", "top stock", "watchlist"])
    is_sentiment   = any(k in q for k in ["sentiment", "fear", "greed", "emotion", "vix", "put", "call", "retail", "smart money"])
    is_accuracy    = any(k in q for k in ["accuracy", "correct", "performance", "return", "best", "worst", "horizon", "verify", "verified"])
    is_signal      = any(k in q for k in ["signal", "buy", "sell", "hold", "confidence", "conviction"]) or tickers_mentioned
    is_market      = any(k in q for k in ["rsi", "macd", "technical", "volume", "support", "resistance", "momentum"])
    is_fundamental = any(k in q for k in ["revenue", "margin", "earnings", "pe ratio", "cash flow", "debt", "insider", "fundamental"])
    is_geo         = any(k in q for k in ["geo", "macro risk", "supply chain", "tariff", "rate", "dollar", "inflation", "sector flow"])

    # Default: treat as signal + trend query if nothing else matched
    if not any([is_trend, is_theme, is_screener, is_sentiment, is_accuracy,
                is_signal, is_market, is_fundamental, is_geo]):
        is_signal = True
        is_trend  = True

    # ── Signals ───────────────────────────────────────────────────────────────
    if is_signal or tickers_mentioned:
        signals_col = get_collection(Collections.SIGNALS)

        if tickers_mentioned:
            for ticker in tickers_mentioned[:3]:
                rows = list(signals_col.find(
                    {"ticker": ticker},
                    {"_id": 0},
                    sort=[("created_at", -1)],
                    limit=10,
                ))
                if rows:
                    context_parts.append(f"SIGNALS FOR {ticker}:\n" + json.dumps(rows, indent=2, default=str))

        recent = list(signals_col.find(
            {},
            {"_id": 0, "ticker": 1, "signal": 1, "horizon": 1, "confidence": 1,
             "created_at": 1, "verified_30d": 1, "return_30d_pct": 1,
             "signal_correct_30d": 1, "run_id": 1},
            sort=[("created_at", -1)],
            limit=30,
        ))
        if recent:
            context_parts.append("RECENT SIGNALS (latest 30, all runs):\n" + json.dumps(recent, indent=2, default=str))

    # ── Trend: pull data across multiple runs ─────────────────────────────────
    if is_trend:
        # World themes across runs — shows how the macro picture evolved
        try:
            themes = list(get_collection(Collections.WORLD_THEMES).find(
                {},
                {"_id": 0, "id": 1, "name": 1, "urgency": 1, "status": 1,
                 "detected_at": 1, "run_id": 1},
                sort=[("detected_at", -1)],
                limit=40,
            ))
            if themes:
                context_parts.append("WORLD THEMES (last 40 across runs — shows macro evolution):\n" + json.dumps(themes, indent=2, default=str))
        except Exception:
            pass

        # Screener results across runs — which tickers were selected each day
        try:
            screened = list(get_collection(Collections.SCREENER_RESULTS).find(
                {},
                {"_id": 0, "ticker": 1, "sector": 1, "theme_alignment": 1,
                 "alignment_score": 1, "run_id": 1, "screened_at": 1},
                sort=[("screened_at", -1)],
                limit=60,
            ))
            if screened:
                context_parts.append("SCREENER RESULTS (last 60 across runs — which tickers appeared):\n" + json.dumps(screened, indent=2, default=str))
        except Exception:
            pass

        # Narrative cycle phases across runs
        try:
            cycles = list(get_collection(Collections.NARRATIVE_CYCLES).find(
                {},
                {"_id": 0, "theme": 1, "current_phase": 1, "action": 1, "captured_at": 1, "run_id": 1},
                sort=[("captured_at", -1)],
                limit=30,
            ))
            if cycles:
                context_parts.append("NARRATIVE CYCLE HISTORY (phase changes over time):\n" + json.dumps(cycles, indent=2, default=str))
        except Exception:
            pass

        # Sentiment history across runs
        try:
            sent_history = list(get_collection(Collections.SENTIMENT_HISTORY).find(
                {},
                {"_id": 0, "market_emotion": 1, "fear_greed_score": 1,
                 "summary": 1, "captured_at": 1},
                sort=[("captured_at", -1)],
                limit=10,
            ))
            if sent_history:
                context_parts.append("SENTIMENT HISTORY (fear/greed trend):\n" + json.dumps(sent_history, indent=2, default=str))
        except Exception:
            pass

    # ── Themes / Causal analysis ──────────────────────────────────────────────
    if is_theme:
        try:
            themes = list(get_collection(Collections.WORLD_THEMES).find(
                {},
                {"_id": 0, "id": 1, "name": 1, "urgency": 1, "status": 1,
                 "summary": 1, "evidence": 1, "detected_at": 1, "run_id": 1},
                sort=[("detected_at", -1)],
                limit=20,
            ))
            if themes:
                context_parts.append("ACTIVE WORLD THEMES:\n" + json.dumps(themes, indent=2, default=str))
        except Exception:
            pass

        try:
            theses = list(get_collection(Collections.CAUSAL_THESES).find(
                {},
                {"_id": 0, "theme_id": 1, "root_cause": 1, "contrarian_take": 1,
                 "historical_parallel": 1, "risk_flags": 1, "confidence": 1,
                 "analysed_at": 1, "run_id": 1},
                sort=[("analysed_at", -1)],
                limit=10,
            ))
            if theses:
                context_parts.append("CAUSAL THESES (root cause analysis):\n" + json.dumps(theses, indent=2, default=str))
        except Exception:
            pass

    # ── Screener picks ────────────────────────────────────────────────────────
    if is_screener:
        try:
            screened = list(get_collection(Collections.SCREENER_RESULTS).find(
                {},
                {"_id": 0},
                sort=[("screened_at", -1)],
                limit=30,
            ))
            if screened:
                context_parts.append("SCREENER RESULTS (latest candidates):\n" + json.dumps(screened, indent=2, default=str))
        except Exception:
            pass

    # ── Sentiment ─────────────────────────────────────────────────────────────
    if is_sentiment:
        try:
            sentiment = get_collection(Collections.SENTIMENT_HISTORY).find_one(
                {}, {"_id": 0},
                sort=[("captured_at", -1)],
            )
            if sentiment:
                context_parts.append("LATEST MARKET SENTIMENT:\n" + json.dumps(sentiment, indent=2, default=str))
        except Exception:
            pass

    # ── Accuracy / performance ────────────────────────────────────────────────
    if is_accuracy:
        try:
            scorecards = list(get_collection(Collections.ACCURACY_SCORECARD).find(
                {}, {"_id": 0}, sort=[("run_date", -1)], limit=10
            ))
            if scorecards:
                context_parts.append("ACCURACY SCORECARD HISTORY:\n" + json.dumps(scorecards, indent=2, default=str))
        except Exception:
            pass

    # ── Market technical reports ──────────────────────────────────────────────
    if is_market and tickers_mentioned:
        try:
            for ticker in tickers_mentioned[:3]:
                rows = list(get_collection(Collections.MARKET_DATA).find(
                    {"ticker": ticker},
                    {"_id": 0},
                    sort=[("generated_at", -1)],
                    limit=5,
                ))
                if rows:
                    context_parts.append(f"MARKET TECHNICAL DATA FOR {ticker}:\n" + json.dumps(rows, indent=2, default=str))
        except Exception:
            pass

    # ── Fundamentals ──────────────────────────────────────────────────────────
    if is_fundamental and tickers_mentioned:
        try:
            for ticker in tickers_mentioned[:3]:
                rows = list(get_collection(Collections.FUNDAMENTALS).find(
                    {"ticker": ticker},
                    {"_id": 0},
                    sort=[("generated_at", -1)],
                    limit=3,
                ))
                if rows:
                    context_parts.append(f"FUNDAMENTALS FOR {ticker}:\n" + json.dumps(rows, indent=2, default=str))
        except Exception:
            pass

    # ── Geo/macro risk ────────────────────────────────────────────────────────
    if is_geo and tickers_mentioned:
        try:
            for ticker in tickers_mentioned[:3]:
                rows = list(get_collection(Collections.GEO_MACRO).find(
                    {"ticker": ticker},
                    {"_id": 0},
                    sort=[("generated_at", -1)],
                    limit=3,
                ))
                if rows:
                    context_parts.append(f"GEO/MACRO RISK FOR {ticker}:\n" + json.dumps(rows, indent=2, default=str))
        except Exception:
            pass

    # ── Always append latest accuracy scorecard as baseline ──────────────────
    if not is_accuracy:
        try:
            scorecard = get_collection(Collections.ACCURACY_SCORECARD).find_one(
                {}, {"_id": 0}, sort=[("run_date", -1)]
            )
            if scorecard:
                context_parts.append("LATEST ACCURACY SCORECARD:\n" + json.dumps(scorecard, indent=2, default=str))
        except Exception:
            pass

    return "\n\n---\n\n".join(context_parts) if context_parts else "No data found in MongoDB yet."


def _call_claude(question: str, context: str) -> str:
    """Call Claude via Anthropic API (same as all other agents)."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        messages = []
        for turn in CONVERSATION_HISTORY[-MAX_HISTORY:]:
            messages.append({"role": "user", "content": turn["user"]})
            messages.append({"role": "assistant", "content": turn["assistant"]})

        user_message = f"""CONTEXT FROM YOUR MONGODB DATA:
{context}

---

QUESTION: {question}

Answer based ONLY on the context above. If the data doesn't contain the answer, say so clearly."""

        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return response.content[0].text

    except Exception as e:
        return f"Error calling Claude: {e}\n\nCheck AWS credentials and BEDROCK_MODEL_ID in .env"


def chat():
    """Interactive RAG chat loop."""
    print("\n" + "=" * 55)
    print("  📊 Stock Intelligence — Ask Your Data")
    print("=" * 55)
    print("  Type a question about your signal history.")
    print("  Type 'quit' or 'exit' to stop.")
    print("  Type 'clear' to reset conversation memory.")
    print("=" * 55 + "\n")

    # Show quick data health summary
    try:
        from db import get_collection
        from db.collections import Collections
        n_signals = get_collection(Collections.SIGNALS).count_documents({})
        n_verified = get_collection(Collections.SIGNALS).count_documents({"verified_30d": True})
        print(f"  Data: {n_signals} total signals, {n_verified} verified (30d)\n")
    except Exception:
        pass

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit"):
            print("Goodbye.")
            break
        if question.lower() == "clear":
            CONVERSATION_HISTORY.clear()
            print("  [Conversation memory cleared]\n")
            continue

        print("\n  Searching your data...", end="", flush=True)
        context = _get_mongo_context(question)
        print("\r  Thinking...          ", end="", flush=True)
        answer = _call_claude(question, context)
        print("\r" + " " * 25 + "\r", end="")

        print(f"\nAgent: {answer}\n")
        print("-" * 55 + "\n")

        CONVERSATION_HISTORY.append({"user": question, "assistant": answer})
        if len(CONVERSATION_HISTORY) > MAX_HISTORY:
            CONVERSATION_HISTORY.pop(0)


if __name__ == "__main__":
    chat()
