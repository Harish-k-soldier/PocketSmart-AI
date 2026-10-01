"""Deterministic non-AI selection and budget trimming.

Used when Gemini fails twice: the user still gets a valid plan, with
ai_used=false and a notice. Selection is "cheapest good rating with style
matching" — fully deterministic so tests can rely on it.
"""

from typing import Optional

from app.models.common import CatalogItem


def score_candidate(item: CatalogItem, style: Optional[str] = None, room: Optional[str] = None) -> float:
    """Higher is better. Style/room tag matches first, then rating, then price."""
    score = 0.0
    if style and style in item.tags:
        score += 100.0
    if room and room in item.tags:
        score += 50.0
    score += item.rating * 10.0
    score -= item.price_inr / 10000.0
    return score


def rank(
    candidates: list[CatalogItem],
    style: Optional[str] = None,
    room: Optional[str] = None,
) -> list[CatalogItem]:
    """Best-first ordering: score desc, then price asc, then rating desc, then id."""
    return sorted(
        candidates,
        key=lambda i: (-score_candidate(i, style, room), i.price_inr, -i.rating, i.id),
    )


def pick_options(
    candidates: list[CatalogItem],
    count: int = 3,
    style: Optional[str] = None,
    room: Optional[str] = None,
) -> list[CatalogItem]:
    """Top-N distinct candidates, preferring distinct platforms."""
    ranked = rank(candidates, style, room)
    picked: list[CatalogItem] = []
    seen_platforms: set[str] = set()
    for item in ranked:
        if len(picked) >= count:
            break
        if item.platform.value in seen_platforms and len(picked) < count - 1:
            continue
        picked.append(item)
        seen_platforms.add(item.platform.value)
    # Backfill if platform diversity left us short.
    for item in ranked:
        if len(picked) >= count:
            break
        if item not in picked:
            picked.append(item)
    return picked


def cheapest(candidates: list[CatalogItem]) -> Optional[CatalogItem]:
    if not candidates:
        return None
    return min(candidates, key=lambda i: (i.price_inr, -i.rating, i.id))


def trim_to_budget(
    slots: list[dict],
    budget: int,
) -> tuple[list[dict], list[str]]:
    """Deterministically bring selections under `budget`.

    Each slot: {"candidates": [CatalogItem], "selected_id": str, "quantity": int,
    "required": bool, "label": str}. Cost of a slot = unit price x quantity.

    Strategy: while over budget, find the slot where swapping to the cheapest
    candidate saves the most; if no swap helps and the slot is optional, drop it.
    Returns (adjusted slots, notices).
    """
    notices: list[str] = []
    working = [dict(s) for s in slots]

    def slot_cost(slot: dict) -> int:
        item = next((c for c in slot["candidates"] if c.id == slot["selected_id"]), None)
        return (item.price_inr if item else 0) * slot["quantity"]

    def total() -> int:
        return sum(slot_cost(s) for s in working)

    guard = 0
    while total() > budget and guard < 1000:
        guard += 1
        best_swap: Optional[tuple[int, CatalogItem, int]] = None
        for idx, slot in enumerate(working):
            current = next((c for c in slot["candidates"] if c.id == slot["selected_id"]), None)
            if current is None:
                continue
            cheap = cheapest(slot["candidates"])
            if cheap is None or cheap.id == current.id:
                continue
            saving = (current.price_inr - cheap.price_inr) * slot["quantity"]
            if saving > 0 and (best_swap is None or saving > best_swap[2]):
                best_swap = (idx, cheap, saving)

        if best_swap is not None:
            idx, cheap, _ = best_swap
            working[idx]["selected_id"] = cheap.id
            continue

        optional = [s for s in working if not s.get("required", True)]
        if optional:
            victim = max(optional, key=slot_cost)
            notices.append(
                f"Dropped {victim.get('label', 'an optional item')} to stay within budget."
            )
            working.remove(victim)
            continue

        break

    return working, notices
