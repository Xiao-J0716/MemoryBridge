"""LLM 服务：抽象基类 + API 模式 / Ollama 模式。"""

from abc import ABC, abstractmethod
from typing import Optional
import httpx
from loguru import logger

from config import settings


class BaseLlmService(ABC):
    """LLM 服务抽象基类，统一 chat 与 embed 接口。"""

    @abstractmethod
    async def chat(self, messages: list[dict], temperature: Optional[float] = None,
                   max_tokens: Optional[int] = None) -> str:
        """对话补全。

        Args:
            messages: OpenAI 格式的消息列表 [{"role": "user", "content": "..."}]
            temperature: 采样温度
            max_tokens: 最大生成 token 数
        Returns:
            模型回复的文本
        """
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """文本向量化，用于 RAG 检索。

        Args:
            text: 待向量化的文本
        Returns:
            浮点向量列表
        """
        ...

    async def close(self) -> None:
        """释放底层 HTTP 连接。"""
        pass


class ApiLlmService(BaseLlmService):
    """API 模式 —— 调用 DeepSeek 或通义千问（OpenAI 兼容接口）。"""

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        if self.provider == "deepseek":
            self.api_key = settings.DEEPSEEK_API_KEY
            self.base_url = settings.DEEPSEEK_BASE_URL
            self.model = settings.DEEPSEEK_MODEL
            self.embedding_model = settings.QWEN_EMBEDDING_MODEL  # DeepSeek 无 embedding，借用通义
            self.embed_base_url = settings.QWEN_BASE_URL
            self.embed_api_key = settings.QWEN_API_KEY
        else:  # qwen
            self.api_key = settings.QWEN_API_KEY
            self.base_url = settings.QWEN_BASE_URL
            self.model = settings.QWEN_MODEL
            self.embedding_model = settings.QWEN_EMBEDDING_MODEL
            self.embed_base_url = settings.QWEN_BASE_URL
            self.embed_api_key = settings.QWEN_API_KEY

        self.client = httpx.AsyncClient(timeout=60.0)
        logger.info("ApiLlmService 初始化完成，provider={} model={}", self.provider, self.model)

    async def chat(self, messages: list[dict], temperature: Optional[float] = None,
                   max_tokens: Optional[int] = None) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or settings.LLM_TEMPERATURE,
            "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        }
        # TODO: 调用 self.base_url + "/chat/completions"，解析 choices[0].message.content
        resp = await self.client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def embed(self, text: str) -> list[float]:
        headers = {"Authorization": f"Bearer {self.embed_api_key}", "Content-Type": "application/json"}
        payload = {"model": self.embedding_model, "input": text}
        # TODO: 调用 embed_base_url + "/embeddings"，解析 data[0].embedding
        resp = await self.client.post(f"{self.embed_base_url}/embeddings", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]

    async def close(self) -> None:
        await self.client.aclose()


class OllamaLlmService(BaseLlmService):
    """Ollama 模式 —— 本地自部署 Qwen2.5-7B。"""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL
        self.embedding_model = settings.OLLAMA_EMBEDDING_MODEL
        self.client = httpx.AsyncClient(timeout=120.0)
        logger.info("OllamaLlmService 初始化完成，base_url={} model={}", self.base_url, self.model)

    async def chat(self, messages: list[dict], temperature: Optional[float] = None,
                   max_tokens: Optional[int] = None) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature or settings.LLM_TEMPERATURE,
                "num_predict": max_tokens or settings.LLM_MAX_TOKENS,
            },
        }
        # TODO: 调用 Ollama /api/chat 接口，解析 message.content
        resp = await self.client.post(f"{self.base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]

    async def embed(self, text: str) -> list[float]:
        payload = {"model": self.embedding_model, "input": text}
        # Ollama 0.32+ 使用 /api/embed，旧版 /api/embeddings 返回空向量
        resp = await self.client.post(f"{self.base_url}/api/embed", json=payload)
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings")
        if embeddings and embeddings[0]:
            return embeddings[0]
        # 兼容旧版 Ollama
        legacy = data.get("embedding")
        if legacy:
            return legacy
        raise ValueError("Ollama embed 响应为空")

    async def close(self) -> None:
        await self.client.aclose()


def create_llm_service() -> BaseLlmService:
    """工厂函数：根据配置创建对应的 LLM 服务实例。"""
    if settings.LLM_MODE == "ollama":
        return OllamaLlmService()
    return ApiLlmService()
