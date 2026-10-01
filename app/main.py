"""App factory, middleware, routers, and error handlers."""

import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.routers import health, home_plan, pages, party_plan, jewelry_plan
from app.services.formatting import format_inr
from app.services.gemini import (
    AIAuthError,
    AINotConfiguredError,
    AIUnavailableError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

CHARTJS_CDN = "https://cdn.jsdelivr.net"

CSP = (
    "default-src 'self'; "
    f"script-src 'self' {CHARTJS_CDN}; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class RateLimiter:
    """In-memory sliding-window rate limiter (per IP)."""

    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self.windows: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        window = self.windows[key]
        cutoff = now - 60.0
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= self.limit:
            retry_after = int(60.0 - (now - window[0])) + 1
            return False, max(1, retry_after)
        window.append(now)
        return True, 0


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PocketSmart AI",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
    )

    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    templates = Jinja2Templates(directory="app/templates")
    templates.env.filters["inr"] = format_inr

    rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = CSP
        return response

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.method == "POST" and request.url.path.startswith("/api/"):
            client_ip = request.client.host if request.client else "unknown"
            allowed, retry_after = rate_limiter.is_allowed(client_ip)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "Too many requests. Please wait a minute and try again.",
                            "fields": {},
                        }
                    },
                )
        return await call_next(request)

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------

    def error_response(code: str, message: str, fields: dict[str, str] | None = None, status: int = 400):
        return JSONResponse(
            status_code=status,
            content={"error": {"code": code, "message": message, "fields": fields or {}}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "header", "path", "cookie")]
            key = ".".join(loc) if loc else "input"
            fields[key] = err.get("msg", "Invalid value")
        message = "Please fix the highlighted fields and try again."
        if request.url.path.startswith("/api/"):
            return error_response("VALIDATION_ERROR", message, fields, status=422)
        return HTMLResponse(
            content=f"<h1>Invalid input</h1><p>{message}</p>",
            status_code=422,
        )

    @app.exception_handler(AINotConfiguredError)
    async def ai_not_configured_handler(request: Request, exc: AINotConfiguredError):
        return error_response("AI_NOT_CONFIGURED", str(exc), status=503)

    @app.exception_handler(AIUnavailableError)
    async def ai_unavailable_handler(request: Request, exc: AIUnavailableError):
        return error_response("AI_UNAVAILABLE", str(exc), status=503)

    @app.exception_handler(AIAuthError)
    async def ai_auth_handler(request: Request, exc: AIAuthError):
        return error_response("AI_UNAVAILABLE", str(exc), status=503)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            if request.url.path.startswith("/api/"):
                return error_response("NOT_FOUND", "The requested resource was not found.", status=404)
            return templates.TemplateResponse(request, "404.html", {"title": "Page not found"}, status_code=404)
        if exc.status_code == 413:
            return error_response("PAYLOAD_TOO_LARGE", "The request payload is too large.", status=413)
        if exc.status_code == 415:
            return error_response("UNSUPPORTED_MEDIA", "The uploaded media type is not supported.", status=415)
        return error_response("INTERNAL_ERROR", "Something went wrong on our side.", status=exc.status_code)

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(
            "INTERNAL_ERROR",
            "Something went wrong on our side. Please try again later.",
            status=500,
        )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------

    app.include_router(pages.router)
    app.include_router(health.router)
    app.include_router(home_plan.router)
    app.include_router(party_plan.router)
    app.include_router(jewelry_plan.router)

    return app


app = create_app()
