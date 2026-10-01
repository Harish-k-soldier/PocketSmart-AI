import pytest

from app.services import catalog as catalog_svc


VALID_REQUEST = {
    "budget": 150000,
    "style": "modern",
    "notes": "",
    "rooms": [
        {"name": "living_room", "items": {"lights": 3, "ceiling_fans": 1, "sofas": 1}},
        {"name": "bedroom", "items": {"beds": 1, "wardrobes": 1}},
    ],
}


async def test_home_plan_valid(client):
    resp = await client.post("/api/home-plan", json=VALID_REQUEST)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["ai_used"] is True
    assert data["budget_total"] == 150000
    assert data["contingency"] == 7500

    catalog_ids = {i.id for i in catalog_svc.load_catalog()}
    total = 0
    for room in data["rooms"]:
        for item in room["items"]:
            assert item["recommended_id"] in catalog_ids
            for opt in item["options"]:
                assert opt["id"] in catalog_ids
            sel = next(o for o in item["options"] if o["id"] == item["recommended_id"])
            total += sel["unit_price"] * item["quantity"]
    assert data["total_spent"] == total
    assert data["remaining"] == data["budget_total"] - data["total_spent"]
    assert data["remaining"] >= 0
    assert data["total_spent"] <= data["budget_total"]


async def test_home_plan_invented_id_sanitized(client, patch_gemini):
    real_ids = [i.id for i in catalog_svc.filter(group="home", category="lights")][:2]
    patch_gemini([{
        "groups": [
            {
                "room": "living_room",
                "category": "lights",
                "options": [
                    {"item_id": "FAKE-INVENTED-001", "reason": "invented"},
                    {"item_id": real_ids[0], "reason": "real"},
                ],
                "recommended_id": "FAKE-INVENTED-001",
            }
        ]
    }])
    resp = await client.post("/api/home-plan", json=VALID_REQUEST)
    assert resp.status_code == 200
    data = resp.json()
    catalog_ids = {i.id for i in catalog_svc.load_catalog()}
    for room in data["rooms"]:
        for item in room["items"]:
            assert item["recommended_id"] in catalog_ids
            for opt in item["options"]:
                assert opt["id"] in catalog_ids
    assert data["total_spent"] <= data["budget_total"]


async def test_home_plan_fallback_on_ai_failure(client, patch_gemini):
    patch_gemini([Exception("boom"), Exception("boom again")])
    resp = await client.post("/api/home-plan", json=VALID_REQUEST)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_used"] is False
    assert data["notice"] is not None
    assert "without AI" in data["notice"]
    assert data["total_spent"] <= data["budget_total"]
    assert data["remaining"] >= 0


async def test_home_plan_insufficient_budget(client):
    resp = await client.post("/api/home-plan", json={
        "budget": 10000,
        "style": "modern",
        "rooms": [{"name": "living_room", "items": {"sofas": 3, "beds": 2, "wardrobes": 2}}],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "insufficient_budget"
    assert data["minimum_required"] > 10000
    assert "message" in data


@pytest.mark.parametrize("payload,field", [
    ({"budget": 5000, "rooms": [{"name": "living_room", "items": {"lights": 1}}]}, "budget"),
    ({"budget": 200000000, "rooms": [{"name": "living_room", "items": {"lights": 1}}]}, "budget"),
    ({"budget": 150000, "rooms": []}, "rooms"),
    ({"budget": 150000, "rooms": [{"name": "living_room", "items": {"lights": 0}}]}, "rooms"),
    ({"budget": 150000, "rooms": [{"name": "living_room", "items": {"lights": 11}}]}, "items"),
    ({"budget": 150000, "rooms": [{"name": "unknown_room", "items": {"lights": 1}}]}, "name"),
    ({"budget": 150000, "rooms": [
        {"name": "living_room", "items": {"lights": 1}},
        {"name": "living_room", "items": {"lights": 1}},
    ]}, "name"),
    ({"budget": 150000, "style": "art_deco", "rooms": [{"name": "living_room", "items": {"lights": 1}}]}, "style"),
    ({"budget": "lots", "rooms": [{"name": "living_room", "items": {"lights": 1}}]}, "budget"),
])
async def test_home_plan_validation_errors(client, payload, field):
    resp = await client.post("/api/home-plan", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "fields" in data["error"]
    assert data["error"]["message"]


async def test_home_plan_not_configured(client, test_settings):
    test_settings.use_mock_ai = False
    test_settings.gemini_api_key = ""
    resp = await client.post("/api/home-plan", json=VALID_REQUEST)
    assert resp.status_code == 503
    data = resp.json()
    assert data["error"]["code"] == "AI_NOT_CONFIGURED"
