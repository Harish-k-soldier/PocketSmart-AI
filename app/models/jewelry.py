"""Request/response models for the Jewelry Budget Planner."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .common import PlanStatus, sanitize_text

OCCASIONS = ("wedding", "festival", "office", "party")
STYLES = ("traditional", "modern", "minimalist", "statement")
METALS = ("gold_plated", "silver", "rose_gold", "oxidised", "no_preference")
STONES = ("kundan", "pearl", "cz", "gemstone", "none", "no_preference")

BUDGET_MIN = 500
BUDGET_MAX = 5_000_000


class JewelryPlanRequest(BaseModel):
    budget: int
    occasion: str = "wedding"
    style: str = "traditional"
    metal: str = "no_preference"
    stone: str = "no_preference"
    notes: str = ""

    @field_validator("budget")
    @classmethod
    def valid_budget(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("Budget must be an integer")
        if v < BUDGET_MIN or v > BUDGET_MAX:
            raise ValueError(f"Budget must be between ₹{BUDGET_MIN:,} and ₹{BUDGET_MAX:,}")
        return v

    @field_validator("occasion")
    @classmethod
    def valid_occasion(cls, v: str) -> str:
        if v not in OCCASIONS:
            raise ValueError(f"Occasion must be one of {OCCASIONS}")
        return v

    @field_validator("style")
    @classmethod
    def valid_style(cls, v: str) -> str:
        if v not in STYLES:
            raise ValueError(f"Style must be one of {STYLES}")
        return v

    @field_validator("metal")
    @classmethod
    def valid_metal(cls, v: str) -> str:
        if v not in METALS:
            raise ValueError(f"Metal must be one of {METALS}")
        return v

    @field_validator("stone")
    @classmethod
    def valid_stone(cls, v: str) -> str:
        if v not in STONES:
            raise ValueError(f"Stone must be one of {STONES}")
        return v

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str) -> str:
        return sanitize_text(v)


class PaletteColor(BaseModel):
    hex: str = Field(pattern=r"^#[0-9A-F]{6}$")
    name: str = Field(max_length=60)


class JewelryRecommendation(BaseModel):
    id: str
    name: str
    platform: str
    price: int
    image: str
    url: str
    colors: list[str] = Field(default_factory=list)
    why_it_matches: str
    match_score: int = Field(ge=0, le=100)


class JewelryPlanResponse(BaseModel):
    status: str = PlanStatus.OK
    ai_used: bool
    notice: Optional[str] = None
    budget_total: int
    total_spent: int
    remaining: int
    percent_used: float
    currency: str = "INR"
    palette: list[PaletteColor] = Field(default_factory=list)
    outfit_summary: Optional[str] = None
    recommendations: list[JewelryRecommendation]
