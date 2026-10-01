"""Offline mock Gemini used when USE_MOCK_AI=true.

Returns schema-valid responses by picking the first N candidate IDs it is
given. The user prompt must contain a JSON block:

    <!-- CANDIDATES
    [{"id": "...", ...}, ...]
    -->

or, for grouped schemas (home/party):

    <!-- CANDIDATES
    [{"room": "...", "category": "...", "candidates": [{"id": "..."}, ...]}, ...]
    -->

so the mock chooses from the same whitelist the real model would see.
"""

import json
import logging
import re
from typing import Any, Optional, Type

from pydantic import BaseModel

log = logging.getLogger(__name__)

_CANDIDATES_RE = re.compile(r"<!--\s*CANDIDATES\s*(\[.*?\])\s*-->", re.DOTALL)


def _extract_candidates(user_prompt: str) -> list[dict[str, Any]]:
    match = _CANDIDATES_RE.search(user_prompt)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _is_grouped(entries: list[dict[str, Any]]) -> bool:
    return bool(entries) and isinstance(entries[0].get("candidates"), list)


def _pick_ids(candidates: list[dict[str, Any]], count: int) -> list[str]:
    return [c["id"] for c in candidates[:count] if isinstance(c.get("id"), str)]


async def generate_structured(
    system_prompt: str,
    user_prompt: str,
    schema: Type[BaseModel],
    image_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
) -> dict[str, Any]:
    """Build a schema-valid response from the candidate whitelist in the prompt."""
    entries = _extract_candidates(user_prompt)
    model_name = getattr(schema, "__name__", "Response")
    log.info("Mock AI (%s): %d candidate entries available", model_name, len(entries))

    if model_name == "HomePlanChoice":
        groups = []
        for entry in entries:
            picks = _pick_ids(entry.get("candidates", []), 3)
            if not picks:
                continue
            groups.append({
                "room": entry.get("room", ""),
                "category": entry.get("category", ""),
                "options": [
                    {"item_id": pid, "reason": "Mock AI pick: good value within the allocated budget."}
                    for pid in picks
                ],
                "recommended_id": picks[0],
            })
        if not groups:
            raise ValueError("mock_ai: no candidates found in prompt")
        return {"groups": groups}

    if model_name == "PartyPlanChoice":
        categories = []
        for entry in entries:
            picks = _pick_ids(entry.get("candidates", []), 3)
            if not picks:
                continue
            categories.append({
                "category": entry.get("category", ""),
                "options": [
                    {"item_id": pid, "reason": "Mock AI pick: fits the allocated budget."}
                    for pid in picks
                ],
                "recommended_id": picks[0],
            })
        if not categories:
            raise ValueError("mock_ai: no candidates found in prompt")
        return {"categories": categories}

    if model_name == "JewelryChoice":
        picks = _pick_ids(entries, 5)
        if not picks:
            raise ValueError("mock_ai: no candidates found in prompt")
        return {
            "recommendations": [
                {
                    "id": pid,
                    "why_it_matches": "Mock AI pick: matches the chosen occasion and style.",
                }
                for pid in picks
            ]
        }

    if model_name == "OutfitAnalysis":
        return {
            "dominant_colors": [{"hex": "#B22222", "name": "crimson red"}],
            "outfit_type": "saree",
            "outfit_style": "traditional",
            "neckline": "v-neck",
            "notes": "Mock AI outfit analysis.",
        }

    raise ValueError(f"mock_ai: unsupported schema {model_name}")
