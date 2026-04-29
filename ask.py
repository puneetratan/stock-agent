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
You are a personal investment data analyst with access to the user's own stock signal history.
You are grounded in real verified data from MongoDB.

RULES (non-negotiable):
1. Never make up signals, returns, or dates.
2. If the data context does not contain the answer, say:
   "I do not have data on this yet — we need more time collecting signals."
3. Always cite specific tickers, dates, and numbers from the context provided.
4. Be concise — bullet points preferred over paragraphs.
5. When the user asks "what happened" to a ticker, cite the actual signal, date, confidence, and verified return if available.
6. Never invent analyst consensus or price targets not in the data.

CONTEXT IS YOUR ONLY SOURCE OF TRUTH.
"""

CONVERSATION_HISTORY = []
MAX_HISTORY = 10


def _get_mongo_context(question: str) -> str:
    """
    Pull relevant documents from MongoDB based on the question.
    Combines keyword search (ticker mentions) with recent data.
    """
    from db import get_collection
    from db.collections import Collections

    context_parts = []

    # Extract tickers mentioned in the question (uppercase 2-5 letter words)
    import re
    tickers_mentioned = re.findall(r'\b([A-Z]{2,5})\b', question.upper())

    signals_col = get_collection(Collections.SIGNALS)

    # Fetch signals for mentioned tickers
    if tickers_mentioned:
        for ticker in tickers_mentioned[:3]:
            signals = list(signals_col.find(
                {"ticker": ticker},
                {"_id": 0, "ticker": 1, "signal": 1, "horizon": 1, "confidence": 1,
                 "thesis": 1, "created_at": 1, "verified_30d": 1, "return_30d_pct": 1,
                 "signal_correct_30d": 1, "price_at_signal": 1},
                sort=[("created_at", -1)],
                limit=5,
            ))
            if signals:
                context_parts.append(f"SIGNALS FOR {ticker}:\n" + json.dumps(signals, indent=2, default=str))

    # Fetch recent signals regardless (last 20)
    recent = list(signals_col.find(
        {},
        {"_id": 0, "ticker": 1, "signal": 1, "horizon": 1, "confidence": 1,
         "created_at": 1, "verified_30d": 1, "return_30d_pct": 1, "signal_correct_30d": 1},
        sort=[("created_at", -1)],
        limit=20,
    ))
    if recent:
        context_parts.append("RECENT SIGNALS (latest 20):\n" + json.dumps(recent, indent=2, default=str))

    # Fetch latest accuracy scorecard
    try:
        scorecard = get_collection(Collections.ACCURACY_SCORECARD).find_one(
            {}, {"_id": 0}, sort=[("run_date", -1)]
        )
        if scorecard:
            context_parts.append("LATEST ACCURACY SCORECARD:\n" + json.dumps(scorecard, indent=2, default=str))
    except Exception:
        pass

    # Fetch latest sentiment
    try:
        sentiment = get_collection(Collections.SENTIMENT_HISTORY).find_one(
            {}, {"_id": 0, "market_emotion": 1, "fear_greed_score": 1, "summary": 1,
                 "contrarian_signal": 1, "narrative_cycles": 1, "captured_at": 1},
            sort=[("captured_at", -1)],
        )
        if sentiment:
            context_parts.append("LATEST MARKET SENTIMENT:\n" + json.dumps(sentiment, indent=2, default=str))
    except Exception:
        pass

    # If question mentions accuracy/performance/returns
    keywords_accuracy = ["accuracy", "correct", "performance", "return", "best", "worst", "horizon"]
    if any(k in question.lower() for k in keywords_accuracy):
        try:
            all_scorecards = list(get_collection(Collections.ACCURACY_SCORECARD).find(
                {}, {"_id": 0}, sort=[("run_date", -1)], limit=5
            ))
            if all_scorecards:
                context_parts.append("ACCURACY SCORECARD HISTORY:\n" + json.dumps(all_scorecards, indent=2, default=str))
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
