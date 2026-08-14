"""ASR 语音识别路由：接收客户端音频，返回识别文本。

端点设计：
  POST /api/asr          - 上传 WAV 音频，返回识别文本
  GET  /api/asr/status   - 查询 ASR 服务状态和后端信息

先粗后精 ASR 流程：
  1. 客户端 Vosk 离线识别 → 即时返回粗略结果（毫秒级）
  2. 客户端将同一段音频上传到本端点 → 精细识别（秒级）
  3. 客户端用精细结果替换粗略结果，提升准确度
"""

import io
import wave
from fastapi import APIRouter, File, UploadFile, HTTPException
from loguru import logger

from config import settings
from models.schemas import AsrResponse
from services.asr_service import get_asr_service

router = APIRouter()


@router.post("/asr", response_model=AsrResponse)
async def recognize_speech(
    file: UploadFile = File(..., description="WAV 音频文件 (16kHz, mono, 16-bit PCM)"),
    language: str = "zh",
):
    """在线语音识别（精细识别）。

    接收客户端上传的 WAV 音频，调用配置的 ASR 后端进行识别。

    请求示例（multipart/form-data）:
        curl -X POST http://localhost:8000/api/asr \
             -F "file=@audio.wav" \
             -F "language=zh"

    返回:
        {"text": "你好世界", "backend": "simple", "duration_ms": 0}
    """
    # 1. 读取音频数据
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音频数据为空")

    logger.info("收到 ASR 请求, 文件大小={} bytes, language={}", len(audio_bytes), language)

    # 2. 验证 WAV 格式
    try:
        wav_info = _parse_wav_header(audio_bytes)
        logger.debug(
            "WAV 信息: sample_rate={}, channels={}, duration={:.2f}s",
            wav_info["sample_rate"],
            wav_info["channels"],
            wav_info["duration"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无效的 WAV 文件: {e}")

    # 3. 调用 ASR 服务识别
    import time
    start_time = time.time()
    try:
        asr_service = get_asr_service()
        text = await asr_service.recognize(audio_bytes, language=language)
        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "ASR 识别完成, backend={}, 耗时={}ms, 结果='{}'",
            asr_service.backend_name,
            duration_ms,
            text[:50] if text else "(空)",
        )

        return AsrResponse(
            text=text,
            backend=asr_service.backend_name,
            duration_ms=duration_ms,
        )
    except Exception as e:
        logger.error("ASR 识别异常: {}", e)
        return AsrResponse(
            text="",
            backend=settings.ASR_BACKEND,
            duration_ms=0,
        )


@router.get("/asr/status")
async def asr_status():
    """查询 ASR 服务状态。

    返回当前配置的 ASR 后端和可用状态，供客户端判断是否启用在线 ASR。
    """
    return {
        "backend": settings.ASR_BACKEND,
        "available": True,
        "timeout": settings.ASR_TIMEOUT,
    }


def _parse_wav_header(wav_bytes: bytes) -> dict:
    """解析 WAV 文件头，返回采样率、声道数、时长等信息。

    WAV 文件结构（PCM）:
      RIFF header (12 bytes)
      fmt chunk (24+ bytes)
      data chunk (8 bytes header + audio data)
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        return {
            "sample_rate": wav_file.getframerate(),
            "channels": wav_file.getnchannels(),
            "sample_width": wav_file.getsampwidth(),
            "frames": wav_file.getnframes(),
            "duration": wav_file.getnframes() / wav_file.getframerate(),
        }
