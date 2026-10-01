import pytest
import math


from app.services import catalog as catalog_svc


VALID_REQUEST = {
    "budget": 150000,
    "guests": 100,
    "event_type": "wedding",
    "venue_type": "indoor",
    "city": "any",
    "duration_hours": 4,
    "guests_travelling": False,
    "notes": "",
}


async def test_party_plan_valid(client):
    resp = await client.post("/api/party-plan", json=VALID_REQUEST)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["event_type"] == "wedding"
    assert data["guests"] == 100
    assert data["per_guest_cost"] == round(data["total_spent"] / 100)
    assert data["total_spent"] <= data["budget_total"]
    assert data["remaining"] == data["budget_total"] - data["total_spent"]
    assert data["remaining"] >= 0

    alloc = data["allocation"]
    assert sum(a["amount"] for a in alloc) == data["budget_total"]
    cats = {a["category"] for a in alloc}
    assert "stay" not in cats

    catalog_ids = {i.id for i in catalog_svc.load_catalog()}
    for a in alloc:
        for opt in a["options"]:
            assert opt["id"] in catalog_ids


async def test_party_plan_stay_only_when_travelling(client):
    resp = await client.post("/api/party-plan", json=VALID_REQUEST)
    assert "stay" not in {a["category"] for a in resp.json()["allocation"]}

    travelling = dict(VALID_REQUEST, guests_travelling=True, stay_guests=10, nights=2)
    resp = await client.post("/api/party-plan", json=travelling)
    assert resp.status_code == 200
    data = resp.json()
    cats = {a["category"]: a for a in data["allocation"]}
    assert "stay" in cats
    stay = cats["stay"]
    assert stay["amount"] > 0
    for opt in stay["options"]:
        assert opt["price_unit"] == "per_night"


async def test_party_plan_wedding_vs_birthday_differ(client):
    wedding = await client.post("/api/party-plan", json=VALID_REQUEST)
    birthday = await client.post("/api/party-plan", json=dict(VALID_REQUEST, event_type="birthday"))
    w = {a["category"]: a["amount"] for a in wedding.json()["allocation"]}
    b = {a["category"]: a["amount"] for a in birthday.json()["allocation"]}
    assert w["catering"] != b["catering"] or w["decoration"] != b["decoration"]


async def test_party_plan_catering_cost_per_plate_times_guests(client):
    resp = await client.post("/api/party-plan", json=VALID_REQUEST)
    data = resp.json()
    catering = next(a for a in data["allocation"] if a["category"] == "catering")
    for opt in catering["options"]:
        assert opt["price_unit"] == "per_plate"
        assert opt["total_cost"] == opt["unit_price"] * 100


async def test_party_plan_stay_room_count_uses_ceil(client):
    travelling = dict(VALID_REQUEST, guests_travelling=True, stay_guests=5, nights=1, city="Delhi")
    resp = await client.post("/api/party-plan", json=travelling)
    data = resp.json()
    stay = next(a for a in data["allocation"] if a["category"] == "stay")
    for opt in stay["options"]:
        item = catalog_svc.get_by_id(opt["id"])
        max_occ = item.attributes.get("max_occupancy", 2)
        rooms = math.ceil(5 / max_occ)
        assert opt["total_cost"] == opt["unit_price"] * rooms * 1


async def test_party_plan_insufficient_budget(client):
    resp = await client.post("/api/party-plan", json=dict(VALID_REQUEST, budget=5000, guests=100))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "insufficient_budget"
    assert data["minimum_required"] >= 150 * 100


@pytest.mark.parametrize("payload,field", [
    ({"budget": 1000, "guests": 100}, "budget"),
    ({"budget": 150000, "guests": 1}, "guests"),
    ({"budget": 150000, "guests": 3000}, "guests"),
    ({"budget": 150000, "guests": 100, "event_type": "concert"}, "event_type"),
    ({"budget": 150000, "guests": 100, "venue_type": "pool"}, "venue_type"),
    ({"budget": 150000, "guests": 100, "duration_hours": 25}, "duration_hours"),
    ({"budget": 150000, "guests": 100, "guests_travelling": True}, "stay_guests"),
    ({"budget": 150000, "guests": 100, "guests_travelling": True, "stay_guests": 200, "nights": 2}, "stay_guests"),
    ({"budget": 150000, "guests": 100, "guests_travelling": True, "stay_guests": 10, "nights": 9}, "nights"),
])
async def test_party_plan_validation_errors(client, payload, field):
    resp = await client.post("/api/party-plan", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["fields"]


async def test_party_plan_fallback(client, patch_gemini):
    patch_gemini([Exception("boom"), Exception("boom")])
    resp = await client.post("/api/party-plan", json=VALID_REQUEST)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_used"] is False
    assert data["notice"] is not None
    assert data["total_spent"] <= data["budget_total"]
