"""RAG 记忆服务：用 pgvector 做向量存储与相似度检索。"""

from typing import Optional
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.schemas import Memory
from services.llm_service import BaseLlmService
from config import settings


class MemoryService:
    """记忆的存储与检索。

    流程：
      存：用户说的关键内容 → embed → 写入 memories 表（含向量列）
      取：当前用户输入 → embed → pgvector 余弦相似度检索 Top-K
    """

    def __init__(self, llm_service: BaseLlmService):
        self.llm = llm_service

    async def add_memory(
        self,
        db: AsyncSession,
        user_id: int,
        content: str,
        category: Optional[str] = None,
        importance: int = 1,
    ) -> Memory:
        """将一段文本向量化后存入记忆表。

        TODO: 可加入「重要性评估」逻辑——用 LLM 判断这句话是否值得长期记住。
        """
        embedding = await self.llm.embed(content)
        memory = Memory(
            user_id=user_id,
            content=content,
            embedding=embedding,
            category=category,
            importance=importance,
        )
        db.add(memory)
        await db.flush()
        logger.debug("记忆已存储 user_id={} category={} len={}", user_id, category, len(content))
        return memory

    async def search_memories(
        self,
        db: AsyncSession,
        user_id: int,
        query: str,
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """向量相似度检索：返回与 query 最相关的记忆。

        使用 pgvector 的 <=> 操作符（余弦距离），距离越小越相似。
        """
        top_k = top_k or settings.MEMORY_TOP_K
        query_embedding = await self.llm.embed(query)

        # pgvector 余弦距离排序：<=> 为余弦距离，取最近的 top_k
        stmt = (
            select(
                Memory,
                Memory.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .where(Memory.user_id == user_id)
            .order_by(text("distance"))
            .limit(top_k)
        )
        result = await db.execute(stmt)
        rows = result.all()

        memories = []
        for row in rows:
            mem: Memory = row[0]
            distance: float = row[1]
            score = 1.0 - distance  # 距离转相似度
            memories.append({
                "content": mem.content,
                "category": mem.category,
                "importance": mem.importance,
                "score": round(score, 4),
            })
        logger.debug("记忆检索 user_id={} query_len={} hits={}", user_id, len(query), len(memories))
        return memories

    async def build_memory_context(self, memories: list[dict]) -> str:
        """将检索到的记忆列表拼接为 Prompt 上下文文本。

        TODO: 可加入记忆去重、按重要性加权、超长截断等逻辑。
        """
        if not memories:
            return ""
        lines = ["以下是关于这位老人的已知信息，请在回复中自然地参考："]
        for m in memories:
            lines.append(f"- {m['content']}")
        return "\n".join(lines)
