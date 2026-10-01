"""Catalog loading, validation, and pure query helpers."""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.models.common import CatalogItem

log = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "catalog.json"


class CatalogError(Exception):
    pass


@lru_cache(maxsize=1)
def load_catalog() -> list[CatalogItem]:
    """Load and validate the catalog once at startup. Fail fast if malformed."""
    try:
        raw = CATALOG_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise CatalogError(f"Cannot read catalog at {CATALOG_PATH}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CatalogError(f"Catalog is not valid JSON: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise CatalogError("Catalog must be a non-empty JSON array")

    items: list[CatalogItem] = []
    seen: set[str] = set()
    for idx, entry in enumerate(data):
        try:
            item = CatalogItem.model_validate(entry)
        except Exception as exc:
            raise CatalogError(f"Catalog item at index {idx} is invalid: {exc}") from exc
        if item.id in seen:
            raise CatalogError(f"Duplicate catalog id: {item.id}")
        seen.add(item.id)
        items.append(item)

    log.info("Loaded %d catalog items", len(items))
    return items


@lru_cache(maxsize=1)
def _by_id() -> dict[str, CatalogItem]:
    return {item.id: item for item in load_catalog()}


def get_by_id(item_id: str) -> Optional[CatalogItem]:
    return _by_id().get(item_id)


def all_items() -> list[CatalogItem]:
    return load_catalog()


def filter(
    group: Optional[str] = None,
    category: Optional[str] = None,
    platforms: Optional[list[str]] = None,
    max_price: Optional[int] = None,
    tags_any: Optional[list[str]] = None,
    tags_all: Optional[list[str]] = None,
) -> list[CatalogItem]:
    """Pure filter. Never mutates the catalog."""
    platform_set = set(platforms) if platforms else None
    any_set = set(tags_any) if tags_any else None
    all_set = set(tags_all) if tags_all else None
    result = []
    for item in load_catalog():
        if group is not None and item.group.value != group:
            continue
        if category is not None and item.category != category:
            continue
        if platform_set is not None and item.platform.value not in platform_set:
            continue
        if max_price is not None and item.price_inr > max_price:
            continue
        if any_set is not None and not any_set.intersection(item.tags):
            continue
        if all_set is not None and not all_set.issubset(item.tags):
            continue
        result.append(item)
    return result


def by_category(group: str) -> dict[str, list[CatalogItem]]:
    """Map category -> items for a group, sorted by price ascending."""
    out: dict[str, list[CatalogItem]] = {}
    for item in filter(group=group):
        out.setdefault(item.category, []).append(item)
    for items in out.values():
        items.sort(key=lambda i: (i.price_inr, -i.rating))
    return out


def cities() -> list[str]:
    """Sorted list of distinct OYO cities (excluding 'any')."""
    cities = set()
    for item in filter(group="party", category="stay", platforms=["OYO"]):
        city = item.attributes.get("city")
        if isinstance(city, str) and city.lower() != "any":
            cities.add(city)
    return sorted(cities)
