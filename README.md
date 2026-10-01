# PocketSmart AI

GenAI-powered, budget-based recommendation web app for India. Pick a planner, enter a budget and preferences, and get curated product or service recommendations from popular Indian platforms — Amazon, Flipkart, IKEA, Swiggy, Zomato, and OYO — all within your budget. Currency is always INR (₹).

## Features

- **Home Budget Planner** — room-wise interior shopping plan. Your budget is split room-by-room (largest-remainder, integer math), a 5% contingency is always kept aside, and each room/category gets 2–3 catalog options with a recommended pick.
- **Party Planner** — proportional event budget across catering, decoration, entertainment, and (optional) stay. Allocation adjusts for event type, outdoor venues, long durations, and travelling guests. Includes a Chart.js doughnut chart with a table fallback.
- **Jewelry Budget Planner** — occasion and outfit-aware jewelry suggestions. Optionally upload a photo of your outfit; the app extracts the dominant colour palette and coordinates the jewelry to it.
- **Deterministic and safe** — Python does all arithmetic; the AI only picks catalog IDs and writes short reasons. Every plan is whitelist-validated against the catalog and guaranteed to stay within budget (or returns `insufficient_budget` with the minimum required amount).
- **Graceful fallback** — if the AI service is unavailable, a deterministic selector still builds a valid plan (`ai_used: false`, with a notice). The user never sees a blank screen or stack trace.
- **Mobile-first, responsive UI** — 320px to 1280px+, keyboard accessible, `prefers-reduced-motion` support, print-friendly.

## Architecture

```
┌────────────┐   HTTP    ┌──────────────────────────────────────────┐
│  Browser   │ ◄───────► │  FastAPI (app/main.py)                   │
│  HTML/CSS/ │  JSON /   │  ├─ middleware: security headers,        │
│  vanilla JS│  multipart│  │  │  per-IP rate limiter (POST /api/*)  │
└────────────┘           │  ├─ error handlers → error contract      │
                         │  └─ routers/                              │
                         │     ├─ pages.py        (HTML, Jinja2)     │
                         │     ├─ home_plan.py    (POST /api/…)     │
                         │     ├─ party_plan.py   (POST /api/…)     │
                         │     ├─ jewelry_plan.py (POST /api/…)     │
                         │     └─ health.py       (GET  /api/health)│
                         └──────────────────────────────────────────┘
                                      │
                         ┌────────────▼─────────────────────────────┐
                         │  services/                                │
                         │  ├─ planners.py   orchestration + guard   │
                         │  ├─ budget.py     largest-remainder math │
                         │  ├─ catalog.py    load/index/filter JSON  │
                         │  ├─ gemini.py     Gemini SDK + retries   │
                         │  ├─ mock_ai.py    offline selector        │
                         │  ├─ fallback.py   deterministic selection │
                         │  └─ formatting.py INR (lakh/crore)        │
                         └────────────┬─────────────────────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │  data/catalog.json        │  ← single source
                         │  (109 items, 6 platforms) │     of truth
                         └───────────────────────────┘
```

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
```

### Getting a Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/apikey).
2. Click **Create API key** and copy it.
3. Paste it into `.env` as `GEMINI_API_KEY=your-key-here`.

The key is read only by the server. It is never logged, never sent to the browser, and never appears in rendered HTML.

## Running

```bash
# Start the app (development, auto-reload)
uvicorn app.main:app --reload

# Or without auto-reload
uvicorn app.main:app
```

Then open http://127.0.0.1:8000

### Mock mode (no API key needed)

```bash
USE_MOCK_AI=true uvicorn app.main:app --reload
```

In mock mode the app uses a built-in offline selector instead of Gemini, so the whole app is demo-able and testable without a key. Set `USE_MOCK_AI=false` (and provide `GEMINI_API_KEY`) to use the real model.

## Tests

```bash
pytest -q
```

The suite runs with the Gemini service mocked (and a `USE_MOCK_AI=true` path), covering formatting, budget math, the catalog, all three APIs, the Gemini service, and the pages.

## Catalog validation

```bash
python scripts/validate_catalog.py
```

Exits non-zero with clear messages if any item is malformed, duplicated, or missing required coverage.

## Routes

| Route | What it shows (screenshot-ready) |
|---|---|
| `/` | Hero + three planner cards linking to each planner. |
| `/home-planner` | Budget input, style radio cards, room chips, adaptive per-room quantity fields, notes, "Build my plan". |
| `/party-planner` | Budget, guests, event type, venue, city, duration, travelling toggle (reveals stay fields), notes. |
| `/jewelry-planner` | Budget, occasion, style, metal, stone, outfit-image dropzone with preview, notes. |
| `/api/home-plan` | JSON home plan (see below). |
| `/api/party-plan` | JSON party plan. |
| `/api/jewelry-plan` | JSON jewelry plan (multipart, optional image). |
| `/api/health` | `{status, model, ai_configured, mock}` — never the key. |
| `/docs` | Interactive OpenAPI docs. |

## API examples

### POST /api/home-plan

```bash
curl -X POST http://127.0.0.1:8000/api/home-plan \
  -H "Content-Type: application/json" \
  -d '{
    "budget": 150000,
    "style": "modern",
    "notes": "",
    "rooms": [
      {"name": "living_room", "items": {"lights": 3, "ceiling_fans": 1, "sofas": 1}},
      {"name": "bedroom", "items": {"beds": 1, "wardrobes": 1}}
    ]
  }'
```

Response (abridged):

```json
{
  "status": "ok", "ai_used": true, "notice": null,
  "budget_total": 150000, "contingency": 7500,
  "total_spent": 65993, "remaining": 84007, "percent_used": 44.0,
  "currency": "INR",
  "rooms": [
    {
      "room": "living_room", "label": "Living Room",
      "room_budget": 91250, "room_spent": 35995,
      "items": [
        {
          "category": "lights", "label": "Lights", "quantity": 3,
          "unit_ceiling": 10115, "recommended_id": "IKEA-LIGHT-001",
          "options": [
            {"id": "IKEA-LIGHT-001", "name": "ALANG LED Floor Lamp", "platform": "IKEA",
             "unit_price": 2499, "line_total": 7497, "image": "/static/img/placeholder.svg",
             "url": "https://www.ikea.com/in/en/search/products/?q=floor+lamp",
             "reason": "...", "is_recommended": true}
          ],
          "unavailable": false
        }
      ]
    }
  ]
}
```

### POST /api/party-plan

```bash
curl -X POST http://127.0.0.1:8000/api/party-plan \
  -H "Content-Type: application/json" \
  -d '{
    "budget": 150000, "guests": 100, "event_type": "wedding",
    "venue_type": "indoor", "city": "any", "duration_hours": 4,
    "guests_travelling": false, "notes": ""
  }'
```

Response (abridged):

```json
{
  "status": "ok", "ai_used": true, "notice": null,
  "budget_total": 150000, "contingency": 7500,
  "total_spent": 39898, "remaining": 110102, "percent_used": 26.6,
  "currency": "INR", "per_guest_cost": 399,
  "event_type": "wedding", "guests": 100,
  "allocation": [
    {"category": "catering", "label": "Catering", "percent": 45.0, "amount": 67500, "spent": 14900,
     "options": [{"id": "SWIGGY-CATER-001", "name": "Veg Thali Catering (Per Plate)",
                  "platform": "Swiggy", "unit_price": 149, "price_unit": "per_plate",
                  "total_cost": 14900, "reason": "...", "url": "https://www.swiggy.com/",
                  "image": "/static/img/placeholder.svg", "is_recommended": true}]}
  ]
}
```

### POST /api/jewelry-plan

```bash
curl -X POST http://127.0.0.1:8000/api/jewelry-plan \
  -F "budget=10000" -F "occasion=wedding" -F "style=traditional" \
  -F "metal=no_preference" -F "stone=no_preference" \
  -F "outfit_image=@/path/to/outfit.jpg;type=image/jpeg"
```

Response (abridged):

```json
{
  "status": "ok", "ai_used": true, "notice": null,
  "budget_total": 10000, "total_spent": 6996, "remaining": 3004,
  "percent_used": 70.0, "currency": "INR",
  "palette": [{"hex": "#B22222", "name": "crimson red"}],
  "outfit_summary": "saree traditional v-neck",
  "recommendations": [
    {"id": "FLIPKART-JEWEL-003", "name": "Gold-Plated Bangles Set (6-Piece)",
     "platform": "Flipkart", "price": 1199, "image": "/static/img/placeholder.svg",
     "url": "https://www.flipkart.com/search?q=gold+plated+bangles+set",
     "colors": ["#D4AF37", "#FF0000"], "why_it_matches": "...", "match_score": 70}
  ]
}
```

### Error contract

All `/api/*` errors return:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Human-friendly text", "fields": { "budget": "Must be at least ₹5,000" } } }
```

Codes: `VALIDATION_ERROR` (422), `AI_NOT_CONFIGURED` (503), `AI_UNAVAILABLE` (503), `RATE_LIMITED` (429), `PAYLOAD_TOO_LARGE` (413), `UNSUPPORTED_MEDIA` (415), `INTERNAL_ERROR` (500).

## Model name note

The brief mentions "Gemini 1.5 Flash", but the older 1.5 models are retired. The model is therefore read from the `GEMINI_MODEL` env var (default `gemini-2.5-flash`) and can be swapped freely with no code changes. The model name appears only in the settings default — never hard-coded elsewhere.

## JS `formatINR` manual check

`PS.formatINR` in `static/js/common.js` mirrors the Python `format_inr`. Verify in the browser console:

| Input | Expected |
|---|---|
| `1234` | `₹1,234` |
| `100000` | `₹1,00,000` |
| `12345678` | `₹1,23,45,678` |
| `0` | `₹0` |
| `-5000` | `-₹5,000` |
| `null` | `₹0` |
| `NaN` | `₹0` |
| `"abc"` | `₹0` |

## Manual / visual checks

- [ ] Layouts at 320px, 768px, and 1280px widths (no horizontal scroll at 320px).
- [ ] Keyboard-only navigation through every form and results view.
- [ ] Print preview (nav, buttons, and forms hidden; clean one-page layout).
- [ ] Chart.js blocked → the allocation table still renders, no console errors.
- [ ] Long product names wrap without breaking the option cards.
- [ ] Missing image → `<img>` falls back to `placeholder.svg`.

## Troubleshooting

- **"AI service is not configured" (503)** — set `GEMINI_API_KEY` in `.env`, or set `USE_MOCK_AI=true` for offline mode.
- **Gemini calls time out** — increase `AI_TIMEOUT_SECONDS`. The app retries once (`AI_MAX_RETRIES`) and then falls back to deterministic suggestions.
- **Rate limited (429)** — you've exceeded `RATE_LIMIT_PER_MINUTE` POST requests per minute from one IP. Wait and retry.
- **Image rejected (415)** — only JPEG/PNG/WebP are allowed, and the file must be a real image (verified with Pillow).
- **Image too large (413)** — the upload exceeds `MAX_UPLOAD_MB` (default 5 MB).
- **Catalog invalid** — run `python scripts/validate_catalog.py` and fix the reported items.
- **Port already in use** — change the port: `uvicorn app.main:app --port 8001`.

## Known limitations

- The catalog is representative mock data; prices are indicative Indian-market prices, not live. Product links point to platform homepages or search pages, not live product pages.
- The mock AI (`USE_MOCK_AI=true`) picks the first N candidates and is not a real recommendation engine — it exists for demos and tests.
- The outfit-image analysis depends on the Gemini multimodal model; if it fails, the app continues without colour coordination (with a notice).
- No database or accounts — plans are not persisted server-side. "Save" is client-side (print / clipboard).
- The rate limiter is in-memory and resets on restart (single-process only).
