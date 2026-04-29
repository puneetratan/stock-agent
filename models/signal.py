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

    # Price at signal creation — required for verification
    price_at_signal: Optional[float] = None

    # 30-day verification
    verified_30d: bool = False
    price_30d_later: Optional[float] = None
    return_30d_pct: Optional[float] = None
    signal_correct_30d: Optional[bool] = None

    # 90-day verification
    verified_90d: bool = False
    price_90d_later: Optional[float] = None
    return_90d_pct: Optional[float] = None
    signal_correct_90d: Optional[bool] = None

    # 180-day verification
    verified_180d: bool = False
    price_180d_later: Optional[float] = None
    return_180d_pct: Optional[float] = None
    signal_correct_180d: Optional[bool] = None

    def to_mongo(self) -> dict:
        d = self.model_dump()
        d["signal"] = self.signal.value
        return d
