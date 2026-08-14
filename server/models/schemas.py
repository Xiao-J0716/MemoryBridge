"""Pydantic 请求/响应模型 + SQLAlchemy ORM 模型。"""

from datetime import datetime
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field
from sqlalchemy import (
    String, Integer, Text, DateTime, ForeignKey, JSON, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base
from config import settings


# ============================================================
#  SQLAlchemy ORM 模型
# ============================================================

class User(Base):
    """用户表 —— 存储老人基本信息。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="老人姓名")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="年龄")
    avatar: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="头像 URL")
    profile: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="扩展信息：爱好、亲属、禁忌等")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")
    memories: Mapped[list["Memory"]] = relationship(back_populates="user")


class Session(Base):
    """会话表 —— 每次对话连接为一条记录。"""
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="会话 ID（UUID）")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="会话标题")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="sessions")


class Memory(Base):
    """记忆表 —— 存储 RAG 向量化的记忆片段。"""
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="记忆文本内容")
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.EMBEDDING_DIM), nullable=False, comment="向量嵌入")
    category: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="分类：family/hobby/event 等")
    importance: Mapped[int] = mapped_column(Integer, default=1, comment="重要程度 1-5")
    metadata_: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="额外元信息")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="memories")


# ============================================================
#  Pydantic 请求/响应模型
# ============================================================

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatMessage(BaseModel):
    """单条消息。"""
    role: str = Field(description="消息角色：user / assistant / system")
    content: str = Field(description="消息内容")


class ChatRequest(BaseModel):
    """对话请求。"""
    text: str = Field(..., min_length=1, max_length=2000, description="用户输入文本")
    user_id: int = Field(..., description="用户 ID")
    session_id: str = Field(..., description="会话 ID")


class ChatResponse(BaseModel):
    """对话响应。"""
    reply: str = Field(description="AI 回复文本")
    session_id: str = Field(description="会话 ID")
    memories_used: int = Field(default=0, description="本次检索到的记忆条数")


class TTSRequest(BaseModel):
    """语音合成请求。"""
    text: str = Field(..., min_length=1, max_length=500, description="待合成文本")
    voice: str | None = Field(default=None, description="语音角色，默认取配置")
    rate: str | None = Field(default=None, description="语速如 +10%，默认取配置")
    volume: str | None = Field(default=None, description="音量如 +0%，默认取配置")


class MemoryCreate(BaseModel):
    """手动写入记忆（调试/导入用）。"""
    user_id: int
    content: str
    category: str | None = None
    importance: int = 1


class MemoryResponse(BaseModel):
    """记忆检索结果。"""
    content: str
    category: str | None = None
    importance: int = 1
    score: float | None = None


class AsrResponse(BaseModel):
    """ASR 语音识别响应。"""
    text: str = Field(default="", description="识别出的文本，空字符串表示识别失败")
    backend: str = Field(default="", description="ASR 后端名称: funasr / whisper / simple")
    duration_ms: int = Field(default=0, description="识别耗时（毫秒）")
