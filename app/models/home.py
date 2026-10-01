"""Request/response models for the Home Budget Planner."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import PlanStatus, sanitize_text

HOME_STYLES = ("modern", "minimal", "traditional")

ROOM_ITEM_DEFAULTS: dict[str, dict[str, int]] = {
    "living_room": {
        "lights": 3,
        "ceiling_fans": 1,
        "sofas": 1,
        "rugs": 1,
        "curtains": 2,
        "wall_decor": 2,
    },
    "kitchen": {"lights": 2, "ceiling_fans": 1, "kitchen_storage": 2},
    "bedroom": {
        "lights": 2,
        "ceiling_fans": 1,
        "beds": 1,
        "mattresses": 1,
        "wardrobes": 1,
        "curtains": 2,
    },
    "dining_room": {"lights": 2, "ceiling_fans": 1, "dining_tables": 1, "curtains": 1},
    "kids_room": {
        "lights": 2,
        "ceiling_fans": 1,
        "beds": 1,
        "study_tables": 1,
        "wardrobes": 1,
    },
    "study_room": {"lights": 2, "ceiling_fans": 1, "study_tables": 1, "curtains": 1},
}

ROOM_LABELS = {
    "living_room": "Living Room",
    "kitchen": "Kitchen",
    "bedroom": "Bedroom",
    "dining_room": "Dining Room",
    "kids_room": "Kids Room",
    "study_room": "Study/Home Office",
}

CATEGORY_LABELS = {
    "lights": "Lights",
    "ceiling_fans": "Ceiling Fans",
    "sofas": "Sofas",
    "rugs": "Rugs",
    "curtains": "Curtains",
    "wall_decor": "Wall Decor",
    "kitchen_storage": "Kitchen Storage",
    "beds": "Beds",
    "mattresses": "Mattresses",
    "wardrobes": "Wardrobes",
    "dining_tables": "Dining Tables",
    "study_tables": "Study Tables",
}

BUDGET_MIN = 10_000
BUDGET_MAX = 100_000_000


class RoomItems(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    items: dict[str, int] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def valid_room(cls, v: str) -> str:
        if v not in ROOM_ITEM_DEFAULTS:
            raise ValueError(f"Unknown room: {v}")
        return v

    @field_validator("items")
    @classmethod
    def valid_items(cls, v: dict[str, int]) -> dict[str, int]:
        for cat, qty in v.items():
            if not isinstance(qty, int) or isinstance(qty, bool):
                raise ValueError(f"Quantity for {cat} must be an integer")
            if qty < 0 or qty > 10:
                raise ValueError(f"Quantity for {cat} must be between 0 and 10")
        return v


class HomePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget: int
    style: str = "modern"
    notes: str = ""
    rooms: list[RoomItems]

    @field_validator("budget")
    @classmethod
    def valid_budget(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("Budget must be an integer")
        if v < BUDGET_MIN or v > BUDGET_MAX:
            raise ValueError(f"Budget must be between ₹{BUDGET_MIN:,} and ₹{BUDGET_MAX:,}")
        return v

    @field_validator("style")
    @classmethod
    def valid_style(cls, v: str) -> str:
        if v not in HOME_STYLES:
            raise ValueError(f"Style must be one of {HOME_STYLES}")
        return v

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, v: str) -> str:
        return sanitize_text(v)

    @model_validator(mode="after")
    def normalize(self) -> "HomePlanRequest":
        seen: set[str] = set()
        normalized: list[RoomItems] = []
        for room in self.rooms:
            if room.name in seen:
                raise ValueError(f"Duplicate room: {room.name}")
            seen.add(room.name)
            items = {c: q for c, q in room.items.items() if q > 0}
            if items:
                normalized.append(RoomItems(name=room.name, items=items))
        if not normalized:
            raise ValueError("Add at least one item")
        self.rooms = normalized
        return self


class HomeOption(BaseModel):
    id: str
    name: str
    platform: str
    unit_price: int
    line_total: int
    image: str
    url: str
    reason: str
    is_recommended: bool


class HomeItemResult(BaseModel):
    category: str
    label: str
    quantity: int
    unit_ceiling: int
    recommended_id: Optional[str] = None
    options: list[HomeOption] = Field(default_factory=list)
    unavailable: bool = False


class HomeRoomResult(BaseModel):
    room: str
    label: str
    room_budget: int
    room_spent: int
    items: list[HomeItemResult]


class HomePlanResponse(BaseModel):
    status: str = PlanStatus.OK
    ai_used: bool
    notice: Optional[str] = None
    budget_total: int
    contingency: int
    total_spent: int
    remaining: int
    percent_used: float
    currency: str = "INR"
    rooms: list[HomeRoomResult]
