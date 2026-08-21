"""ASR 语音识别服务：支持 Unisound / FunASR / Whisper / Simple 四种后端。

架构设计：
  - BaseAsrService: 抽象基类，统一 recognize 接口
  - UnisoundService: 云知声 U2-ASR，云端异步，精度高，推荐做先粗后精的精
  - FunAsrService: 阿里达摩院 FunASR，中文识别精度最高，需本地模型
  - WhisperService: OpenAI Whisper (faster-whisper)，多语言
  - SimpleAsrService: speech_recognition + Google Web API，零配置快速测试

音频输入格式：WAV (16kHz, mono, 16-bit PCM)，与客户端 AudioRecorder 一致
"""

import io
import json
import time
import tempfile
import urllib.request
import urllib.error
from urllib.parse import quote
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


class UnisoundService(BaseAsrService):
    """云知声 U2-ASR：异步语音转写云服务。

    流程：上传音频文件 → 创建 ASR 任务 → 轮询至完成 → 取逐句文本。
    鉴权：Authorization: Bearer {api_key}（Token Plan 优先）。
    用纯标准库实现（urllib），无第三方依赖；与官方 skill 脚本一致。
    适合做"先粗后精"中的精修后端：精度高、带标点时间戳，但延迟秒级。
    """

    BASE_URL = "https://maas-api.unisound.com"
    UPLOAD_URL = f"{BASE_URL}/v1/files/upload"
    TASK_URL = f"{BASE_URL}/v1/audio/asr/tasks"

    def __init__(self):
        api_key = settings.UNISOUND_API_KEY
        if not api_key:
            raise RuntimeError("UNISOUND_API_KEY 未配置，无法启用云知声 ASR")
        self._api_key = api_key
        logger.info("UnisoundService 初始化完成（U2-ASR 云端）")

    @property
    def backend_name(self) -> str:
        return "unisound"

    def _headers(self, json_body: bool = False) -> dict:
        h = {"Authorization": f"Bearer {self._api_key}"}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def _http(self, url: str, method: str, headers: dict, body: bytes | None = None) -> dict:
        req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.error("HTTP {} for {}: {}", exc.code, url, detail[:300])
            return {}

    async def recognize(self, audio_wav: bytes, language: str = "zh") -> str:
        def _do():
            # 1. 上传音频（multipart，purpose=a2t_async_input）
            boundary = "----memorybridge-boundary-" + str(int(time.time() * 1000))
            filename = "audio.wav"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="purpose"\r\n\r\n'
                f"a2t_async_input\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: audio/wav\r\n\r\n"
            ).encode("utf-8") + audio_wav + f"\r\n--{boundary}--\r\n".encode("utf-8")
            upload_headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            }
            upload_resp = self._http(self.UPLOAD_URL, "POST", upload_headers, body)
            # 返回结构: {"file": {"file_id": ...}, "base_resp": {"status_code": 0}}
            file_id = (upload_resp.get("file") or {}).get("file_id") or upload_resp.get("file_id")
            if not file_id:
                logger.error("云知声上传失败: {}", json.dumps(upload_resp, ensure_ascii=False)[:200])
                return ""

            # 2. 创建 ASR 任务（payload 与官方 skill 一致，file_id 须为 int）
            lang_map = {"zh": "zh-CN", "en": "en-US"}
            payload = {
                "model": "u2-asr",
                "format": "wav",
                "sample_rate": 16000,
                "enable_auto_lang": False,
                "enable_itn": True,
                "channel": 1,
                "enable_speaker": False,
                "word_info": False,
                "file_id": int(file_id),
                "language": lang_map.get(language, language),
            }
            task_resp = self._http(
                self.TASK_URL, "POST", self._headers(json_body=True),
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
            task_id = (task_resp.get("data") or task_resp).get("task_id") or task_resp.get("task_id")
            if not task_id:
                logger.error("云知声建任务失败: {}", json.dumps(task_resp, ensure_ascii=False)[:200])
                return ""

            # 3. 轮询
            deadline = time.time() + settings.ASR_TIMEOUT
            while time.time() < deadline:
                time.sleep(3)
                status_resp = self._http(
                    f"{self.TASK_URL}/{quote(str(task_id))}", "GET", self._headers(),
                )
                data = status_resp.get("data") or status_resp
                status = data.get("status")
                if status in ("Success", "success", 2, "2"):
                    # 结果在 data.result（逐句 list）或 data.results
                    results = data.get("result") or data.get("results") or []
                    if isinstance(results, list):
                        return "".join(seg.get("text", "") for seg in results if isinstance(seg, dict))
                    return str(results)
                if status in ("Failed", "failed", 3, "3"):
                    logger.error("云知声任务失败: {}", json.dumps(status_resp, ensure_ascii=False)[:200])
                    return ""
            logger.warning("云知声识别超时 task_id={}", task_id)
            return ""

        try:
            text = await asyncio.wait_for(asyncio.to_thread(_do), timeout=settings.ASR_TIMEOUT)
            logger.info("Unisound 识别成功: {}", text[:50])
            return text
        except asyncio.TimeoutError:
            logger.warning("Unisound 识别超时")
            return ""
        except Exception as e:
            logger.error("Unisound 识别失败: {}", e)
            return ""


def create_asr_service() -> BaseAsrService:
    """根据配置创建 ASR 服务实例（单例）。

    后端选择策略：
    1. unisound - 云知声 U2-ASR，云端精修，精度高（推荐做先粗后精的精）
    2. funasr   - 阿里达摩院 FunASR，中文识别精度高，需本地模型
    3. whisper  - OpenAI Whisper，多语言
    4. simple   - 开发测试，零配置快速验证
    """
    global _asr_service
    if _asr_service is not None:
        return _asr_service

    backend = settings.ASR_BACKEND
    logger.info("创建 ASR 服务，后端={}", backend)

    if backend == "unisound":
        _asr_service = UnisoundService()
    elif backend == "funasr":
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
