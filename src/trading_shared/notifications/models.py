from typing import Literal

from pydantic import BaseModel


class TradeNotification(BaseModel):
    """A structured model for a trade notification."""

    direction: str
    amount: float
    instrument_name: str
    price: float


class SystemAlert(BaseModel):
    """A structured model for a system-level alert."""

    component: str
    event: str
    details: str
    severity: Literal["INFO", "WARNING", "CRITICAL"] = "CRITICAL"
