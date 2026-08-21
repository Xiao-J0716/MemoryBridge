"""FastAPI 应用入口：注册路由、CORS、生命周期事件。"""

from contextlib import asynccontextmanager
from loguru import logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.database import engine, Base
from routers import health, chat, tts, asr, memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表，关闭时释放连接池。"""
    logger.info("启动 {} v{}", settings.APP_NAME, settings.APP_VERSION)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表已就绪")
    except Exception as e:
        logger.warning("数据库连接失败，服务以无数据库模式启动: {}", e)
    yield
    await engine.dispose()
    logger.info("数据库连接池已释放，应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health.router, tags=["健康检查"])
app.include_router(chat.router, prefix="/api", tags=["对话"])
app.include_router(tts.router, prefix="/api", tags=["语音合成"])
app.include_router(asr.router, prefix="/api", tags=["语音识别"])
app.include_router(memory.router, prefix="/api", tags=["记忆"])
