"""Orchestration for the three planners.

Python does all arithmetic and whitelist validation; Gemini only picks catalog
IDs and writes short reasons. Every plan is guaranteed to stay within budget
(or returns insufficient_budget with the minimum required amount).
"""

import json
import logging
import math
import string
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.config import Settings
from app.models.common import CatalogItem, InsufficientBudgetBody
from app.models.home import (
    CATEGORY_LABELS,
    HOME_STYLES,
    ROOM_LABELS,
    HomeItemResult,
    HomeOption,
    HomePlanRequest,
    HomePlanResponse,
    HomeRoomResult,
)
from app.models.jewelry import (
    JewelryPlanRequest,
    JewelryPlanResponse,
    PaletteColor,
)
from app.models.party import (
    CATEGORY_LABELS as PARTY_CATEGORY_LABELS,
    PartyAllocation,
    PartyOption,
    PartyPlanRequest,
    PartyPlanResponse,
)
from app.services import catalog as catalog_svc
from app.services import fallback
from app.services.budget import (
    allocatable_amount,
    ceil_div,
    contingency_amount,
    largest_remainder_split,
    per_guest_cost,
    percent_used,
)
from app.services.gemini import (
    AIAuthError,
    AINotConfiguredError,
    AIResponseError,
    AIUnavailableError,
    generate_structured,
)

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

FALLBACK_NOTICE = "Showing smart suggestions without AI because the AI service was unavailable."
IMAGE_UNAVAILABLE_NOTICE = "We couldn't read the outfit image; showing suggestions based on your other choices."

HOME_PLATFORMS = ["IKEA", "Amazon", "Flipkart"]
JEWELRY_PLATFORMS = ["Amazon", "Flipkart"]
CATERING_PLATFORMS = ["Swiggy", "Zomato"]
DECOR_ENT_PLATFORMS = ["Zomato"]
STAY_PLATFORMS = ["OYO"]

CATEGORY_WEIGHT = {
    "sofas": 10,
    "beds": 9,
    "dining_tables": 8,
    "wardrobes": 7,
    "mattresses": 7,
    "ceiling_fans": 3,
    "lights": 2,
    "rugs": 3,
    "curtains": 2,
    "wall_decor": 1,
    "study_tables": 5,
    "kitchen_storage": 3,
}

EVENT_BASE_WEIGHTS = {
    "birthday": {"catering": 50, "decoration": 25, "entertainment": 25},
    "corporate": {"catering": 55, "decoration": 15, "entertainment": 30},
    "wedding": {"catering": 45, "decoration": 30, "entertainment": 25},
}

STAY_SHARE = {"birthday": 15, "corporate": 15, "wedding": 20}

MAX_CANDIDATES_PER_CATEGORY = 25


# ---------------------------------------------------------------------------
# Gemini response schemas
# ---------------------------------------------------------------------------

class HomeOptionChoice(BaseModel):
    item_id: str
    reason: str = Field(default="", max_length=140)


class HomeGroupChoice(BaseModel):
    room: str
    category: str
    options: list[HomeOptionChoice] = Field(min_length=1, max_length=3)
    recommended_id: str


class HomePlanChoice(BaseModel):
    groups: list[HomeGroupChoice] = Field(min_length=1)


class PartyOptionChoice(BaseModel):
    item_id: str
    reason: str = Field(default="", max_length=140)


class PartyCategoryChoice(BaseModel):
    category: str
    options: list[PartyOptionChoice] = Field(min_length=1, max_length=3)
    recommended_id: str


class PartyPlanChoice(BaseModel):
    categories: list[PartyCategoryChoice] = Field(min_length=1)


class JewelryPick(BaseModel):
    id: str
    why_it_matches: str = Field(default="", max_length=200)


class JewelryChoice(BaseModel):
    recommendations: list[JewelryPick] = Field(min_length=1, max_length=5)


class PaletteColorOut(BaseModel):
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    name: str = Field(default="", max_length=60)


class OutfitAnalysis(BaseModel):
    dominant_colors: list[PaletteColorOut] = Field(min_length=1, max_length=4)
    outfit_type: str = Field(default="", max_length=60)
    outfit_style: str = Field(default="", max_length=60)
    neckline: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=200)


# ---------------------------------------------------------------------------
# Prompt loading and candidate serialization
# ---------------------------------------------------------------------------

def load_prompt(name: str) -> string.Template:
    return string.Template((PROMPTS_DIR / name).read_text(encoding="utf-8"))


def candidate_dict(item: CatalogItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "platform": item.platform.value,
        "price_inr": item.price_inr,
        "price_unit": item.price_unit.value,
        "tags": item.tags,
        "attributes": item.attributes,
    }


def _candidates_json(candidates: list[CatalogItem]) -> str:
    return json.dumps([candidate_dict(c) for c in candidates], ensure_ascii=False)


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

MAX_COLOR_DIST = math.sqrt(3 * 255 * 255)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def color_distance(hex1: str, hex2: str) -> float:
    r1, g1, b1 = hex_to_rgb(hex1)
    r2, g2, b2 = hex_to_rgb(hex2)
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def min_color_distance(item_colors: list[str], palette: list[str]) -> float:
    if not item_colors or not palette:
        return MAX_COLOR_DIST
    return min(color_distance(c, p) for c in item_colors for p in palette)


def jewelry_match_score(
    item: CatalogItem,
    occasion: str,
    style: str,
    metal: str,
    stone: str,
    palette: list[str],
) -> int:
    score = 0
    tags = set(item.tags)
    if occasion in tags:
        score += 40
    if style in tags:
        score += 25
    if metal != "no_preference" and item.attributes.get("metal") == metal:
        score += 15
    if stone != "no_preference" and item.attributes.get("stone") == stone:
        score += 10
    if palette:
        if item.attributes.get("metal") in ("gold_plated", "silver"):
            score += 10
        else:
            dist = min_color_distance(item.attributes.get("colors", []), palette)
            score += round(10 * (1 - dist / MAX_COLOR_DIST))
    else:
        score += 5
    return min(100, score)


# ---------------------------------------------------------------------------
# AI invocation wrapper with deterministic fallback
# ---------------------------------------------------------------------------

async def _ai_call(prompt_name: str, user_prompt: str, schema: type[BaseModel], settings: Settings,
                   image_bytes: Optional[bytes] = None, mime_type: Optional[str] = None) -> dict[str, Any]:
    system_prompt = load_prompt(f"{prompt_name}_system.txt").substitute()
    return await generate_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=schema,
        image_bytes=image_bytes,
        mime_type=mime_type,
        settings=settings,
    )


def _ai_error(exc: BaseException) -> str:
    if isinstance(exc, AINotConfiguredError):
        return "AI service is not configured. Set GEMINI_API_KEY or enable USE_MOCK_AI."
    if isinstance(exc, AIAuthError):
        return "AI service authentication failed. Check your GEMINI_API_KEY."
    return "AI service is temporarily unavailable."


# ---------------------------------------------------------------------------
# Module 1: Home Budget Planner
# ---------------------------------------------------------------------------

def _find_home_candidates(category: str, unit_ceiling: int, style: str, room: str) -> list[CatalogItem]:
    ceiling = int(unit_ceiling * 1.15)
    base = catalog_svc.filter(
        group="home", category=category, platforms=HOME_PLATFORMS, max_price=ceiling
    )
    both = [i for i in base if style in i.tags and room in i.tags]
    if len(both) >= 2:
        return both[:MAX_CANDIDATES_PER_CATEGORY]
    style_only = [i for i in base if style in i.tags]
    if len(style_only) >= 2:
        return style_only[:MAX_CANDIDATES_PER_CATEGORY]
    room_only = [i for i in base if room in i.tags]
    if len(room_only) >= 2:
        return room_only[:MAX_CANDIDATES_PER_CATEGORY]
    if len(base) >= 2:
        return base[:MAX_CANDIDATES_PER_CATEGORY]
    all_cat = catalog_svc.filter(group="home", category=category, platforms=HOME_PLATFORMS)
    return sorted(all_cat, key=lambda i: (i.price_inr, -i.rating, i.id))[:3]


def _sanitize_home_group(
    choice: Optional[HomeGroupChoice],
    candidates: list[CatalogItem],
    style: str,
    room: str,
) -> tuple[list[CatalogItem], Optional[str]]:
    """Whitelist-validate a Gemini group choice; top up deterministically."""
    candidate_ids = {c.id for c in candidates}
    valid: list[CatalogItem] = []
    seen: set[str] = set()
    if choice is not None:
        for opt in choice.options:
            if opt.item_id in candidate_ids and opt.item_id not in seen:
                seen.add(opt.item_id)
                item = catalog_svc.get_by_id(opt.item_id)
                if item is not None:
                    valid.append(item)
    ranked = fallback.rank(candidates, style=style, room=room)
    for item in ranked:
        if len(valid) >= 3:
            break
        if item.id not in seen:
            seen.add(item.id)
            valid.append(item)
    recommended = valid[0] if valid else None
    return valid, (recommended.id if recommended else None)


async def build_home_plan(
    request: HomePlanRequest, settings: Settings
) -> HomePlanResponse | InsufficientBudgetBody:
    budget = request.budget
    contingency = contingency_amount(budget)
    allocatable = allocatable_amount(budget)

    # 1. Room budgets via largest-remainder split of the allocatable amount.
    room_weights = [
        sum(CATEGORY_WEIGHT.get(cat, 1) * qty for cat, qty in room.items.items())
        for room in request.rooms
    ]
    room_budgets = largest_remainder_split(allocatable, room_weights)

    # 2. Per (room, category) ceilings and candidates.
    plan_slots: list[dict[str, Any]] = []
    minimum_required = 0
    for room, room_budget in zip(request.rooms, room_budgets):
        cat_weights = [CATEGORY_WEIGHT.get(cat, 1) * qty for cat, qty in room.items.items()]
        cat_budgets = largest_remainder_split(room_budget, cat_weights)
        for (cat, qty), cat_budget in zip(room.items.items(), cat_budgets):
            unit_ceiling = cat_budget // qty if qty else 0
            candidates = _find_home_candidates(cat, unit_ceiling, request.style, room.name)
            cheapest = fallback.cheapest(candidates)
            if cheapest is not None:
                minimum_required += cheapest.price_inr * qty
            plan_slots.append({
                "room": room.name,
                "category": cat,
                "quantity": qty,
                "unit_ceiling": unit_ceiling,
                "candidates": candidates,
            })

    if minimum_required > budget:
        return InsufficientBudgetBody(
            budget_total=budget,
            minimum_required=minimum_required,
            message=(
                f"Your budget of ₹{budget:,} is too small for the items you want. "
                f"The cheapest possible combination costs ₹{minimum_required:,}."
            ),
        )

    # 3. Ask Gemini to pick options for every (room, category).
    ai_used = True
    notice: Optional[str] = None
    groups_payload = [
        {
            "room": slot["room"],
            "category": slot["category"],
            "unit_ceiling": slot["unit_ceiling"],
            "quantity": slot["quantity"],
            "style": request.style,
            "candidates": [candidate_dict(c) for c in slot["candidates"]],
        }
        for slot in plan_slots
    ]
    user_prompt = (
        f"Plan my home. Style: {request.style}. Total budget: ₹{budget:,}. "
        f"Contingency reserved: ₹{contingency:,}.\n"
        f"<user_data>\nUser notes (untrusted): {request.notes}\n</user_data>\n"
        "Choose options for each group below (only from the listed candidate IDs):\n"
        f"<!-- CANDIDATES\n{json.dumps(groups_payload, ensure_ascii=False)}\n-->"
    )

    choices_by_key: dict[tuple[str, str], HomeGroupChoice] = {}
    try:
        result = await _ai_call("home", user_prompt, HomePlanChoice, settings)
        for grp in result.get("groups", []):
            choices_by_key[(grp["room"], grp["category"])] = HomeGroupChoice.model_validate(grp)
    except Exception as exc:
        log.warning("Home plan AI failed, using deterministic fallback: %s", _ai_error(exc))
        ai_used = False
        notice = FALLBACK_NOTICE

    # 4. Build item results with whitelist validation.
    for slot in plan_slots:
        choice = choices_by_key.get((slot["room"], slot["category"]))
        if not ai_used:
            picks = fallback.pick_options(slot["candidates"], count=3, style=request.style, room=slot["room"])
            slot["selected_id"] = picks[0].id if picks else None
            slot["options"] = picks
            slot["reasons"] = {p.id: "Best value pick from the catalog for this budget and style." for p in picks}
        else:
            valid, recommended_id = _sanitize_home_group(
                choice, slot["candidates"], request.style, slot["room"]
            )
            slot["selected_id"] = recommended_id
            slot["options"] = valid
            slot["reasons"] = {}
            if choice is not None:
                for opt in choice.options:
                    if opt.item_id in {v.id for v in valid}:
                        slot["reasons"][opt.item_id] = opt.reason

    # 5. Budget guard: trim if the recommended total exceeds the budget.
    def _slot_label(slot: dict[str, Any]) -> str:
        return f"{ROOM_LABELS.get(slot['room'], slot['room'])} - {CATEGORY_LABELS.get(slot['category'], slot['category'])}"

    trim_slots = [
        {
            "candidates": slot["candidates"],
            "selected_id": slot["selected_id"],
            "quantity": slot["quantity"],
            "required": True,
            "label": _slot_label(slot),
        }
        for slot in plan_slots
        if slot["selected_id"]
    ]
    total = sum(
        (catalog_svc.get_by_id(s["selected_id"]).price_inr if catalog_svc.get_by_id(s["selected_id"]) else 0) * s["quantity"]
        for s in trim_slots
    )
    if total > budget:
        trimmed, trim_notices = fallback.trim_to_budget(trim_slots, budget)
        trimmed_by_label = {s["label"]: s["selected_id"] for s in trimmed}
        for slot in plan_slots:
            label = _slot_label(slot)
            if label in trimmed_by_label:
                slot["selected_id"] = trimmed_by_label[label]
        if trim_notices:
            notice = (notice + " " if notice else "") + " ".join(trim_notices)

    # 6. Assemble the response.
    rooms_out: list[HomeRoomResult] = []
    total_spent = 0
    for room, room_budget in zip(request.rooms, room_budgets):
        items_out: list[HomeItemResult] = []
        room_spent = 0
        for slot in plan_slots:
            if slot["room"] != room.name:
                continue
            options_out: list[HomeOption] = []
            for item in slot["options"]:
                line_total = item.price_inr * slot["quantity"]
                options_out.append(HomeOption(
                    id=item.id,
                    name=item.name,
                    platform=item.platform.value,
                    unit_price=item.price_inr,
                    line_total=line_total,
                    image=item.image,
                    url=item.url,
                    reason=slot["reasons"].get(item.id, ""),
                    is_recommended=(item.id == slot["selected_id"]),
                ))
            if slot["selected_id"]:
                sel = catalog_svc.get_by_id(slot["selected_id"])
                if sel is not None:
                    room_spent += sel.price_inr * slot["quantity"]
            items_out.append(HomeItemResult(
                category=slot["category"],
                label=CATEGORY_LABELS.get(slot["category"], slot["category"]),
                quantity=slot["quantity"],
                unit_ceiling=slot["unit_ceiling"],
                recommended_id=slot["selected_id"],
                options=options_out,
                unavailable=slot["selected_id"] is None,
            ))
        total_spent += room_spent
        rooms_out.append(HomeRoomResult(
            room=room.name,
            label=ROOM_LABELS.get(room.name, room.name),
            room_budget=room_budget,
            room_spent=room_spent,
            items=items_out,
        ))

    return HomePlanResponse(
        ai_used=ai_used,
        notice=notice,
        budget_total=budget,
        contingency=contingency,
        total_spent=total_spent,
        remaining=budget - total_spent,
        percent_used=percent_used(total_spent, budget),
        rooms=rooms_out,
    )


# ---------------------------------------------------------------------------
# Module 2: Party Planner
# ---------------------------------------------------------------------------

def _party_weights(request: PartyPlanRequest) -> dict[str, float]:
    weights = dict(EVENT_BASE_WEIGHTS[request.event_type])
    if request.guests_travelling:
        stay_share = float(STAY_SHARE[request.event_type])
        remaining = 100.0 - stay_share
        total_three = sum(weights.values())
        weights = {k: v * remaining / total_three for k, v in weights.items()}
        weights["stay"] = stay_share
    if request.venue_type == "outdoor":
        others = [k for k in weights if k != "decoration"]
        total_others = sum(weights[k] for k in others)
        if total_others > 0:
            for k in others:
                weights[k] -= 5.0 * weights[k] / total_others
            weights["decoration"] += 5.0
    if request.duration_hours > 6:
        others = [k for k in weights if k != "entertainment"]
        total_others = sum(weights[k] for k in others)
        if total_others > 0:
            for k in others:
                weights[k] -= 5.0 * weights[k] / total_others
            weights["entertainment"] += 5.0
    return weights


def _find_party_candidates(
    category: str, budget: int, request: PartyPlanRequest
) -> list[CatalogItem]:
    if category == "catering":
        ceiling = int(budget * 1.1)
        base = catalog_svc.filter(
            group="party", category="catering", platforms=CATERING_PLATFORMS
        )
        matching = []
        for item in base:
            attrs = item.attributes
            min_g = attrs.get("min_guests", 0)
            max_g = attrs.get("max_guests", 10**9)
            if item.price_inr * request.guests <= ceiling and min_g <= request.guests <= max_g:
                matching.append(item)
        event_matched = [i for i in matching if request.event_type in i.attributes.get("event_types", [])]
        return (event_matched or matching)[:MAX_CANDIDATES_PER_CATEGORY]

    if category in ("decoration", "entertainment"):
        base = catalog_svc.filter(
            group="party", category=category, platforms=DECOR_ENT_PLATFORMS
        )
        matching = []
        for item in base:
            if item.price_unit.value == "per_hour":
                cost = item.price_inr * request.duration_hours
            else:
                cost = item.price_inr
            if cost <= budget * 1.1:
                matching.append(item)
        event_matched = [i for i in matching if request.event_type in i.attributes.get("event_types", [])]
        return (event_matched or matching)[:MAX_CANDIDATES_PER_CATEGORY]

    if category == "stay":
        base = catalog_svc.filter(
            group="party", category="stay", platforms=STAY_PLATFORMS
        )
        matching = []
        for item in base:
            city = item.attributes.get("city", "any")
            if city.lower() != request.city.lower() and city.lower() != "any":
                continue
            max_occ = item.attributes.get("max_occupancy", 2)
            rooms_needed = ceil_div(request.stay_guests or 1, max_occ)
            cost = item.price_inr * rooms_needed * (request.nights or 1)
            if cost <= budget * 1.1:
                matching.append(item)
        return matching[:MAX_CANDIDATES_PER_CATEGORY]

    return []


def _party_cost(item: CatalogItem, request: PartyPlanRequest) -> int:
    if item.price_unit.value == "per_plate":
        return item.price_inr * request.guests
    if item.price_unit.value == "per_hour":
        return item.price_inr * request.duration_hours
    if item.price_unit.value == "per_night":
        max_occ = item.attributes.get("max_occupancy", 2)
        rooms_needed = ceil_div(request.stay_guests or 1, max_occ)
        return item.price_inr * rooms_needed * (request.nights or 1)
    return item.price_inr


def _sanitize_party_category(
    choice: Optional[PartyCategoryChoice],
    candidates: list[CatalogItem],
) -> tuple[list[CatalogItem], Optional[str]]:
    candidate_ids = {c.id for c in candidates}
    valid: list[CatalogItem] = []
    seen: set[str] = set()
    if choice is not None:
        for opt in choice.options:
            if opt.item_id in candidate_ids and opt.item_id not in seen:
                seen.add(opt.item_id)
                item = catalog_svc.get_by_id(opt.item_id)
                if item is not None:
                    valid.append(item)
    ranked = fallback.rank(candidates)
    for item in ranked:
        if len(valid) >= 3:
            break
        if item.id not in seen:
            seen.add(item.id)
            valid.append(item)
    recommended = valid[0] if valid else None
    return valid, (recommended.id if recommended else None)


async def build_party_plan(
    request: PartyPlanRequest, settings: Settings
) -> PartyPlanResponse | InsufficientBudgetBody:
    budget = request.budget

    if request.guests > 0 and budget // request.guests < 150:
        minimum = 150 * request.guests
        return InsufficientBudgetBody(
            budget_total=budget,
            minimum_required=minimum,
            message=(
                f"Budget per guest must be at least ₹150. For {request.guests} guests, "
                f"the minimum budget is ₹{minimum:,}."
            ),
        )

    contingency = contingency_amount(budget)
    weights = _party_weights(request)
    categories = ["catering", "decoration", "entertainment"]
    if request.guests_travelling:
        categories.append("stay")

    weight_list = [weights[c] for c in categories]
    amounts = largest_remainder_split(budget, weight_list)

    plan_slots: list[dict[str, Any]] = []
    minimum_required = 0
    for cat, amount in zip(categories, amounts):
        candidates = _find_party_candidates(cat, amount, request)
        cheapest = fallback.cheapest(candidates)
        if cheapest is not None:
            minimum_required += _party_cost(cheapest, request)
        plan_slots.append({
            "category": cat,
            "amount": amount,
            "weight": weights[cat],
            "candidates": candidates,
        })

    if minimum_required > budget:
        return InsufficientBudgetBody(
            budget_total=budget,
            minimum_required=minimum_required,
            message=(
                f"Your budget of ₹{budget:,} is too small for this event. "
                f"The cheapest possible combination costs ₹{minimum_required:,}."
            ),
        )

    ai_used = True
    notice: Optional[str] = None
    categories_payload = [
        {
            "category": slot["category"],
            "budget": slot["amount"],
            "candidates": [candidate_dict(c) for c in slot["candidates"]],
        }
        for slot in plan_slots
    ]
    user_prompt = (
        f"Plan my {request.event_type}. Guests: {request.guests}. Duration: {request.duration_hours}h. "
        f"Venue: {request.venue_type}. City: {request.city}. Total budget: ₹{budget:,}.\n"
        f"<user_data>\nUser notes (untrusted): {request.notes}\n</user_data>\n"
        "Choose vendor options for each category below (only from the listed candidate IDs):\n"
        f"<!-- CANDIDATES\n{json.dumps(categories_payload, ensure_ascii=False)}\n-->"
    )

    choices_by_cat: dict[str, PartyCategoryChoice] = {}
    try:
        result = await _ai_call("party", user_prompt, PartyPlanChoice, settings)
        for grp in result.get("categories", []):
            choices_by_cat[grp["category"]] = PartyCategoryChoice.model_validate(grp)
    except Exception as exc:
        log.warning("Party plan AI failed, using deterministic fallback: %s", _ai_error(exc))
        ai_used = False
        notice = FALLBACK_NOTICE

    for slot in plan_slots:
        choice = choices_by_cat.get(slot["category"])
        if not ai_used:
            picks = fallback.pick_options(slot["candidates"], count=3)
            slot["selected_id"] = picks[0].id if picks else None
            slot["options"] = picks
            slot["reasons"] = {p.id: "Best value vendor pick for this budget." for p in picks}
        else:
            valid, recommended_id = _sanitize_party_category(choice, slot["candidates"])
            slot["selected_id"] = recommended_id
            slot["options"] = valid
            slot["reasons"] = {}
            if choice is not None:
                for opt in choice.options:
                    if opt.item_id in {v.id for v in valid}:
                        slot["reasons"][opt.item_id] = opt.reason

    # Budget guard.
    trim_slots = [
        {
            "candidates": slot["candidates"],
            "selected_id": slot["selected_id"],
            "quantity": 1,
            "required": True,
            "label": PARTY_CATEGORY_LABELS.get(slot["category"], slot["category"]),
        }
        for slot in plan_slots
        if slot["selected_id"]
    ]
    def _slot_cost(s: dict) -> int:
        item = catalog_svc.get_by_id(s["selected_id"])
        return _party_cost(item, request) if item else 0

    if sum(_slot_cost(s) for s in trim_slots) > budget:
        trimmed, trim_notices = fallback.trim_to_budget(trim_slots, budget)
        trimmed_by_label = {s["label"]: s["selected_id"] for s in trimmed}
        for slot in plan_slots:
            label = PARTY_CATEGORY_LABELS.get(slot["category"], slot["category"])
            if label in trimmed_by_label:
                slot["selected_id"] = trimmed_by_label[label]
        if trim_notices:
            notice = (notice + " " if notice else "") + " ".join(trim_notices)

    allocation_out: list[PartyAllocation] = []
    total_spent = 0
    for slot in plan_slots:
        options_out: list[PartyOption] = []
        spent = 0
        for item in slot["options"]:
            cost = _party_cost(item, request)
            options_out.append(PartyOption(
                id=item.id,
                name=item.name,
                platform=item.platform.value,
                unit_price=item.price_inr,
                price_unit=item.price_unit.value,
                total_cost=cost,
                reason=slot["reasons"].get(item.id, ""),
                url=item.url,
                image=item.image,
                is_recommended=(item.id == slot["selected_id"]),
            ))
        if slot["selected_id"]:
            sel = catalog_svc.get_by_id(slot["selected_id"])
            if sel is not None:
                spent = _party_cost(sel, request)
        total_spent += spent
        allocation_out.append(PartyAllocation(
            category=slot["category"],
            label=PARTY_CATEGORY_LABELS.get(slot["category"], slot["category"]),
            percent=round(slot["weight"], 1),
            amount=slot["amount"],
            spent=spent,
            options=options_out,
        ))

    return PartyPlanResponse(
        ai_used=ai_used,
        notice=notice,
        budget_total=budget,
        contingency=contingency,
        total_spent=total_spent,
        remaining=budget - total_spent,
        percent_used=percent_used(total_spent, budget),
        per_guest_cost=per_guest_cost(total_spent, request.guests),
        event_type=request.event_type,
        guests=request.guests,
        allocation=allocation_out,
    )


# ---------------------------------------------------------------------------
# Module 3: Jewelry Budget Planner
# ---------------------------------------------------------------------------

def _find_jewelry_candidates(
    request: JewelryPlanRequest,
) -> list[CatalogItem]:
    base = catalog_svc.filter(
        group="jewelry", platforms=JEWELRY_PLATFORMS, max_price=request.budget
    )

    def matches(item: CatalogItem, use_metal: bool, use_stone: bool, use_style: bool) -> bool:
        tags = set(item.tags)
        if request.occasion not in tags:
            return False
        if use_style and request.style not in tags:
            return False
        if use_metal and request.metal != "no_preference" and item.attributes.get("metal") != request.metal:
            return False
        if use_stone and request.stone != "no_preference" and item.attributes.get("stone") != request.stone:
            return False
        return True

    for use_metal, use_stone, use_style in (
        (True, True, True),
        (False, True, True),
        (False, False, True),
        (False, False, False),
    ):
        cands = [i for i in base if matches(i, use_metal, use_stone, use_style)]
        if len(cands) >= 3:
            return cands[:MAX_CANDIDATES_PER_CATEGORY]
    return base[:MAX_CANDIDATES_PER_CATEGORY]


def _validate_palette(raw: dict[str, Any]) -> list[PaletteColor]:
    colors: list[PaletteColor] = []
    seen: set[str] = set()
    for entry in raw.get("dominant_colors", []):
        if not isinstance(entry, dict):
            continue
        hex_code = entry.get("hex", "")
        if not isinstance(hex_code, str):
            continue
        hex_code = hex_code.upper()
        if len(hex_code) == 7 and hex_code[0] == "#" and all(c in "0123456789ABCDEF" for c in hex_code[1:]):
            if hex_code not in seen:
                seen.add(hex_code)
                colors.append(PaletteColor(hex=hex_code, name=str(entry.get("name", ""))[:60]))
        if len(colors) >= 4:
            break
    return colors


async def build_jewelry_plan(
    request: JewelryPlanRequest,
    settings: Settings,
    image_bytes: Optional[bytes] = None,
    image_mime: Optional[str] = None,
) -> JewelryPlanResponse | InsufficientBudgetBody:
    budget = request.budget
    notice: Optional[str] = None

    # 1. Optional outfit image analysis.
    palette: list[PaletteColor] = []
    outfit_summary: Optional[str] = None
    if image_bytes:
        try:
            vision_system = load_prompt("jewelry_vision.txt").substitute()
            result = await generate_structured(
                system_prompt=vision_system,
                user_prompt="Describe the outfit in this image so we can coordinate jewelry.",
                schema=OutfitAnalysis,
                image_bytes=image_bytes,
                mime_type=image_mime,
                settings=settings,
            )
            palette = _validate_palette(result)
            outfit_summary = " ".join(filter(None, [
                result.get("outfit_type", ""),
                result.get("outfit_style", ""),
                result.get("neckline", ""),
            ])) or None
            if not palette:
                notice = IMAGE_UNAVAILABLE_NOTICE
        except Exception as exc:
            log.warning("Outfit vision failed, continuing without it: %s", _ai_error(exc))
            notice = IMAGE_UNAVAILABLE_NOTICE

    # 2. Candidates.
    candidates = _find_jewelry_candidates(request)
    if not candidates:
        cheapest = fallback.cheapest(
            catalog_svc.filter(group="jewelry", platforms=JEWELRY_PLATFORMS)
        )
        minimum = cheapest.price_inr if cheapest else budget + 1
        return InsufficientBudgetBody(
            budget_total=budget,
            minimum_required=minimum,
            message=(
                f"Your budget of ₹{budget:,} is too small for any jewelry in the catalog. "
                f"The cheapest piece costs ₹{minimum:,}."
            ),
        )

    palette_hexes = [c.hex for c in palette]
    ranked = sorted(
        candidates,
        key=lambda i: (
            -jewelry_match_score(i, request.occasion, request.style, request.metal, request.stone, palette_hexes),
            i.price_inr,
        ),
    )

    # 3. Ask Gemini to pick 3-5 recommendations.
    ai_used = True
    top = ranked[:MAX_CANDIDATES_PER_CATEGORY]
    palette_block = ""
    if palette_hexes:
        palette_block = "Outfit palette (dominant colours): " + ", ".join(palette_hexes) + "\n"
    user_prompt = (
        f"Pick jewelry for a {request.occasion}. Budget: ₹{budget:,}. Style: {request.style}. "
        f"Metal: {request.metal}. Stone: {request.stone}.\n"
        f"{palette_block}"
        f"<user_data>\nUser notes (untrusted): {request.notes}\n</user_data>\n"
        "Choose recommendations below (only from the listed candidate IDs):\n"
        f"<!-- CANDIDATES\n{_candidates_json(top)}\n-->"
    )

    picked: list[CatalogItem] = []
    reasons: dict[str, str] = {}
    try:
        result = await _ai_call("jewelry", user_prompt, JewelryChoice, settings)
        candidate_ids = {c.id for c in top}
        seen: set[str] = set()
        for rec in result.get("recommendations", []):
            rid = rec.get("id", "")
            if rid in candidate_ids and rid not in seen:
                seen.add(rid)
                item = catalog_svc.get_by_id(rid)
                if item is not None:
                    picked.append(item)
                    reasons[rid] = rec.get("why_it_matches", "")[:200]
    except Exception as exc:
        log.warning("Jewelry AI failed, using deterministic fallback: %s", _ai_error(exc))
        ai_used = False
        notice = FALLBACK_NOTICE
        picked = []
        reasons = {}

    if not ai_used:
        picked = ranked[:5]
        reasons = {p.id: f"Great match for {request.occasion} in {request.style} style." for p in picked}

    # 4. Enforce the budget: drop lowest-ranked pieces until the sum fits.
    picked = sorted(
        picked,
        key=lambda i: (
            -jewelry_match_score(i, request.occasion, request.style, request.metal, request.stone, palette_hexes),
            i.price_inr,
        ),
    )
    total = sum(p.price_inr for p in picked)
    while total > budget and picked:
        picked.pop()
        total = sum(p.price_inr for p in picked)

    if not picked:
        cheapest = fallback.cheapest(candidates)
        minimum = cheapest.price_inr if cheapest else budget + 1
        return InsufficientBudgetBody(
            budget_total=budget,
            minimum_required=minimum,
            message=(
                f"Your budget of ₹{budget:,} is too small for any matching jewelry. "
                f"The cheapest matching piece costs ₹{minimum:,}."
            ),
        )

    recs_out = []
    for item in picked:
        recs_out.append({
            "id": item.id,
            "name": item.name,
            "platform": item.platform.value,
            "price": item.price_inr,
            "image": item.image,
            "url": item.url,
            "colors": item.attributes.get("colors", []),
            "why_it_matches": reasons.get(item.id, ""),
            "match_score": jewelry_match_score(
                item, request.occasion, request.style, request.metal, request.stone, palette_hexes
            ),
        })

    total_spent = sum(r["price"] for r in recs_out)
    return JewelryPlanResponse(
        ai_used=ai_used,
        notice=notice,
        budget_total=budget,
        total_spent=total_spent,
        remaining=budget - total_spent,
        percent_used=percent_used(total_spent, budget),
        palette=palette,
        outfit_summary=outfit_summary,
        recommendations=recs_out,  # type: ignore[arg-type]
    )
