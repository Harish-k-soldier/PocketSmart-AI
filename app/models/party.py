"""Request/response models for the Party Planner."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import PlanStatus, sanitize_text

EVENT_TYPES = ("birthday", "corporate", "wedding")
VENUE_TYPES = ("indoor", "outdoor")

BUDGET_MIN = 5_000
BUDGET_MAX = 50_000_000
GUESTS_MIN = 2
GUESTS_MAX = 2000
MIN_PER_GUEST = 150

CATEGORY_LABELS = {
    "catering": "Catering",
    "decoration": "Decoration",
    "entertainment": "Entertainment",
    "stay": "Stay",
}


class PartyPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget: int
    guests: int
    event_type: str = "birthday"
    venue_type: str = "indoor"
    city: str = "any"
    duration_hours: int = 4
    guests_travelling: bool = False
    stay_guests: Optional[int] = None
    nights: Optional[int] = None
    notes: str = ""

    @field_validator("budget")
    @classmethod
    def valid_budget(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("Budget must be an integer")
        if v < BUDGET_MIN or v > BUDGET_MAX:
            raise ValueError(f"Budget must be between ₹{BUDGET_MIN:,} and ₹{BUDGET_MAX:,}")
        return v

    @field_validator("guests")
    @classmethod
    def valid_guests(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("Guest count must be an integer")
        if v < GUESTS_MIN or v > GUESTS_MAX:
            raise ValueError(f"Guest count must be between {GUESTS_MIN} and {GUESTS_MAX}")
        return v

    @field_validator("event_type")
    @classmethod
    def valid_event(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(f"Event type must be one of {EVENT_TYPES}")
        return v

    @field_validator("venue_type")
    @classmethod
    def valid_venue(cls, v: str) -> str:
        if v not in VENUE_TYPES:
            raise ValueError(f"Venue type must be one of {VENUE_TYPES}")
        return v

    @field_validator("duration_hours")
    @classmethod
    def valid_duration(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("Duration must be an integer")
        if v < 1 or v > 24:
            raise ValueError("Duration must be between 1 and 24 hours")
        return v

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str) -> str:
        return sanitize_text(v)

    @model_validator(mode="after")
    def validate_stay(self) -> "PartyPlanRequest":
        if self.guests_travelling:
            if self.stay_guests is None or self.nights is None:
                raise ValueError("stay_guests and nights are required when guests are travelling")
            if not isinstance(self.stay_guests, int) or isinstance(self.stay_guests, bool):
                raise ValueError("stay_guests must be an integer")
            if not isinstance(self.nights, int) or isinstance(self.nights, bool):
                raise ValueError("nights must be an integer")
            if self.stay_guests < 1 or self.stay_guests > self.guests:
                raise ValueError("stay_guests must be between 1 and the guest count")
            if self.nights < 1 or self.nights > 7:
                raise ValueError("nights must be between 1 and 7")
        else:
            self.stay_guests = None
            self.nights = None
        return self


class PartyOption(BaseModel):
    id: str
    name: str
    platform: str
    unit_price: int
    price_unit: str
    total_cost: int
    reason: str
    url: str
    image: str
    is_recommended: bool


class PartyAllocation(BaseModel):
    category: str
    label: str
    percent: float
    amount: int
    spent: int
    options: list[PartyOption] = Field(default_factory=list)


class PartyPlanResponse(BaseModel):
    status: str = PlanStatus.OK
    ai_used: bool
    notice: Optional[str] = None
    budget_total: int
    contingency: int
    total_spent: int
    remaining: int
    percent_used: float
    currency: str = "INR"
    per_guest_cost: int
    event_type: str
    guests: int
    allocation: list[PartyAllocation]
