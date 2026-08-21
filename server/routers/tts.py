"""TTS 路由：POST /tts —— 语音合成，支持降级。

接收文本，返回 audio/mpeg 格式的 MP3 音频。
降级链：edge-tts（在线）→ pyttsx3（离线）→ 500 报错。
响应头 X-TTS-Engine 标注实际使用的引擎。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from loguru import logger

from models.schemas import TTSRequest
from config import settings
from services.tts_service import tts_synthesize

router = APIRouter()


@router.post("/tts")
async def tts(req: TTSRequest) -> Response:
    """语音合成接口，返回 MP3 音频。

    降级策略：edge-tts 失败时自动切到 pyttsx3 离线引擎。
    响应头 X-TTS-Engine 标明使用了哪个引擎（edge / offline）。
    """
    voice = req.voice or settings.TTS_VOICE
    rate = req.rate or settings.TTS_RATE
    volume = req.volume or settings.TTS_VOLUME

    logger.info("TTS 请求 voice={} rate={} text_len={}", voice, rate, len(req.text))

    try:
        mp3_data, engine = await tts_synthesize(req.text, voice, rate, volume)
        logger.info("TTS 完成 engine={} bytes={}", engine, len(mp3_data))
        return Response(
            content=mp3_data,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=tts.mp3",
                "Cache-Control": "no-cache",
                "X-TTS-Engine": engine,
            },
        )
    except Exception as e:
        logger.error("TTS 完全失败: {}", e)
        raise HTTPException(status_code=503, detail=f"语音合成失败，所有引擎不可用: {e}")
