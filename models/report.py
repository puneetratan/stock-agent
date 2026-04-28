"""Final report dataclass — assembled by Ranking Agent and delivered to user."""

from typing import Optional

from pydantic import BaseModel, Field

from .signal import Signal
from .theme import Theme


class HorizonPicks(BaseModel):
    horizon: str                    # quarter | one_year | two_year | five_year | ten_year
    picks: list[Signal] = Field(default_factory=list)
    avoid: list[Signal] = Field(default_factory=list)
    contrarian_picks: list[Signal] = Field(default_factory=list)


class MarketRegime(BaseModel):
    label: str                      # e.g. "Risk-Off", "Reflationary", "Late Cycle"
    description: str
    recommended_posture: str        # e.g. "defensive tilt, hold cash 20%"


class FinalReport(BaseModel):
    run_id: str
    generated_at: str

    # Macro context
    themes: list[Theme] = Field(default_factory=list)
    causal_summary: str = ""        # one-paragraph synthesis of all root causes
    market_regime: Optional[MarketRegime] = None

    # Picks per time horizon
    horizons: list[HorizonPicks] = Field(default_factory=list)

    # Stats
    stocks_screened: int = 0
    stocks_deep_analysed: int = 0
    total_signals: int = 0

    # Free-form analyst note from Ranking Agent
    analyst_note: str = ""

    def to_mongo(self) -> dict:
        return self.model_dump()

    def horizon_by_name(self, name: str) -> Optional[HorizonPicks]:
        return next((h for h in self.horizons if h.horizon == name), None)
