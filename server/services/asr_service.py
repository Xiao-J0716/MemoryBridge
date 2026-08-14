"""ASR 语音识别服务：支持 FunASR / Whisper / Simple 三种后端。

架构设计：
  - BaseAsrService: 抽象基类，统一 recognize 接口
  - FunAsrService: 阿里达摩院 FunASR，中文识别精度最高
  - WhisperService: OpenAI Whisper (faster-whisper)，多语言
  - SimpleAsrService: speech_recognition + Google Web API，零配置快速测试

音频输入格式：WAV (16kHz, mono, 16-bit PCM)，与客户端 AudioRecorder 一致
"""

import io
import tempfile
import asyncio
from abc import ABC, abstractmethod
from typing import Optional
from loguru import logger

from config import settings


class BaseAsrService(ABC):
    """ASR 服务抽象基类。"""

    @abstractmethod
    async def recognize(self, audio_wav: bytes, language: str = "zh") -> str:
        """识别 WAV 音频数据，返回文本。

        Args:
            audio_wav: WAV 格式音频字节数据（16kHz, mono, 16-bit PCM）
            language: 语言代码，默认中文 "zh"

        Returns:
            识别出的文本，识别失败返回空字符串
        """
        ...

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """后端名称（用于日志和调试）。"""
        ...


class SimpleAsrService(BaseAsrService):
    """简易 ASR：使用 speech_recognition 库 + Google Web Speech API。

    特点：
    - 零配置，无需下载模型，适合快速验证流程
    - 需要外网访问 Google 服务
    - 识别精度中等，延迟较高
    """

    def __init__(self):
        import speech_recognition as sr
        self._sr = sr
        logger.info("SimpleAsrService 初始化完成（Google Web Speech API）")

    @property
    def backend_name(self) -> str:
        return "simple"

    async def recognize(self, audio_wav: bytes, language: str = "zh") -> str:
        def _recognize():
            # speech_recognition 是同步库，在线程池中执行
            recognizer = self._sr.Recognizer()
            audio_file = io.BytesIO(audio_wav)
            with self._sr.AudioFile(audio_file) as source:
                audio_data = recognizer.record(source)
            # Google API 语言代码映射
            lang_map = {"zh": "zh-CN", "en": "en-US", "ja": "ja-JP"}
            google_lang = lang_map.get(language, "zh-CN")
            text = recognizer.recognize_google(audio_data, language=google_lang)
            return text

        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_recognize),
                timeout=settings.ASR_TIMEOUT,
            )
            logger.info("SimpleAsr 识别成功: {}", text[:50])
            return text
        except asyncio.TimeoutError:
            logger.warning("SimpleAsr 识别超时")
            return ""
        except Exception as e:
            logger.error("SimpleAsr 识别失败: {}", e)
            return ""


class WhisperService(BaseAsrService):
    """Whisper ASR：使用 faster-whisper 实现。

    特点：
    - 多语言支持（100+ 语言）
    - 可在 CPU 上运行（small 及以下模型）
    - 需要下载模型（small 约 480MB）
    - 识别精度高，支持标点和时间戳
    """

    def __init__(self):
        from faster_whisper import WhisperModel
        model_size = settings.ASR_WHISPER_MODEL
        device = settings.ASR_WHISPER_DEVICE
        # compute_type: int8 适合 CPU，float16 适合 GPU
        compute_type = "float16" if device == "cuda" else "int8"
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("WhisperService 初始化完成, model={}, device={}", model_size, device)

    @property
    def backend_name(self) -> str:
        return "whisper"

    async def recognize(self, audio_wav: bytes, language: str = "zh") -> str:
        def _recognize():
            # faster_whisper 接受文件路径，写入临时文件
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_wav)
                tmp_path = tmp.name
            try:
                # language=None 表示自动检测，指定则强制语言
                lang_code = language if language != "zh" else "zh"
                segments, _info = self._model.transcribe(
                    tmp_path,
                    language=lang_code,
                    beam_size=5,
                    vad_filter=True,  # 过滤静音段，提升速度
                )
                text = "".join(seg.text for seg in segments).strip()
                return text
            finally:
                import os
                os.unlink(tmp_path)

        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_recognize),
                timeout=settings.ASR_TIMEOUT,
            )
            logger.info("Whisper 识别成功: {}", text[:50])
            return text
        except asyncio.TimeoutError:
            logger.warning("Whisper 识别超时")
            return ""
        except Exception as e:
            logger.error("Whisper 识别失败: {}", e)
            return ""


class FunAsrService(BaseAsrService):
    """FunASR：阿里达摩院语音识别引擎。

    特点：
    - 中文识别精度最高（Paraformer 模型）
    - 支持标点恢复、热词、时间戳
    - 需要下载模型（paraformer-zh 约 300MB）
    - CPU 可运行，GPU 更快
    """

    def __init__(self):
        from funasr import AutoModel
        model_name = settings.ASR_FUNASR_MODEL
        self._model = AutoModel(
            model=model_name,
            # 同时加载标点恢复模型
            punc_model="ct-punc",
            # 输出带标点的文本
            disable_pbar=True,
        )
        logger.info("FunAsrService 初始化完成, model={}", model_name)

    @property
    def backend_name(self) -> str:
        return "funasr"

    async def recognize(self, audio_wav: bytes, language: str = "zh") -> str:
        def _recognize():
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_wav)
                tmp_path = tmp.name
            try:
                result = self._model.generate(
                    input=tmp_path,
                    batch_size_s=300,  # 批处理时长（秒）
                    is_final=True,
                )
                # FunASR 返回列表，每个元素含 "text" 字段
                if result and isinstance(result, list):
                    text = result[0].get("text", "").strip()
                    return text
                return ""
            finally:
                import os
                os.unlink(tmp_path)

        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_recognize),
                timeout=settings.ASR_TIMEOUT,
            )
            logger.info("FunAsr 识别成功: {}", text[:50])
            return text
        except asyncio.TimeoutError:
            logger.warning("FunAsr 识别超时")
            return ""
        except Exception as e:
            logger.error("FunAsr 识别失败: {}", e)
            return ""


# ---------- 工厂函数 ----------

_asr_service: Optional[BaseAsrService] = None


def create_asr_service() -> BaseAsrService:
    """根据配置创建 ASR 服务实例（单例）。

    后端选择策略：
    1. funasr  - 生产环境，中文场景最优
    2. whisper - 多语言或无 FunASR 环境时使用
    3. simple  - 开发测试，零配置快速验证
    """
    global _asr_service
    if _asr_service is not None:
        return _asr_service

    backend = settings.ASR_BACKEND
    logger.info("创建 ASR 服务，后端={}", backend)

    if backend == "funasr":
        _asr_service = FunAsrService()
    elif backend == "whisper":
        _asr_service = WhisperService()
    else:
        _asr_service = SimpleAsrService()

    return _asr_service


def get_asr_service() -> BaseAsrService:
    """获取 ASR 服务单例。"""
    if _asr_service is None:
        return create_asr_service()
    return _asr_service
