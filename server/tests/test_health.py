"""测试 GET /health 端点。"""

import pytest


@pytest.mark.asyncio
async def test_health(client):
    """GET /health 应返回 200，status=ok，含版本号和时间戳。"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_no_body(client):
    """GET /health 不需要请求体。"""
    resp = await client.get("/health")
    assert resp.status_code == 200
