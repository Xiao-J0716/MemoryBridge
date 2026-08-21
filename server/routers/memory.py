"""记忆查询路由：GET /memory/query —— 调试用记忆检索端点。

供前端调试面板或开发人员查看 RAG 检索结果。
不修改 MemoryService 本身，仅做薄封装。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.database import get_db
from models.schemas import MemoryResponse
from services.llm_service import create_llm_service, BaseLlmService
from services.memory_service import MemoryService

router = APIRouter()

# LLM 服务单例（与 chat 路由共享同一实例逻辑）
_llm_service: BaseLlmService | None = None


def _get_llm_service() -> BaseLlmService:
    global _llm_service
    if _llm_service is None:
        _llm_service = create_llm_service()
    return _llm_service


@router.get("/memory/query", response_model=list[MemoryResponse])
async def query_memories(
    user_id: int = Query(..., description="用户 ID"),
    query: str = Query(..., min_length=1, max_length=500, description="检索文本"),
    top_k: int = Query(default=0, ge=0, description="返回条数，0 表示用默认配置"),
    db: AsyncSession = Depends(get_db),
) -> list[MemoryResponse]:
    """向量相似度检索：返回与 query 最相关的记忆条目。

    用途：调试面板展示 RAG 检索结果，验证记忆是否被正确存储和检索。
    """
    llm = _get_llm_service()
    memory_svc = MemoryService(llm)
    memories = await memory_svc.search_memories(db, user_id, query, top_k or None)
    logger.info("记忆查询 user_id={} query_len={} hits={}", user_id, len(query), len(memories))
    return [
        MemoryResponse(
            content=m["content"],
            category=m["category"],
            importance=m["importance"],
            score=m["score"],
        )
        for m in memories
    ]
