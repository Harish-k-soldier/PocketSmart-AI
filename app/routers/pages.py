"""HTML page routes (Jinja2, server-rendered)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings, get_settings
from app.services import catalog as catalog_svc

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home_page(request: Request):
    return templates.TemplateResponse(request, "home.html", {"title": "PocketSmart AI"})


@router.get("/home-planner", response_class=HTMLResponse, include_in_schema=False)
def home_planner_page(request: Request):
    return templates.TemplateResponse(request, "home_planner.html", {"title": "Home Budget Planner"})


@router.get("/party-planner", response_class=HTMLResponse, include_in_schema=False)
def party_planner_page(request: Request):
    return templates.TemplateResponse(request, "party_planner.html", {"title": "Party Planner"})


@router.get("/jewelry-planner", response_class=HTMLResponse, include_in_schema=False)
def jewelry_planner_page(request: Request, settings: Settings = Depends(get_settings)):
    cities = catalog_svc.cities()
    return templates.TemplateResponse(
        request, "jewelry_planner.html", {"title": "Jewelry Budget Planner", "cities": cities}
    )
