"""Collection name constants and index bootstrap."""

from pymongo import ASCENDING, DESCENDING, IndexModel

from .client import get_db


class Collections:
    MARKET_DATA = "market_data"
    NEWS_SENTIMENT = "news_sentiment"
    FUNDAMENTALS = "fundamentals"
    GEO_MACRO = "geo_macro"
    CAUSAL_THESES = "causal_theses"
    SIGNALS = "signals"
    SCREENER_RESULTS = "screener_results"
    WORLD_THEMES = "world_themes"
    EMBEDDINGS = "embeddings"
    ACCURACY_SCORECARD = "accuracy_scorecard"
    CROSSOVER_DATA = "crossover_data"
    SENTIMENT_HISTORY = "sentiment_history"
    NARRATIVE_CYCLES = "narrative_cycles"
    GOOGLE_TRENDS = "google_trends_history"


# Every document written by agents carries these top-level fields.
COMMON_FIELDS = {
    "run_id": str,       # UUID of the daily run — lets you query "today's run"
    "created_at": str,   # ISO-8601 timestamp
    "ticker": str,       # present on all per-stock docs
}


def ensure_indexes() -> None:
    """Create indexes on first run; idempotent thereafter."""
    db = get_db()

    db[Collections.MARKET_DATA].create_indexes([
        IndexModel([("ticker", ASCENDING), ("run_id", DESCENDING)]),
    ])
    db[Collections.NEWS_SENTIMENT].create_indexes([
        IndexModel([("ticker", ASCENDING), ("run_id", DESCENDING)]),
    ])
    db[Collections.FUNDAMENTALS].create_indexes([
        IndexModel([("ticker", ASCENDING), ("run_id", DESCENDING)]),
    ])
    db[Collections.GEO_MACRO].create_indexes([
        IndexModel([("ticker", ASCENDING), ("run_id", DESCENDING)]),
    ])
    db[Collections.CAUSAL_THESES].create_indexes([
        IndexModel([("theme_id", ASCENDING), ("run_id", DESCENDING)]),
    ])
    db[Collections.SIGNALS].create_indexes([
        IndexModel([("ticker", ASCENDING), ("run_id", DESCENDING)]),
        IndexModel([("horizon", ASCENDING)]),
    ])
    db[Collections.WORLD_THEMES].create_indexes([
        IndexModel([("run_id", DESCENDING)]),
        IndexModel([("urgency", DESCENDING)]),
    ])
    db[Collections.SCREENER_RESULTS].create_indexes([
        IndexModel([("run_id", DESCENDING)]),
        IndexModel([("ticker", ASCENDING)]),
    ])
    db[Collections.ACCURACY_SCORECARD].create_indexes([
        IndexModel([("run_date", DESCENDING)]),
        IndexModel([("horizon", ASCENDING)]),
    ])
    db[Collections.CROSSOVER_DATA].create_indexes([
        IndexModel([("date", DESCENDING)]),
    ])
    db[Collections.SENTIMENT_HISTORY].create_indexes([
        IndexModel([("captured_at", DESCENDING)]),
    ])
    db[Collections.NARRATIVE_CYCLES].create_indexes([
        IndexModel([("theme", ASCENDING), ("captured_at", DESCENDING)]),
    ])
    db[Collections.GOOGLE_TRENDS].create_indexes([
        IndexModel([("keyword", ASCENDING), ("captured_at", DESCENDING)]),
    ])
