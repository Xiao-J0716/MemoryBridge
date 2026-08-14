"""健康检查路由。"""

from datetime import datetime
from fastapi import APIRouter
from models.schemas import HealthResponse
from config import settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查：返回服务状态与版本号。"""
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        timestamp=datetime.now(),
    )
