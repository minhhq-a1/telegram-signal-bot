from fastapi import APIRouter
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str

@router.get("/api/v1/health", response_model=HealthResponse)
def get_health():
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version
    )
