from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, analyze, workflow
from app.core.database import engine, Base
import app.models.db  # noqa: F401 — registers ORM models with Base before create_all


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create all database tables on startup if they don't already exist."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AI Browser Assist API",
    version="0.1.0",
    description="Backend for the AI Browser Workflow Assistant Chrome extension.",
    lifespan=lifespan,
)

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
