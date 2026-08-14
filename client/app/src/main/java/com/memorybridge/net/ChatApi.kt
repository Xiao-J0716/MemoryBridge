package com.memorybridge.net

import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

/**
 * REST API 接口定义
 *
 * 端点：
 * - POST /api/chat  : 发送用户文本，获取 AI 回复文本
 * - POST /api/tts   : 发送文本，获取 TTS 音频
 * - POST /api/asr   : 上传 WAV 音频，获取识别文本（在线 ASR）
 * - GET  /health    : 服务器健康检查
 */
interface ChatApi {

    /**
     * 对话接口：发送用户文本，获取 AI 回复
     * @param request 包含用户ID、文本内容、会话ID
     * @return AI 回复文本及元数据
     */
    @POST("api/chat")
    suspend fun chat(@Body request: ChatRequest): Response<ChatResponse>

    /**
     * TTS 接口：文本转语音
     * @param request 包含文本、音色、语速
     * @return 音频数据（MP3/WAV）
     */
    @POST("api/tts")
    suspend fun generateTts(@Body request: TtsRequest): Response<ResponseBody>

    /**
     * ASR 接口：在线语音识别（先粗后精的"精"环节）
     *
     * 客户端将 Vosk 识别期间录制的音频上传，服务端用更精确的模型
     * （FunASR/Whisper）重新识别，返回更高精度的文本。
     *
     * @param file WAV 音频文件（16kHz, mono, 16-bit PCM）
     * @param language 语言代码（如 "zh"）
     * @return 识别文本及后端信息
     */
    @Multipart
    @POST("api/asr")
    suspend fun recognizeSpeech(
        @Part file: MultipartBody.Part,
        @Part("language") language: RequestBody,
    ): Response<AsrResponse>

    /**
     * ASR 服务状态查询
     * @return 后端名称和可用状态
     */
    @GET("api/asr/status")
    suspend fun asrStatus(): Response<okhttp3.ResponseBody>

    /**
     * 健康检查
     * @return 服务器状态信息
     */
    @GET("health")
    suspend fun healthCheck(): Response<HealthResponse>
}
