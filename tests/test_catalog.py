import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from app.services import catalog as catalog_svc
from app.services.catalog import CatalogError

ROOT = Path(__file__).resolve().parent.parent


def test_validate_catalog_script_passes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_catalog.py")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_catalog_loads_and_validates():
    items = catalog_svc.load_catalog()
    assert len(items) >= 90


def test_ids_unique():
    items = catalog_svc.load_catalog()
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids))


def test_at_least_15_per_platform():
    items = catalog_svc.load_catalog()
    counts = Counter(i.platform.value for i in items)
    for platform in ("Amazon", "Flipkart", "IKEA", "Swiggy", "Zomato", "OYO"):
        assert counts[platform] >= 15, f"{platform} has only {counts[platform]}"


def test_required_categories_exist():
    home = catalog_svc.by_category("home")
    for cat in ("lights", "ceiling_fans", "dining_tables", "sofas", "beds", "wardrobes",
                "curtains", "rugs", "wall_decor", "kitchen_storage", "study_tables", "mattresses"):
        assert cat in home and home[cat], f"missing home category {cat}"
    party = catalog_svc.by_category("party")
    for cat in ("catering", "decoration", "entertainment", "stay"):
        assert cat in party and party[cat], f"missing party category {cat}"
    jewelry = catalog_svc.by_category("jewelry")
    for cat in ("necklace_set", "earrings", "bracelet", "ring", "maang_tikka", "bangles", "pendant"):
        assert cat in jewelry and jewelry[cat], f"missing jewelry category {cat}"


def test_two_price_tiers_per_home_category():
    home = catalog_svc.by_category("home")
    for cat, items in home.items():
        prices = {i.price_inr for i in items}
        assert len(prices) >= 2, f"category {cat} has only one price tier: {prices}"


def test_jewelry_attributes_valid():
    import re
    hex_re = re.compile(r"^#[0-9A-Fa-f]{6}$")
    for item in catalog_svc.filter(group="jewelry"):
        assert item.attributes.get("metal"), f"{item.id} missing metal"
        assert item.attributes.get("stone"), f"{item.id} missing stone"
        colors = item.attributes.get("colors", [])
        assert 1 <= len(colors) <= 3, f"{item.id} bad colors count"
        for c in colors:
            assert hex_re.match(c), f"{item.id} invalid hex {c}"


def test_filter_is_pure():
    items = catalog_svc.load_catalog()
    before = [i.id for i in items]
    result = catalog_svc.filter(group="home", category="lights", platforms=["IKEA"])
    assert all(i.group.value == "home" for i in result)
    assert all(i.category == "lights" for i in result)
    assert all(i.platform.value == "IKEA" for i in result)
    after = [i.id for i in catalog_svc.load_catalog()]
    assert before == after


def test_get_by_id():
    item = catalog_svc.get_by_id("IKEA-LIGHT-001")
    assert item is not None
    assert item.name == "ALANG LED Floor Lamp"
    assert catalog_svc.get_by_id("NOPE-000") is None


def test_cities():
    cities = catalog_svc.cities()
    for city in ("Delhi", "Mumbai", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune", "Jaipur"):
        assert city in cities
    assert "any" not in cities


def test_malformed_catalog_fails_fast(tmp_path, monkeypatch):
    bad = tmp_path / "catalog.json"
    bad.write_text(json.dumps([{"id": "X", "name": 123}]))
    monkeypatch.setattr(catalog_svc, "CATALOG_PATH", bad)
    catalog_svc.load_catalog.cache_clear()
    catalog_svc._by_id.cache_clear()
    with pytest.raises(CatalogError):
        catalog_svc.load_catalog()
    catalog_svc.load_catalog.cache_clear()
    catalog_svc._by_id.cache_clear()


def test_sanitize_text_strips_control_chars():
    from app.models.common import sanitize_text
    assert sanitize_text("hello\x00world\x01") == "helloworld"
    assert sanitize_text("normal text") == "normal text"
    assert sanitize_text("x" * 300) == "x" * 200
    assert sanitize_text("keep\ttabs\nand newlines") == "keep\ttabs\nand newlines"
