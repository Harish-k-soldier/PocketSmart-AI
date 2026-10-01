"""Shared models: enums, error contract, and the catalog item schema."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Platform(str, Enum):
    AMAZON = "Amazon"
    FLIPKART = "Flipkart"
    IKEA = "IKEA"
    SWIGGY = "Swiggy"
    ZOMATO = "Zomato"
    OYO = "OYO"


class Group(str, Enum):
    HOME = "home"
    PARTY = "party"
    JEWELRY = "jewelry"


class PriceUnit(str, Enum):
    PER_ITEM = "per_item"
    PER_PLATE = "per_plate"
    PER_EVENT = "per_event"
    PER_HOUR = "per_hour"
    PER_NIGHT = "per_night"
    PER_SET = "per_set"


class CatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z]+-[A-Z_]+-[0-9]{3}$")
    name: str = Field(min_length=1, max_length=200)
    platform: Platform
    category: str = Field(pattern=r"^[a-z_]+$")
    group: Group
    price_inr: int = Field(gt=0)
    price_unit: PriceUnit
    tags: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    rating: float = Field(default=4.0, ge=0, le=5)
    image: str = Field(default="/static/img/placeholder.svg")
    url: str = Field(pattern=r"^https://")

    @field_validator("tags")
    @classmethod
    def tags_lowercase_snake(cls, v: list[str]) -> list[str]:
        for t in v:
            if t != t.lower() or " " in t:
                raise ValueError(f"tag must be lowercase snake_case: {t!r}")
        return v


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: dict[str, str] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class PlanStatus(str, Enum):
    OK = "ok"
    INSUFFICIENT_BUDGET = "insufficient_budget"


def sanitize_text(value: str, max_length: int = 200) -> str:
    """Strip control characters (except newline/tab) and cap length."""
    cleaned = "".join(
        ch for ch in value
        if ch in ("\n", "\t") or (ord(ch) >= 32 and ord(ch) != 127)
    )
    return cleaned.strip()[:max_length]


class InsufficientBudgetBody(BaseModel):
    status: str = "insufficient_budget"
    ai_used: bool = False
    notice: Optional[str] = None
    budget_total: int
    minimum_required: int
    message: str
    currency: str = "INR"
