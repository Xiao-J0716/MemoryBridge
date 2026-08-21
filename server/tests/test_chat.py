"""测试 POST /api/chat 端点。"""

import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_chat_normal(client, mock_llm):
    """正常对话：返回 reply + session_id + memories_used。"""
    resp = await client.post("/api/chat", json={
        "text": "你好",
        "user_id": 1,
        "session_id": "test-session-1",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert data["session_id"] == "test-session-1"
    assert "memories_used" in data
    # reply 应该来自 mock_llm.chat 的返回值
    assert len(data["reply"]) > 0
    # 验证 LLM 被调用
    mock_llm.chat.assert_called_once()


@pytest.mark.asyncio
async def test_chat_empty_text(client):
    """空文本应被 Pydantic 拒绝（422）。"""
    resp = await client.post("/api/chat", json={
        "text": "",
        "user_id": 1,
        "session_id": "test-session-2",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_missing_field(client):
    """缺少必填字段应返回 422。"""
    resp = await client.post("/api/chat", json={
        "text": "你好",
        # 缺少 user_id 和 session_id
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_llm_failure(client, mock_llm):
    """LLM 调用失败时应返回 500。"""
    mock_llm.chat = AsyncMock(side_effect=Exception("LLM 服务不可用"))
    resp = await client.post("/api/chat", json={
        "text": "你好",
        "user_id": 1,
        "session_id": "test-session-3",
    })
    assert resp.status_code == 500
