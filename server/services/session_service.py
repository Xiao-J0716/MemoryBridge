"""会话管理：Redis 缓存最近 N 轮对话上下文。"""

from typing import Optional
import json
import redis.asyncio as redis_async
from loguru import logger

from config import settings


class SessionService:
    """基于 Redis 的会话上下文缓存。

    数据结构：
        key = session:{session_id}
        value = JSON 数组，每轮含 {"role": "user"/"assistant", "content": "..."}
    保留最近 SESSION_HISTORY_TURNS 轮（一轮 = 一问一答 = 2 条消息）。
    """

    def __init__(self):
        self.redis = redis_async.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        self.max_messages = settings.SESSION_HISTORY_TURNS * 2  # 每轮 2 条

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def get_context(self, session_id: str) -> list[dict]:
        """读取缓存的对话历史（OpenAI 消息格式）。"""
        raw = await self.redis.get(self._key(session_id))
        if not raw:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("会话缓存 JSON 解析失败 session_id={}", session_id)
            return []

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        """追加一条消息并裁剪到最近 N 轮。"""
        messages = await self.get_context(session_id)
        messages.append({"role": role, "content": content})
        # 裁剪：保留最近 max_messages 条
        if len(messages) > self.max_messages:
            messages = messages[-self.max_messages:]
        await self.redis.set(
            self._key(session_id),
            json.dumps(messages, ensure_ascii=False),
            ex=settings.SESSION_TTL,
        )

    async def add_round(self, session_id: str, user_text: str, assistant_text: str) -> None:
        """一次性写入一轮对话（用户消息 + 助手回复）。"""
        await self.add_message(session_id, "user", user_text)
        await self.add_message(session_id, "assistant", assistant_text)

    async def clear_session(self, session_id: str) -> None:
        """清除指定会话的缓存。"""
        await self.redis.delete(self._key(session_id))
        logger.info("会话缓存已清除 session_id={}", session_id)

    async def close(self) -> None:
        await self.redis.aclose()


# 单例
_session_service: Optional[SessionService] = None


async def get_session_service() -> SessionService:
    """获取 SessionService 单例（延迟初始化）。"""
    global _session_service
    if _session_service is None:
        _session_service = SessionService()
    return _session_service
