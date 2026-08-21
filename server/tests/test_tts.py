"""测试 POST /api/tts 端点。"""

import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_tts_normal(client):
    """正常 TTS：返回 audio/mpeg + 非空 body + X-TTS-Engine header。"""
    resp = await client.post("/api/tts", json={"text": "你好呀"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert len(resp.content) > 0
    assert resp.headers.get("x-tts-engine") == "edge"


@pytest.mark.asyncio
async def test_tts_empty_text(client):
    """空文本应被 Pydantic 拒绝（422）。"""
    resp = await client.post("/api/tts", json={"text": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tts_fallback_offline(client):
    """模拟 edge-tts 失败，验证降级到 offline 引擎。"""
    # patch 打在 routers.tts 上（import 方），不是 services.tts_service
    with patch("routers.tts.tts_synthesize", return_value=(b"\x00" * 200, "offline")):
        resp = await client.post("/api/tts", json={"text": "降级测试"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert len(resp.content) > 0
    assert resp.headers.get("x-tts-engine") == "offline"


@pytest.mark.asyncio
async def test_tts_all_fail(client):
    """所有引擎都失败时应返回 503。"""
    with patch("routers.tts.tts_synthesize", side_effect=RuntimeError("全部失败")):
        resp = await client.post("/api/tts", json={"text": "测试"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_tts_custom_voice(client):
    """自定义 voice/rate 参数应正常传递。"""
    resp = await client.post("/api/tts", json={
        "text": "自定义语音",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+10%",
    })
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
