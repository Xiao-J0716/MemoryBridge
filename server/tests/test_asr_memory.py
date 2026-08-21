"""测试 GET /api/asr/status 和 GET /api/memory/query 端点。"""

import pytest
from unittest.mock import AsyncMock, patch


# ---------- /api/asr/status ----------

@pytest.mark.asyncio
async def test_asr_status(client):
    """GET /api/asr/status 应返回 backend + available + timeout。"""
    resp = await client.get("/api/asr/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "backend" in data
    assert "available" in data
    assert "timeout" in data
    assert data["available"] is True


# ---------- /api/memory/query ----------

@pytest.mark.asyncio
async def test_memory_query_empty(client):
    """无记忆时返回空列表。"""
    with patch("routers.memory.MemoryService") as MockMemorySvc:
        MockMemorySvc.return_value.search_memories = AsyncMock(return_value=[])
        resp = await client.get("/api/memory/query", params={
            "user_id": 1,
            "query": "奶奶叫什么",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_memory_query_with_results(client):
    """有记忆时返回带 score 的结果列表。"""
    with patch("routers.memory.MemoryService") as MockMemorySvc:
        MockMemorySvc.return_value.search_memories = AsyncMock(return_value=[
            {"content": "我叫张奶奶", "category": "family", "importance": 3, "score": 0.92},
            {"content": "我喜欢听戏曲", "category": "hobby", "importance": 2, "score": 0.78},
        ])
        resp = await client.get("/api/memory/query", params={
            "user_id": 1,
            "query": "我叫什么名字",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["content"] == "我叫张奶奶"
    assert data[0]["score"] == 0.92
    assert data[1]["content"] == "我喜欢听戏曲"


@pytest.mark.asyncio
async def test_memory_query_missing_params(client):
    """缺少必填参数应返回 422。"""
    resp = await client.get("/api/memory/query", params={"user_id": 1})
    assert resp.status_code == 422
