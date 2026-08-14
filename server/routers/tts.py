"""TTS 路由：POST /tts —— 用 edge-tts 生成语音。

接收文本，返回 audio/mpeg 格式的 MP3 音频流。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import edge_tts
from loguru import logger

from models.schemas import TTSRequest
from config import settings

router = APIRouter()


async def _tts_stream(text: str, voice: str, rate: str, volume: str):
    """edge-tts 异步生成器：逐块 yield MP3 数据。"""
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


@router.post("/tts")
async def tts(req: TTSRequest) -> StreamingResponse:
    """语音合成接口，返回 MP3 音频流。"""
    voice = req.voice or settings.TTS_VOICE
    rate = req.rate or settings.TTS_RATE
    volume = req.volume or settings.TTS_VOLUME

    try:
        # 预校验：edge-tts 需要文本非空（已由 Pydantic 校验保证）
        logger.info("TTS 请求 voice={} rate={} text_len={}", voice, rate, len(req.text))
        return StreamingResponse(
            _tts_stream(req.text, voice, rate, volume),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=tts.mp3",
                "Cache-Control": "no-cache",
            },
        )
    except Exception as e:
        logger.error("TTS 失败: {}", e)
        raise HTTPException(status_code=500, detail=f"语音合成失败: {e}")
