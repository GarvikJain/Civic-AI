"""Small schemas shared by several modules."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Answer of the /health endpoint."""

    status: str
    app_name: str
    version: str


class MessageResponse(BaseModel):
    """Generic message, used by the module placeholder endpoints."""

    module: str
    status: str
    message: str
