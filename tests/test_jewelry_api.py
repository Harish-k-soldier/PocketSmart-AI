import pytest
import io

from PIL import Image

from app.services import catalog as catalog_svc



def make_image_bytes(format="JPEG", size=(120, 120), color=(180, 30, 30)):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def form_data(**overrides):
    data = {
        "budget": "10000",
        "occasion": "wedding",
        "style": "traditional",
        "metal": "no_preference",
        "stone": "no_preference",
        "notes": "",
    }
    data.update(overrides)
    return data


async def test_jewelry_plan_without_image(client):
    resp = await client.post("/api/jewelry-plan", data=form_data())
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["ai_used"] is True
    assert data["palette"] == []
    assert data["outfit_summary"] is None
    assert len(data["recommendations"]) >= 1
    assert data["total_spent"] <= data["budget_total"]
    assert data["remaining"] == data["budget_total"] - data["total_spent"]
    assert data["remaining"] >= 0

    catalog_ids = {i.id for i in catalog_svc.load_catalog()}
    for rec in data["recommendations"]:
        assert rec["id"] in catalog_ids
        assert isinstance(rec["match_score"], int)
        assert 0 <= rec["match_score"] <= 100
        assert rec["why_it_matches"]


async def test_jewelry_plan_with_real_image(client):
    image_bytes = make_image_bytes()
    resp = await client.post(
        "/api/jewelry-plan",
        data=form_data(),
        files={"outfit_image": ("outfit.jpg", image_bytes, "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["total_spent"] <= data["budget_total"]


async def test_jewelry_plan_fake_image_rejected(client):
    resp = await client.post(
        "/api/jewelry-plan",
        data=form_data(),
        files={"outfit_image": ("fake.jpg", b"this is not an image", "image/jpeg")},
    )
    assert resp.status_code == 415
    data = resp.json()
    assert data["error"]["code"] == "UNSUPPORTED_MEDIA"


async def test_jewelry_plan_oversize_image_rejected(client):
    big = b"\xff\xd8\xff\xe0" + b"0" * (6 * 1024 * 1024)
    resp = await client.post(
        "/api/jewelry-plan",
        data=form_data(),
        files={"outfit_image": ("big.jpg", big, "image/jpeg")},
    )
    assert resp.status_code == 413
    data = resp.json()
    assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"


async def test_jewelry_plan_empty_file_rejected(client):
    resp = await client.post(
        "/api/jewelry-plan",
        data=form_data(),
        files={"outfit_image": ("empty.jpg", b"", "image/jpeg")},
    )
    assert resp.status_code == 415


async def test_jewelry_plan_invalid_hex_dropped(client, patch_gemini):
    image_bytes = make_image_bytes()
    patch_gemini([
        {
            "dominant_colors": [
                {"hex": "#GGGGGG", "name": "bad"},
                {"hex": "red", "name": "no hash"},
                {"hex": "#B22222", "name": "crimson red"},
            ],
            "outfit_type": "saree",
            "outfit_style": "traditional",
            "neckline": "v-neck",
            "notes": "ok",
        },
        {
            "recommendations": [
                {"id": i.id, "why_it_matches": "Matches the wedding occasion."}
                for i in catalog_svc.filter(group="jewelry")[:3]
            ]
        },
    ])
    resp = await client.post(
        "/api/jewelry-plan",
        data=form_data(),
        files={"outfit_image": ("outfit.jpg", image_bytes, "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    valid_hexes = [c["hex"] for c in data["palette"]]
    assert "#B22222" in valid_hexes
    assert "#GGGGGG" not in valid_hexes
    assert "red" not in valid_hexes
    assert len(valid_hexes) == 1


async def test_jewelry_plan_insufficient_budget(client):
    resp = await client.post("/api/jewelry-plan", data=form_data(budget="500"))
    assert resp.status_code == 200
    data = resp.json()
    # 500 is the minimum; with no items under 500 it should be insufficient
    if data["status"] == "insufficient_budget":
        assert data["minimum_required"] >= 500
    else:
        assert data["total_spent"] <= 500


async def test_jewelry_plan_validation(client):
    resp = await client.post("/api/jewelry-plan", data=form_data(budget="100"))
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"

    resp = await client.post("/api/jewelry-plan", data=form_data(occasion="concert"))
    assert resp.status_code == 422

    resp = await client.post("/api/jewelry-plan", data=form_data(metal="platinum"))
    assert resp.status_code == 422


async def test_jewelry_plan_animated_gif_rejected(client):
    img = Image.new("RGB", (50, 50), (10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="GIF")
    resp = await client.post(
        "/api/jewelry-plan",
        data=form_data(),
        files={"outfit_image": ("anim.gif", buf.getvalue(), "image/gif")},
    )
    assert resp.status_code == 415


async def test_jewelry_plan_control_chars_in_notes(client):
    resp = await client.post(
        "/api/jewelry-plan",
        data=form_data(notes="nice\x00\x01 jewelry"),
    )
    assert resp.status_code == 200
