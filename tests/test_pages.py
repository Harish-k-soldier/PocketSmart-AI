


async def test_home_page(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Plan smart" in resp.text
    assert "Home Budget Planner" in resp.text
    assert "Party Planner" in resp.text
    assert "Jewelry Budget Planner" in resp.text


async def test_home_planner_page(client):
    resp = await client.get("/home-planner")
    assert resp.status_code == 200
    assert "Home Budget Planner" in resp.text
    assert "Build my plan" in resp.text


async def test_party_planner_page(client):
    resp = await client.get("/party-planner")
    assert resp.status_code == 200
    assert "Party Planner" in resp.text
    assert "Guest count" in resp.text


async def test_jewelry_planner_page(client):
    resp = await client.get("/jewelry-planner")
    assert resp.status_code == 200
    assert "Jewelry Budget Planner" in resp.text
    assert "Outfit image" in resp.text


async def test_404_page(client):
    resp = await client.get("/no-such-page")
    assert resp.status_code == 404
    assert "404" in resp.text
    assert "Page not found" in resp.text


async def test_404_api_returns_json(client):
    resp = await client.get("/api/no-such-endpoint")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "model" in data
    assert "ai_configured" in data
    assert "mock" in data
    assert "key" not in resp.text.lower() or "api_key" not in resp.text.lower()


async def test_api_key_never_in_html(client):
    test_key = "SECRET_TEST_KEY_12345"
    for path in ("/", "/home-planner", "/party-planner", "/jewelry-planner"):
        resp = await client.get(path)
        assert test_key not in resp.text


async def test_security_headers(client):
    resp = await client.get("/")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in resp.headers
