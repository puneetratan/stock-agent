"""Theme dataclass — a macro event/narrative detected by World Intelligence Agent."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ThemeStatus(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COOLING = "cooling"
    NEW = "new"


class Theme(BaseModel):
    id: str                         # e.g. PETRODOLLAR_EROSION
    name: str
    urgency: int = Field(ge=1, le=10)
    status: ThemeStatus
    summary: str
    evidence: list[str] = Field(default_factory=list)
    detected_at: str = ""
    run_id: str = ""

    # Populated later by CausalReasoningAgent
    root_cause: Optional[str] = None
    causal_chain: list[str] = Field(default_factory=list)
    historical_parallel: Optional[dict] = None
    second_order_effects: list[str] = Field(default_factory=list)
    contrarian_take: Optional[str] = None
    confidence: Optional[int] = None

    def to_mongo(self) -> dict:
        d = self.model_dump()
        d["status"] = self.status.value
        return d
