"""Signal dataclass — the atomic output unit for every stock pick."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    AVOID = "AVOID"


class Signal(BaseModel):
    run_id: str
    ticker: str
    signal: SignalType
    horizon: str                    # quarter | one_year | two_year | five_year | ten_year
    confidence: int = Field(ge=0, le=100)

    # Scores from individual agents (0-100 each)
    technical_score: Optional[int] = None
    sentiment_score: Optional[float] = None
    fundamental_score: Optional[int] = None
    geo_score: Optional[int] = None

    thesis: str                     # one-paragraph investment thesis
    risks: list[str] = Field(default_factory=list)
    theme_ids: list[str] = Field(default_factory=list)  # which themes drive this pick
    is_contrarian: bool = False
    created_at: str = ""

    def to_mongo(self) -> dict:
        d = self.model_dump()
        d["signal"] = self.signal.value
        return d
