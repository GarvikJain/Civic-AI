"""Collects every v1 route file into one router.

backend/main.py mounts this single router under /api/v1.
"""

from fastapi import APIRouter

from backend.api.v1.routes import (
    auth,
    documents,
    eligibility,
    feedback,
    health,
    officers,
    queue,
    regulations,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)

# The six CivicAI modules
api_router.include_router(regulations.router)
api_router.include_router(documents.router)
api_router.include_router(queue.router)
api_router.include_router(officers.router)
api_router.include_router(eligibility.router)
api_router.include_router(feedback.router)
