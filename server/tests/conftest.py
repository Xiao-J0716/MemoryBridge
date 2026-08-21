"""pytest 全局配置：mock 外部依赖，让测试无需真实 DB/Redis/LLM。

策略：
- get_db 用 app.dependency_overrides（FastAPI 官方方式，不依赖 patch 时机）
- get_llm_service / get_session_service 用模块级 patch（路由内直接调用，非 Depends）
- tts_synthesize 用模块级 patch（路由内直接调用）
- 不清模块缓存——清了反而让 patch 失效
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value="你好呀，今天天气不错呢。")
    llm.embed = AsyncMock(return_value=[0.0] * 1024)
    llm.close = AsyncMock()
    return llm


@pytest.fixture
def mock_session_service():
    svc = AsyncMock()
    svc.get_context = AsyncMock(return_value=[])
    svc.add_round = AsyncMock()
    svc.add_message = AsyncMock()
    svc.clear_session = AsyncMock()
    svc.close = AsyncMock()
    return svc


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest_asyncio.fixture
async def client(mock_llm, mock_session_service, mock_db):
    """FastAPI TestClient，外部依赖全部 mock。"""
    from httpx import ASGITransport, AsyncClient
    from main import app
    from models.database import get_db

    # 1. 用 dependency_overrides 替换 get_db（FastAPI 官方方式）
    async def fake_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db

    # 2. 模块级 patch（路由内直接调用的函数，非 Depends）
    with (
        patch("routers.chat.get_llm_service", return_value=mock_llm),
        patch("routers.chat.get_session_service", return_value=mock_session_service),
        patch("routers.memory._get_llm_service", return_value=mock_llm),
        patch("routers.tts.tts_synthesize", return_value=(b"\xff\xfb\x90\x00" + b"\x00" * 100, "edge")),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()
