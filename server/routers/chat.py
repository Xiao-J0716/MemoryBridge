"""对话路由：POST /chat —— 核心对话入口。

流程：
  1. 从 Redis 取最近对话上下文
  2. 用 pgvector 检索与当前输入相关的记忆
  3. 拼接 System Prompt + 记忆上下文 + 历史消息 + 当前输入
  4. 调 LLM 生成回复
  5. 更新 Redis 会话缓存 + 异步写入记忆（可选）
  6. 返回回复文本
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.database import get_db
from models.schemas import ChatRequest, ChatResponse
from services.llm_service import create_llm_service, BaseLlmService
from services.memory_service import MemoryService
from services.session_service import get_session_service

router = APIRouter()

# LLM 服务单例（应用级，不随请求重建）
_llm_service: BaseLlmService | None = None


def get_llm_service() -> BaseLlmService:
    """获取 LLM 服务单例。"""
    global _llm_service
    if _llm_service is None:
        _llm_service = create_llm_service()
    return _llm_service


SYSTEM_PROMPT = (
    "你是一个温暖、耐心的 AI 陪伴助手，专门陪伴认知症（阿尔茨海默病等）老人。"
    "请用简单、亲切、口语化的中文回复，句子要短，避免复杂句式。"
    "如果老人重复提问，不要指出重复，耐心再回答一遍。"
    "语气要像家人一样关心，适当回忆共同经历，安抚情绪。"
    "回复控制在 3-4 句话以内。"
)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    """核心对话接口。"""
    try:
        llm = get_llm_service()
        session_svc = await get_session_service()
        memory_svc = MemoryService(llm)

        # 1. 从 Redis 取对话历史
        history = await session_svc.get_context(req.session_id)

        # 2. 检索相关记忆
        memories = await memory_svc.search_memories(db, req.user_id, req.text)
        memory_context = await memory_svc.build_memory_context(memories)

        # 3. 拼 Prompt
        system_content = SYSTEM_PROMPT
        if memory_context:
            system_content += "\n\n" + memory_context

        messages: list[dict] = [{"role": "system", "content": system_content}]
        messages.extend(history)
        messages.append({"role": "user", "content": req.text})

        # 4. 调 LLM
        reply = await llm.chat(messages)

        # 5. 更新会话缓存
        await session_svc.add_round(req.session_id, req.text, reply)

        # 6. 异步写入记忆（TODO: 此处可改为后台任务，避免阻塞响应）
        #    简单策略：用户说的每句话都暂存，后续可加入重要性过滤
        await memory_svc.add_memory(db, req.user_id, req.text, category="dialog")

        logger.info("对话完成 user_id={} session={} reply_len={}", req.user_id, req.session_id, len(reply))

        return ChatResponse(
            reply=reply,
            session_id=req.session_id,
            memories_used=len(memories),
        )
    except Exception as e:
        logger.error("对话失败: {}", e)
        raise HTTPException(status_code=500, detail=f"对话服务异常: {e}")
