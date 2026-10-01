"""POST /api/jewelry-plan — Jewelry Budget Planner API (multipart, optional image)."""

import io
import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from PIL import Image

from app.config import Settings, get_settings
from app.models.common import ErrorBody, ErrorResponse, InsufficientBudgetBody
from app.models.jewelry import JewelryPlanRequest, JewelryPlanResponse
from app.services.gemini import AINotConfiguredError
from app.services.planners import build_jewelry_plan

log = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_LONG_SIDE_BEFORE_DOWNSCALE = 4096
MAX_LONG_SIDE_SENT = 1024


class PayloadTooLargeError(Exception):
    pass


class UnsupportedMediaError(Exception):
    pass


async def _read_upload(upload: UploadFile, settings: Settings) -> bytes:
    """Read the upload in memory with a hard cap; never touch the disk."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError(
                f"Image exceeds the {settings.max_upload_mb} MB limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_and_prepare_image(data: bytes, declared_mime: str, settings: Settings) -> tuple[bytes, str]:
    """Verify the bytes are a real image; downscale if huge. Returns (bytes, mime)."""
    if not data:
        raise UnsupportedMediaError("The uploaded file is empty.")
    if declared_mime not in ALLOWED_IMAGE_MIME:
        raise UnsupportedMediaError(
            "Only JPEG, PNG, or WebP images are allowed."
        )
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception as exc:
        raise UnsupportedMediaError("The file is not a valid image.") from exc

    # Re-open after verify() (verify leaves the object unusable).
    img = Image.open(io.BytesIO(data))
    img.load()
    if (img.format or "").upper() == "GIF":
        raise UnsupportedMediaError("Animated GIFs are not supported. Please upload a JPEG, PNG, or WebP image.")
    long_side = max(img.size)
    if long_side > MAX_LONG_SIDE_BEFORE_DOWNSCALE:
        raise UnsupportedMediaError(
            "Image is too large. Please upload an image under 4096 px on the long side."
        )
    if long_side > MAX_LONG_SIDE_SENT:
        scale = MAX_LONG_SIDE_SENT / long_side
        new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        img = img.convert("RGB")
        img = img.resize(new_size, Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue(), "image/jpeg"
    return data, declared_mime


@router.post(
    "/api/jewelry-plan",
    response_model=JewelryPlanResponse | InsufficientBudgetBody,
)
async def jewelry_plan(
    request: Request,
    settings: Settings = Depends(get_settings),
    budget: int = Form(...),
    occasion: str = Form("wedding"),
    style: str = Form("traditional"),
    metal: str = Form("no_preference"),
    stone: str = Form("no_preference"),
    notes: str = Form(""),
    outfit_image: UploadFile | None = File(default=None),
):
    if not settings.ai_configured:
        raise AINotConfiguredError(
            "AI service is not configured. Set GEMINI_API_KEY or enable USE_MOCK_AI."
        )

    image_bytes: bytes | None = None
    image_mime: str | None = None
    if outfit_image is not None and outfit_image.filename:
        declared = (outfit_image.content_type or "").lower()
        try:
            raw = await _read_upload(outfit_image, settings)
            image_bytes, image_mime = _validate_and_prepare_image(raw, declared, settings)
        except PayloadTooLargeError as exc:
            return JSONResponse(
                status_code=413,
                content=ErrorResponse(
                    error=ErrorBody(code="PAYLOAD_TOO_LARGE", message=str(exc))
                ).model_dump(),
            )
        except UnsupportedMediaError as exc:
            return JSONResponse(
                status_code=415,
                content=ErrorResponse(
                    error=ErrorBody(code="UNSUPPORTED_MEDIA", message=str(exc))
                ).model_dump(),
            )

    try:
        plan_request = JewelryPlanRequest(
            budget=budget,
            occasion=occasion,
            style=style,
            metal=metal,
            stone=stone,
            notes=notes,
        )
    except ValidationError as exc:
        fields = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", [])]
            fields[".".join(loc) or "input"] = err.get("msg", "Invalid value")
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error=ErrorBody(code="VALIDATION_ERROR", message="Please fix the highlighted fields and try again.", fields=fields)
            ).model_dump(),
        )
    return await build_jewelry_plan(plan_request, settings, image_bytes, image_mime)
