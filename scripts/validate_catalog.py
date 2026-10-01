#!/usr/bin/env python3
"""Standalone catalog validator. Exits non-zero with clear messages on any problem."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "catalog.json"

PLATFORMS = {"Amazon", "Flipkart", "IKEA", "Swiggy", "Zomato", "OYO"}
GROUPS = {"home", "party", "jewelry"}
PRICE_UNITS = {"per_item", "per_plate", "per_event", "per_hour", "per_night", "per_set"}
ID_RE = re.compile(r"^[A-Z]+-[A-Z_]+-[0-9]{3}$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

REQUIRED_HOME_CATEGORIES = {
    "lights", "ceiling_fans", "dining_tables", "sofas", "beds", "wardrobes",
    "curtains", "rugs", "wall_decor", "kitchen_storage", "study_tables", "mattresses",
}
REQUIRED_PARTY_CATEGORIES = {"catering", "decoration", "entertainment", "stay"}
REQUIRED_JEWELRY_CATEGORIES = {
    "necklace_set", "earrings", "bracelet", "ring", "maang_tikka", "bangles", "pendant",
}
REQUIRED_JEWELRY_STYLES = {"traditional", "modern", "minimalist", "statement"}
REQUIRED_JEWELRY_OCCASIONS = {"wedding", "festival", "office", "party"}

REQUIRED_FIELDS = {
    "id": str, "name": str, "platform": str, "category": str, "group": str,
    "price_inr": int, "price_unit": str, "tags": list, "attributes": dict,
    "rating": (int, float), "image": str, "url": str,
}


def fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def validate(data: list[dict]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, list) or not data:
        return ["catalog.json must be a non-empty JSON array"]

    ids = [item.get("id") for item in data if isinstance(item, dict)]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        fail(errors, f"duplicate id: {dup}")

    platform_counts: Counter = Counter()
    categories_by_group: dict[str, set[str]] = {"home": set(), "party": set(), "jewelry": set()}
    jewelry_styles: set[str] = set()
    jewelry_occasions: set[str] = set()

    for idx, item in enumerate(data):
        where = f"item[{idx}]"
        if not isinstance(item, dict):
            fail(errors, f"{where}: not an object")
            continue
        iid = item.get("id", f"<missing id at index {idx}>")
        where = f"{where} ({iid})"

        for field, typ in REQUIRED_FIELDS.items():
            if field not in item:
                fail(errors, f"{where}: missing required field '{field}'")
            elif not isinstance(item[field], typ) or isinstance(item[field], bool) and typ is int:
                fail(errors, f"{where}: field '{field}' has wrong type (expected {typ})")

        if "id" in item:
            if not isinstance(item["id"], str) or not ID_RE.match(item["id"]):
                fail(errors, f"{where}: id must match <PLATFORM>-<CATEGORY>-<NNN> uppercase")
        if item.get("platform") not in PLATFORMS:
            fail(errors, f"{where}: platform {item.get('platform')!r} not in {sorted(PLATFORMS)}")
        else:
            platform_counts[item["platform"]] += 1
        if item.get("group") not in GROUPS:
            fail(errors, f"{where}: group {item.get('group')!r} not in {sorted(GROUPS)}")
        if item.get("price_unit") not in PRICE_UNITS:
            fail(errors, f"{where}: price_unit {item.get('price_unit')!r} not in {sorted(PRICE_UNITS)}")
        price = item.get("price_inr")
        if isinstance(price, int) and not isinstance(price, bool):
            if price <= 0:
                fail(errors, f"{where}: price_inr must be positive, got {price}")
        if "url" in item and (not isinstance(item["url"], str) or not item["url"].startswith("https://")):
            fail(errors, f"{where}: url must be an https:// URL")
        if "tags" in item and isinstance(item["tags"], list):
            for t in item["tags"]:
                if not isinstance(t, str) or t != t.lower() or " " in t:
                    fail(errors, f"{where}: tag {t!r} must be lowercase snake_case")

        group = item.get("group")
        category = item.get("category")
        if group in categories_by_group and isinstance(category, str):
            categories_by_group[group].add(category)

        if group == "jewelry":
            attrs = item.get("attributes", {})
            metal = attrs.get("metal")
            stone = attrs.get("stone")
            colors = attrs.get("colors")
            if not isinstance(metal, str) or not metal:
                fail(errors, f"{where}: jewelry item lacks attributes.metal")
            if not isinstance(stone, str) or not stone:
                fail(errors, f"{where}: jewelry item lacks attributes.stone")
            if not isinstance(colors, list) or not colors:
                fail(errors, f"{where}: jewelry item lacks attributes.colors")
            else:
                for c in colors:
                    if not isinstance(c, str) or not HEX_RE.match(c):
                        fail(errors, f"{where}: invalid hex color {c!r}")
                if len(colors) > 3:
                    fail(errors, f"{where}: attributes.colors must have 1-3 entries")
            tags = set(item.get("tags", []))
            jewelry_styles |= tags & REQUIRED_JEWELRY_STYLES
            jewelry_occasions |= tags & REQUIRED_JEWELRY_OCCASIONS

    for platform in sorted(PLATFORMS):
        count = platform_counts.get(platform, 0)
        if count < 15:
            fail(errors, f"platform {platform} has {count} items; minimum is 15")

    for group, required in (
        ("home", REQUIRED_HOME_CATEGORIES),
        ("party", REQUIRED_PARTY_CATEGORIES),
        ("jewelry", REQUIRED_JEWELRY_CATEGORIES),
    ):
        missing = required - categories_by_group[group]
        if missing:
            fail(errors, f"group '{group}' is missing required categories: {sorted(missing)}")

    missing_styles = REQUIRED_JEWELRY_STYLES - jewelry_styles
    if missing_styles:
        fail(errors, f"jewelry items missing style tags: {sorted(missing_styles)}")
    missing_occasions = REQUIRED_JEWELRY_OCCASIONS - jewelry_occasions
    if missing_occasions:
        fail(errors, f"jewelry items missing occasion tags: {sorted(missing_occasions)}")

    return errors


def main() -> int:
    try:
        raw = CATALOG_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read {CATALOG_PATH}: {exc}", file=sys.stderr)
        return 1
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {CATALOG_PATH}: {exc}", file=sys.stderr)
        return 1

    errors = validate(data)
    if errors:
        print(f"CATALOG INVALID ({len(errors)} problem(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"Catalog OK: {len(data)} items, {len(set(i['id'] for i in data))} unique ids.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
