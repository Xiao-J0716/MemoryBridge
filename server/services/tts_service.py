"""TTS 服务：edge-tts 在线合成 + pyttsx3 离线降级。

降级链：
  1. edge-tts（在线，音质好，流式 MP3）
  2. 重试 TTS_EDGE_RETRY 次
  3. pyttsx3（离线 SAPI5，WAV → pydub 转 MP3）

无论哪一环成功，都返回 MP3 字节流。
调用方可通过返回的 engine 字段知道用了哪个引擎。
"""

from typing import AsyncGenerator
import asyncio
import io
import tempfile
import os

import edge_tts
from loguru import logger

from config import settings


async def edge_tts_stream(
    text: str, voice: str, rate: str, volume: str
) -> AsyncGenerator[bytes, None]:
    """edge-tts 流式生成器：逐块 yield MP3 数据。"""
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


async def edge_tts_bytes(
    text: str, voice: str, rate: str, volume: str, retries: int = 1
) -> bytes:
    """edge-tts 一次性收集所有 MP3 数据（含重试）。

    重试逻辑：第一次失败后，如果 retries > 0，等待 1 秒再试一次。
    全部失败则抛出异常，由上层捕获并降级。
    """
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            buf = io.BytesIO()
            async for chunk in edge_tts_stream(text, voice, rate, volume):
                buf.write(chunk)
            data = buf.getvalue()
            if not data:
                raise RuntimeError("edge-tts 返回空数据")
            logger.info(
                "edge-tts 成功 attempt={} voice={} bytes={}", attempt, voice, len(data)
            )
            return data
        except Exception as e:
            last_error = e
            logger.warning(
                "edge-tts 失败 attempt={}/{} error={}: {}",
                attempt, retries, type(e).__name__, e,
            )
            if attempt < retries:
                await asyncio.sleep(1)
    raise RuntimeError(f"edge-tts 重试 {retries} 次后仍失败: {last_error}")


def pyttsx3_to_mp3(
    text: str,
    voice_id: str,
    rate: int,
    volume: float,
    bitrate: str,
) -> bytes:
    """pyttsx3 离线合成 → WAV → pydub 转 MP3。

    同步阻塞调用（SAPI5 本身是同步的），在 async 上下文中应放到线程池执行。
    """
    from pydub import AudioSegment
    import pyttsx3

    tmp_wav = tempfile.mktemp(suffix=".wav")
    tmp_mp3 = tempfile.mktemp(suffix=".mp3")
    try:
        engine = pyttsx3.init()
        # 设置语音
        voices = engine.getProperty("voices")
        for v in voices:
            if v.id == voice_id:
                engine.setProperty("voice", v.id)
                break
        # 语速（pyttsx3 默认 200 WPM）
        engine.setProperty("rate", rate)
        # 音量（0.0~1.0）
        engine.setProperty("volume", volume)

        engine.save_to_file(text, tmp_wav)
        engine.runAndWait()
        engine.stop()

        if not os.path.exists(tmp_wav) or os.path.getsize(tmp_wav) == 0:
            raise RuntimeError("pyttsx3 生成的 WAV 为空")

        # WAV → MP3
        audio = AudioSegment.from_wav(tmp_wav)
        buf = io.BytesIO()
        audio.export(buf, format="mp3", bitrate=bitrate)
        mp3_data = buf.getvalue()

        logger.info(
            "pyttsx3 离线合成成功 voice={} wav_bytes={} mp3_bytes={}",
            voice_id, os.path.getsize(tmp_wav), len(mp3_data),
        )
        return mp3_data
    finally:
        for f in (tmp_wav, tmp_mp3):
            try:
                os.unlink(f)
            except OSError:
                pass


async def tts_synthesize(
    text: str, voice: str, rate: str, volume: str
) -> tuple[bytes, str]:
    """TTS 合成入口：edge-tts 优先，失败降级到 pyttsx3 离线。

    Returns:
        (mp3_bytes, engine_name) — engine_name 为 "edge" 或 "offline"
    """
    # 1. 尝试 edge-tts（在线）
    edge_err: Exception | None = None
    try:
        mp3_data = await edge_tts_bytes(
            text, voice, rate, volume, retries=settings.TTS_EDGE_RETRY
        )
        return mp3_data, "edge"
    except Exception as e:
        edge_err = e
        logger.error("edge-tts 不可用，降级到离线 TTS: {}", e)

    # 2. 降级到 pyttsx3（离线，同步阻塞，放到线程池）
    try:
        loop = asyncio.get_event_loop()
        mp3_data = await loop.run_in_executor(
            None,
            pyttsx3_to_mp3,
            text,
            settings.TTS_OFFLINE_VOICE,
            settings.TTS_OFFLINE_RATE,
            settings.TTS_OFFLINE_VOLUME,
            settings.TTS_OFFLINE_BITRATE,
        )
        return mp3_data, "offline"
    except Exception as offline_err:
        logger.error("离线 TTS 也失败: {}", offline_err)
        raise RuntimeError(
            f"所有 TTS 引擎均失败。edge: {edge_err}; offline: {offline_err}"
        )
