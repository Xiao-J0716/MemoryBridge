package com.memorybridge.ui

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.memorybridge.asr.AsrCoordinator
import com.memorybridge.asr.AsrMode
import com.memorybridge.asr.AsrResult
import com.memorybridge.net.ApiClient
import com.memorybridge.net.ChatRequest
import com.memorybridge.offline.OfflineTemplateEngine
import com.memorybridge.tts.TtsManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID

/** 单条对话消息 */
data class ChatMessage(
    val id: Long = System.currentTimeMillis(),
    val text: String,
    val isUser: Boolean,
    val timestamp: Long = System.currentTimeMillis(),
    /** 标记是否已被精修替换（true=粗结果，false=已精修或非ASR来源） */
    val isCoarse: Boolean = false,
)

/** 监听状态 */
enum class ListeningState {
    IDLE,        // 空闲，等待用户操作
    LISTENING,   // 正在听用户说话
    PROCESSING,  // 正在思考（等待 AI 回复）
    SPEAKING,    // 正在播放语音回复
}

/** UI 状态 */
data class ChatUiState(
    val messages: List<ChatMessage> = emptyList(),
    val listeningState: ListeningState = ListeningState.IDLE,
    val partialText: String = "",
    val isOnline: Boolean = true,
    val errorMessage: String? = null,
    /** ASR 引擎是否就绪（Vosk 模型加载完成 或 在线模式可用） */
    val isAsrReady: Boolean = false,
    /** ASR 正在初始化中（首次加载模型时为 true） */
    val isAsrLoading: Boolean = true,
    /** 当前 ASR 模式 */
    val asrMode: AsrMode = AsrMode.COARSE_TO_FINE,
)

/**
 * 对话 ViewModel
 *
 * 管理完整对话流程：
 * 1. 用户点击语音按钮 -> startListening() -> AsrCoordinator 启动
 * 2. ASR 实时输出 partial 结果 -> UI 显示实时文字
 * 3. VAD 静音超时 / 手动停止 -> onUserInputComplete() -> 停止录音
 * 4. 在线：POST /chat 获取 AI 回复；离线：OfflineTemplateEngine 匹配回复
 * 5. TTS 播放回复（在线 edge-tts / 离线 Android TTS）
 * 6. 播放完成 -> 回到 IDLE 状态
 *
 * ASR 双通道（通过 AsrCoordinator 统一管理）：
 * - COARSE_TO_FINE（默认）：Vosk 即时出粗结果，云端再出精结果替换
 * - OFFLINE_ONLY：仅 Vosk，无需网络
 * - ONLINE_ONLY：仅云端 ASR，精度最高但延迟较大
 */
class ChatViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    /** ASR 双通道协调器（内部管理 AudioRecorder + Vosk + OnlineAsrClient） */
    private val asrCoordinator = AsrCoordinator()

    private var asrJob: Job? = null
    private var chatJob: Job? = null

    // TODO: 用户ID，实际从本地存储或登录流程获取
    private val userId = 1

    /** 会话ID，用于多轮对话上下文关联（服务端必填） */
    private val sessionId = UUID.randomUUID().toString()

    /** Vosk 模型名称（assets/models/ 下的文件夹名） */
    private val voskModelName = "vosk-model-small-cn-0.22"

    init {
        observeAsrResults()
        initAsrEngine()
    }

    /**
     * 在后台线程初始化 ASR 引擎
     *
     * 根据 asrMode 初始化不同引擎：
     * - OFFLINE_ONLY / COARSE_TO_FINE：加载 Vosk 模型（1-3 秒）
     * - ONLINE_ONLY：初始化 VAD，无需加载模型
     */
    private fun initAsrEngine() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isAsrLoading = true)
            try {
                Log.i(TAG, "初始化 ASR 引擎, mode=${_uiState.value.asrMode}, model=$voskModelName")
                val success = withContext(Dispatchers.IO) {
                    asrCoordinator.init(getApplication(), voskModelName)
                }
                if (success) {
                    _uiState.value = _uiState.value.copy(
                        isAsrReady = true,
                        isAsrLoading = false,
                    )
                    Log.i(TAG, "ASR 引擎初始化成功")
                } else {
                    _uiState.value = _uiState.value.copy(
                        isAsrReady = false,
                        isAsrLoading = false,
                        errorMessage = "语音识别引擎加载失败，请检查模型文件",
                    )
                    Log.e(TAG, "ASR 引擎初始化失败")
                }
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isAsrReady = false,
                    isAsrLoading = false,
                    errorMessage = "语音识别初始化异常: ${e.message}",
                )
                Log.e(TAG, "ASR 初始化异常", e)
            }
        }
    }

    /** 重试 ASR 初始化 */
    fun retryAsrInit() {
        if (_uiState.value.isAsrLoading) return
        initAsrEngine()
    }

    /**
     * 切换 ASR 模式
     * @param newMode 新的 ASR 模式
     */
    fun switchAsrMode(newMode: AsrMode) {
        if (_uiState.value.listeningState != ListeningState.IDLE) {
            _uiState.value = _uiState.value.copy(errorMessage = "请先结束当前对话再切换模式")
            return
        }
        val success = asrCoordinator.switchMode(newMode, getApplication(), voskModelName)
        if (success) {
            _uiState.value = _uiState.value.copy(asrMode = newMode)
            Log.i(TAG, "ASR 模式已切换: $newMode")
        } else {
            _uiState.value = _uiState.value.copy(errorMessage = "模式切换失败，可能需要重新初始化")
        }
    }

    /** 观察 ASR 结果流，分发到对应的 UI 状态更新 */
    private fun observeAsrResults() {
        asrJob = viewModelScope.launch {
            asrCoordinator.results.collect { result ->
                when (result) {
                    is AsrResult.Partial -> {
                        _uiState.value = _uiState.value.copy(
                            partialText = result.text,
                            listeningState = ListeningState.LISTENING,
                        )
                    }

                    is AsrResult.Final -> {
                        // 最终识别结果（粗结果），提交到对话流程
                        if (result.text.isNotBlank()) {
                            onUserInputComplete(result.text, isCoarse = true)
                        }
                    }

                    is AsrResult.Refined -> {
                        // 精修结果：替换最后一条用户消息的粗结果
                        updateLastUserMessage(result.text)
                    }

                    is AsrResult.Timeout -> {
                        val partial = _uiState.value.partialText
                        if (partial.isNotBlank()) {
                            onUserInputComplete(partial, isCoarse = true)
                        } else {
                            stopListening()
                        }
                    }

                    is AsrResult.Started -> {
                        _uiState.value = _uiState.value.copy(listeningState = ListeningState.LISTENING)
                    }

                    is AsrResult.Stopped -> {
                        if (_uiState.value.listeningState == ListeningState.LISTENING) {
                            _uiState.value = _uiState.value.copy(
                                listeningState = ListeningState.IDLE,
                                partialText = "",
                            )
                        }
                    }

                    is AsrResult.Error -> {
                        _uiState.value = _uiState.value.copy(
                            errorMessage = result.message,
                            listeningState = ListeningState.IDLE,
                        )
                    }
                }
            }
        }
    }

    /** 开始语音监听 */
    fun startListening() {
        val currentState = _uiState.value
        if (currentState.listeningState != ListeningState.IDLE) return

        if (currentState.isAsrLoading) {
            _uiState.value = currentState.copy(errorMessage = "语音识别正在准备中，请稍候...")
            return
        }
        if (!currentState.isAsrReady) {
            _uiState.value = currentState.copy(errorMessage = "语音识别未就绪，请点击重试")
            return
        }

        TtsManager.stop()
        _uiState.value = _uiState.value.copy(
            listeningState = ListeningState.LISTENING,
            partialText = "",
            errorMessage = null,
        )
        // 启动 ASR 协调器（内部统一启动录音 + Vosk）
        asrCoordinator.start()
    }

    /** 手动停止语音监听 */
    fun stopListening() {
        asrCoordinator.stop()
        val partial = _uiState.value.partialText
        if (partial.isNotBlank()) {
            onUserInputComplete(partial, isCoarse = true)
        } else {
            _uiState.value = _uiState.value.copy(
                listeningState = ListeningState.IDLE,
                partialText = "",
            )
        }
    }

    /**
     * 用户输入完成，提交到服务端或离线处理
     *
     * @param text 用户语音识别后的文本
     * @param isCoarse 是否为粗结果（true=Vosk 粗结果，可能被精修替换）
     */
    private fun onUserInputComplete(text: String, isCoarse: Boolean = false) {
        val userMsg = ChatMessage(text = text, isUser = true, isCoarse = isCoarse)
        _uiState.value = _uiState.value.copy(
            messages = _uiState.value.messages + userMsg,
            listeningState = ListeningState.PROCESSING,
            partialText = "",
        )
        chatJob = viewModelScope.launch {
            val isOnline = ApiClient.isNetworkAvailable()
            _uiState.value = _uiState.value.copy(isOnline = isOnline)
            val reply = if (isOnline) {
                fetchOnlineReply(text)
            } else {
                OfflineTemplateEngine.generateReply(text)
            }
            val aiMsg = ChatMessage(text = reply, isUser = false)
            _uiState.value = _uiState.value.copy(
                messages = _uiState.value.messages + aiMsg,
                listeningState = ListeningState.SPEAKING,
            )
            TtsManager.speak(reply) {
                _uiState.value = _uiState.value.copy(listeningState = ListeningState.IDLE)
            }
        }
    }

    /**
     * 用精修结果替换最后一条用户消息
     *
     * 先粗后精策略：Vosk 先出粗结果（已加入消息列表），云端精修返回后替换文本。
     * 如果消息已进入 AI 回复流程，仅更新显示文本，不重新请求 AI 回复。
     */
    private fun updateLastUserMessage(refinedText: String) {
        val messages = _uiState.value.messages.toMutableList()
        // 找到最后一条 isCoarse=true 的用户消息
        val lastIndex = messages.indexOfLast { it.isUser && it.isCoarse }
        if (lastIndex >= 0) {
            val oldMsg = messages[lastIndex]
            messages[lastIndex] = oldMsg.copy(text = refinedText, isCoarse = false)
            _uiState.value = _uiState.value.copy(messages = messages.toList())
            Log.i(TAG, "已用精修结果替换粗结果: '${oldMsg.text}' -> '$refinedText'")
        }
    }

    /** 调用云端获取 AI 回复，失败时降级到离线模板 */
    private suspend fun fetchOnlineReply(text: String): String {
        return try {
            val response = ApiClient.chatApi.chat(
                ChatRequest(userId = userId, text = text, sessionId = sessionId)
            )
            if (response.isSuccessful) {
                response.body()?.reply ?: OfflineTemplateEngine.generateReply(text)
            } else {
                Log.w(TAG, "云端对话失败: HTTP ${response.code()}")
                OfflineTemplateEngine.generateReply(text)
            }
        } catch (e: Exception) {
            Log.w(TAG, "云端对话异常，降级到离线: ${e.message}")
            OfflineTemplateEngine.generateReply(text)
        }
    }

    override fun onCleared() {
        super.onCleared()
        asrCoordinator.release()
        TtsManager.release()
        asrJob?.cancel()
        chatJob?.cancel()
    }

    companion object {
        private const val TAG = "ChatViewModel"
    }
}
