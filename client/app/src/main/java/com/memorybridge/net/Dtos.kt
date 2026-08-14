package com.memorybridge.net

import com.google.gson.annotations.SerializedName

/**
 * 对话请求
 *
 * 与服务端 schemas.ChatRequest 对齐：
 * - user_id: int（服务端 User 表主键为自增整数）
 * - session_id: str（必填，服务端用于 Redis 上下文缓存关联）
 * - text: 用户输入文本（ASR 识别结果）
 *
 * @param userId 用户唯一标识（整数，对应服务端 users.id）
 * @param text 用户输入文本（ASR 识别结果）
 * @param sessionId 会话ID，用于多轮对话上下文关联
 */
data class ChatRequest(
    @SerializedName("user_id") val userId: Int,
    @SerializedName("text") val text: String,
    @SerializedName("session_id") val sessionId: String,
)

/**
 * 对话响应
 *
 * 与服务端 schemas.ChatResponse 对齐：
 * - reply: AI 回复文本
 * - session_id: 会话ID（原样返回，用于后续请求关联）
 * - memories_used: 本次检索到的记忆条数（RAG 命中数）
 *
 * @param reply AI 回复文本
 * @param sessionId 会话ID
 * @param memoriesUsed 本次检索到的记忆条数
 */
data class ChatResponse(
    @SerializedName("reply") val reply: String,
    @SerializedName("session_id") val sessionId: String,
    @SerializedName("memories_used") val memoriesUsed: Int = 0,
)

/**
 * TTS 请求
 *
 * 与服务端 schemas.TTSRequest 对齐：
 * - text: 待合成文本（服务端限制 1-500 字）
 * - voice/rate/volume: 可选，不传则服务端使用配置默认值
 *
 * @param text 待合成文本
 * @param voice 音色名称（edge-tts 音色，如 zh-CN-XiaoxiaoNeural）
 * @param rate 语速调整（如 "-10%" 表示慢 10%，适配老人听力）
 * @param volume 音量调整
 */
data class TtsRequest(
    @SerializedName("text") val text: String,
    @SerializedName("voice") val voice: String = "zh-CN-XiaoxiaoNeural",
    @SerializedName("rate") val rate: String = "-10%",
    @SerializedName("volume") val volume: String = "+0%",
)

/**
 * 健康检查响应
 *
 * 与服务端 schemas.HealthResponse 对齐：
 * - status: 服务器状态（"ok" / "error"）
 * - version: 服务版本号
 * - timestamp: 服务器当前时间
 *
 * @param status 服务器状态
 * @param version 服务版本号
 * @param timestamp 服务器时间戳（ISO 8601 字符串）
 */
data class HealthResponse(
    @SerializedName("status") val status: String,
    @SerializedName("version") val version: String = "",
    @SerializedName("timestamp") val timestamp: String? = null,
)

/**
 * ASR 语音识别响应
 *
 * 与服务端 schemas.AsrResponse 对齐：
 * - text: 识别出的文本
 * - backend: 使用的后端（funasr/whisper/simple）
 * - duration_ms: 识别耗时
 *
 * @param text 识别文本（空字符串表示失败）
 * @param backend ASR 后端名称
 * @param durationMs 识别耗时（毫秒）
 */
data class AsrResponse(
    @SerializedName("text") val text: String = "",
    @SerializedName("backend") val backend: String = "",
    @SerializedName("duration_ms") val durationMs: Int = 0,
)
