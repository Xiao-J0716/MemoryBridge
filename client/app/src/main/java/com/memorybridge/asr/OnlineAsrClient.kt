package com.memorybridge.asr

import android.util.Log
import com.memorybridge.audio.WavUtils
import com.memorybridge.net.ApiClient
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

/**
 * 在线 ASR 客户端：将音频上传到服务端进行精细识别
 *
 * 先粗后精策略中的"精"环节：
 * 1. Vosk 在端侧实时出粗结果（毫秒级）
 * 2. 本客户端将同一段音频上传到服务端
 * 3. 服务端用 FunASR/Whisper 重新识别，返回更准确的文本
 * 4. 精修结果替换粗结果，提升用户体验
 *
 * 网络异常或超时时静默失败，不影响粗结果的使用
 */
object OnlineAsrClient {

    private const val TAG = "OnlineAsrClient"

    /** 在线 ASR 超时时间（毫秒），超时后使用粗结果 */
    private const val TIMEOUT_MS = 10_000L

    /**
     * 上传 WAV 音频到服务端进行精细识别
     *
     * @param pcmData 原始 PCM 16-bit 数据
     * @param language 语言代码（默认 "zh"）
     * @return 识别文本，失败返回 null（调用方使用粗结果）
     */
    suspend fun recognize(pcmData: ByteArray, language: String = "zh"): String? {
        return withContext(Dispatchers.IO) {
            try {
                // 1. PCM → WAV
                val wavData = WavUtils.pcmToWav(pcmData)
                Log.d(TAG, "上传音频进行在线 ASR, pcm=${pcmData.size}B, wav=${wavData.size}B")

                // 2. 构建 multipart 请求
                val filePart = MultipartBody.Part.createFormData(
                    name = "file",
                    filename = "audio.wav",
                    body = wavData.toRequestBody("audio/wav".toMediaTypeOrNull()),
                )
                val langPart = language.toRequestBody("text/plain".toMediaTypeOrNull())

                // 3. 发送请求（带超时保护）
                val text = withTimeoutOrNull(TIMEOUT_MS) {
                    val response = ApiClient.chatApi.recognizeSpeech(filePart, langPart)
                    if (response.isSuccessful) {
                        val body = response.body()
                        Log.i(TAG, "在线 ASR 成功: backend=${body?.backend}, text='${body?.text?.take(50)}', duration=${body?.durationMs}ms")
                        body?.text
                    } else {
                        Log.w(TAG, "在线 ASR HTTP 失败: ${response.code()}")
                        null
                    }
                }

                if (text == null) {
                    Log.w(TAG, "在线 ASR 超时或失败，将使用粗结果")
                }
                text
            } catch (e: Exception) {
                Log.w(TAG, "在线 ASR 异常: ${e.message}")
                null
            }
        }
    }

    /**
     * 查询服务端 ASR 状态
     *
     * @return true 表示在线 ASR 可用，false 表示不可用
     */
    suspend fun isAvailable(): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val response = ApiClient.chatApi.asrStatus()
                response.isSuccessful
            } catch (e: Exception) {
                false
            }
        }
    }
}
