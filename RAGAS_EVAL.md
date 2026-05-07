# RAGAS Evaluation — Hallucination Detection for ask.py

## What is RAGAS?

RAGAS (Retrieval-Augmented Generation Assessment) is a framework for measuring
whether a RAG pipeline's answers are grounded in the retrieved data — or made up.

The key question it answers: **did the LLM hallucinate, or is every claim
traceable back to real data in MongoDB?**

---

## How It Works — 3 Steps Per Answer

### Step 1 — Claim Extraction
The answer is broken into atomic, self-contained factual statements.

```
Answer: "NVDA had RSI of 42, received a BUY signal with 78% confidence."

Claims extracted:
  → "NVDA RSI was 42"
  → "NVDA received a BUY signal"
  → "Confidence was 78%"
```

### Step 2 — Claim Verification
Each claim is checked individually against the MongoDB context that was
retrieved to answer the question.

```
"NVDA RSI was 42"       → found in market_data doc  ✅ supported
"NVDA received a BUY"   → found in signals doc       ✅ supported
"Confidence was 78%"    → NOT found in context       ❌ hallucinated
```

### Step 3 — Score
```
Faithfulness     = supported_claims / total_claims  = 2/3 = 0.67
Answer Relevancy = did the answer actually address the question? (0-1)
```

---

## Scores and What They Mean

### Faithfulness (hallucination check)

| Score     | Risk   | Meaning                                          |
|-----------|--------|--------------------------------------------------|
| 0.85–1.0  | LOW ✅  | Fully grounded — trust this answer               |
| 0.60–0.84 | MED ⚠️  | Some claims unverified — review flagged items    |
| 0.00–0.59 | HIGH ❌ | High hallucination risk — do not rely on this   |

### Answer Relevancy

| Score     | Meaning                                      |
|-----------|----------------------------------------------|
| 0.80–1.0  | Fully answers the question                   |
| 0.50–0.79 | Partially answers                            |
| 0.00–0.49 | Off-topic or refused to answer               |

---

## Usage

### Normal mode (no evaluation)
```bash
uv run python ask.py
```

### Eval mode — scores every answer
```bash
uv run python ask.py --eval
```

### Commands available inside eval mode
```
eval history    →  shows trend table of last 20 evaluations
clear           →  resets conversation memory
quit / exit     →  stop
```

---

## What You See in Eval Mode

After every answer, a RAGAS block prints automatically:

```
  ┌─ RAGAS Evaluation ─────────────────────────────────
  │  Faithfulness:      0.92  (11/12 claims grounded)  ✅ LOW risk
  │  Answer Relevancy:  0.90
  │
  │  Answer is fully grounded in your MongoDB data.
  └─────────────────────────────────────────────────────
```

If hallucinations are detected, the ungrounded claims are listed:

```
  ┌─ RAGAS Evaluation ─────────────────────────────────
  │  Faithfulness:      0.67  (2/3 claims grounded)  ⚠️  MEDIUM risk
  │  Answer Relevancy:  0.90
  │
  │  Ungrounded claims — review these:
  │    • Confidence was 78%
  └─────────────────────────────────────────────────────
```

### Evaluation History Table

Type `eval history` to see the trend across all past evaluations:

```
  ┌─ RAGAS Evaluation History (last 20) ──────────────
  │  Avg Faithfulness:     0.84
  │  Avg Answer Relevancy: 0.87
  │  High-risk answers:    2/20
  │
  │  Date          Faith   Relev  Risk      Question
  │  ────────────  ──────  ──────  ────────  ──────────────────────────────────
  │  2026-05-06    0.92    0.90   low ✅    What signals ran yesterday?
  │  2026-05-06    0.67    0.85   med ⚠️   What is NVDA confidence score?
  └─────────────────────────────────────────────────────
```

---

## Implementation — No External RAGAS Package Needed

The RAGAS faithfulness algorithm is implemented directly using Claude Haiku
as the judge LLM. This is identical to what the RAGAS library does internally,
without the extra dependency.

**Judge model:** `claude-haiku-4-5-20251001` (cheap, fast)

**Cost per evaluation:**
- ~1 call to extract claims
- ~1 call per claim to verify (typically 3–8 claims per answer)
- ~1 call for answer relevancy
- Total: ~5–10 Haiku calls per answer evaluated

---

## File Locations

| File                        | Purpose                                      |
|-----------------------------|----------------------------------------------|
| `tools/ragas_eval.py`       | Core evaluation logic (claims, scoring, display) |
| `ask.py`                    | RAG chat loop — pass `--eval` flag to activate |
| `db/collections.py`         | `RAG_EVALUATIONS` collection constant added  |

---

## MongoDB Collection

All evaluations are saved to `rag_evaluations` collection:

```json
{
  "question":          "What signals ran yesterday?",
  "faithfulness":      0.92,
  "answer_relevancy":  0.90,
  "total_claims":      12,
  "supported_claims":  11,
  "unsupported":       [{ "claim": "...", "supported": false }],
  "hallucination_risk": "low",
  "evaluated_at":      "2026-05-06T12:00:00Z",
  "answer_snippet":    "First 400 chars of the answer..."
}
```

Query recent evaluations directly:
```python
from db import get_collection
from db.collections import Collections

evals = list(get_collection(Collections.RAG_EVALUATIONS).find(
    {}, {"_id": 0}, sort=[("evaluated_at", -1)], limit=20
))
```

---

## Why Not the RAGAS Package?

The official `ragas` Python package:
- Defaults to OpenAI (requires config to use Claude)
- Adds heavy dependencies (`langchain`, `datasets`, etc.)
- Has frequent breaking API changes between versions

The custom implementation here:
- Uses the same algorithm as RAGAS faithfulness
- Uses Claude Haiku (already configured in the project)
- Zero extra dependencies
- Full control over scoring thresholds and display

---

## Fine-Tuning Use Case

Once you have 3+ months of verified signals, RAGAS scores help you decide
**which Q&A pairs are safe to include in fine-tuning data**:

- Only include pairs where `faithfulness >= 0.85` (low risk)
- Discard pairs where the model hallucinated (faithfulness < 0.70)
- This ensures your Llama fine-tuning dataset contains only grounded examples

```python
# Export only high-quality Q&A pairs for fine-tuning
safe_pairs = list(get_collection(Collections.RAG_EVALUATIONS).find(
    {"faithfulness": {"$gte": 0.85}},
    {"question": 1, "answer_snippet": 1, "_id": 0}
))
```
