from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, analyze, workflow, assist, cognitive, research, intelligence, unified, mission, mission_intelligence, tabs as tabs_router, trust as trust_router, browser as browser_router, decisions as decisions_router, approvals as approvals_router, governance as governance_router, authorization as authorization_router, runtime as runtime_router, plans as plans_router, gateway as gateway_router, website_intelligence as website_intelligence_router, certification as certification_router
from app.core.database import engine, Base
import app.models.db  # noqa: F401 — registers ORM models with Base before create_all


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create all database tables and warm up in-memory stores on startup."""
    Base.metadata.create_all(bind=engine)
    # V4.6: warm up unified task store from DB (no-op when persistence is disabled)
    from app.unified import store as _unified_store
    _unified_store.warmup()
    # V5.0: warm up mission store from DB (no-op when mission_persistence is disabled)
    from app.mission import restoration as _mission_restoration
    _mission_restoration.warmup()
    # V6.0: restore tab registry from snapshots (no-op when no snapshots exist)
    from app.tabs import restoration as _tab_restoration
    _tab_restoration.warmup()
    yield


app = FastAPI(
    title="AI Browser Assist API",
    version="0.1.0",
    description="Backend for the AI Browser Workflow Assistant Chrome extension.",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict:
    return {
        "service": "AI Browser Assist API",
        "health": "/health",
        "docs": "/docs",
        "endpoints": {
            "analyze": "POST /analyze",
            "workflow_log": "POST /workflow/log",
            "workflow_history": "GET /workflow/history",
            "workflow_analytics": "GET /workflow/{session_id}/analytics",
        },
    }


# Allow requests from Chrome extension pages (side panel, service worker).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(workflow.router)
app.include_router(assist.router)
app.include_router(cognitive.router)
app.include_router(research.router)
app.include_router(intelligence.router)
app.include_router(unified.router)
app.include_router(mission.router)
app.include_router(mission_intelligence.router, prefix="/mission")
app.include_router(tabs_router.router)
app.include_router(trust_router.router)
app.include_router(browser_router.router)
app.include_router(decisions_router.router)
app.include_router(approvals_router.router)
app.include_router(governance_router.router)
app.include_router(authorization_router.router)
app.include_router(runtime_router.router)
app.include_router(plans_router.router)
app.include_router(gateway_router.router)
app.include_router(website_intelligence_router.router)
app.include_router(certification_router.router)
