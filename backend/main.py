"""FastAPI entry point for CivicAI.

Start the server with:  uvicorn backend.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1.router import api_router
from backend.core.config import settings
from backend.db.init_db import init_db

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the database tables when the server starts."""
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="An AI-Powered Intelligent Citizen Service Platform for Government Offices.",
    lifespan=lifespan,
)

# The Streamlit frontend runs on a different port, so it needs CORS access.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [settings.backend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=API_PREFIX)


@app.get("/", tags=["root"])
def root() -> dict:
    """Simple landing response so the base URL is not empty."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "api": API_PREFIX,
    }
