package com.memorybridge.asr

import android.content.Context
import android.util.Log
import com.memorybridge.audio.AudioRecorder
import com.memorybridge.audio.VadStrategy
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

/**
 * ASR 双通道协调器
 *
 * 统一管理离线 Vosk 和在线云端 ASR，对上层屏蔽多引擎细节。
 *
 * 三种工作模式：
 *
 * 1. OFFLINE_ONLY（仅离线）
 *    AudioRecorder → Vosk → Partial/Final → ViewModel
 *    特点：最快（毫秒级），无需网络，精度中等
 *
 * 2. ONLINE_ONLY（仅在线）
 *    AudioRecorder → VAD 检测句末 → 上传音频 → 云端 ASR → Final → ViewModel
 *    特点：最准，需网络，延迟较高（秒级），无实时 partial
 *
 * 3. COARSE_TO_FINE（先粗后精，默认）
 *    AudioRecorder → Vosk → Partial/Final（粗）→ ViewModel
 *                 ↘ 缓冲音频 → 句末上传 → 云端 ASR → Refined（精）→ ViewModel
 *    特点：兼顾速度和精度，先用 Vosk 出粗结果，再用云端精修替换
 *
 * 数据流：
 *   AudioRecorder.onAudioData → coordinator.onAudioData()
 *     ├─ mode != ONLINE_ONLY → SpeechRecognizerManager.feedAudioData (Vosk)
 *     └─ mode == ONLINE_ONLY → VadStrategy 检测句末
 *
 *   SpeechRecognizerManager.results → coordinator 观察
 *     ├─ Partial → 直接转发
 *     ├─ Final → 转发 + 触发在线精修（COARSE_TO_FINE 模式）
 *     └─ Timeout → 触发在线精修（COARSE_TO_FINE 模式）
 */
class AsrCoordinator {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    /** 内部创建 AudioRecorder，回调直接路由到 onAudioData */
    private val audioRecorder = AudioRecorder { buffer, bytesRead ->
        onAudioData(buffer, bytesRead)
    }

    /** 统一的 ASR 结果流，ViewModel 观察此流 */
    private val _results = MutableSharedFlow<AsrResult>(extraBufferCapacity = 32)
    val results: SharedFlow<AsrResult> = _results.asSharedFlow()

    /** 当前 ASR 模式 */
    var mode: AsrMode = AsrMode.COARSE_TO_FINE
        private set

    /** VAD 策略（仅 ONLINE_ONLY 模式使用，替代 Vosk 的端点检测） */
    private var vadStrategy: VadStrategy? = null

    /** 当前在线精修任务（防止并发） */
    private var refineJob: Job? = null

    /** 是否正在运行 */
    private var isRunning = false

    /** 观察 Vosk 结果的协程 */
    private var observeJob: Job? = null

    /**
     * 初始化 ASR 引擎
     * - OFFLINE_ONLY / COARSE_TO_FINE：初始化 Vosk
     * - ONLINE_ONLY：初始化 VAD
     *
     * @param context Android Context
     * @param modelPath Vosk 模型路径（assets 下的文件夹名）
     * @return true 初始化成功
     */
    fun init(context: Context, modelPath: String): Boolean {
        return when (mode) {
            AsrMode.ONLINE_ONLY -> {
                vadStrategy = VadStrategy()
                Log.i(TAG, "ONLINE_ONLY 模式：VAD 初始化完成")
                true
            }
            else -> {
                // OFFLINE_ONLY 或 COARSE_TO_FINE：需要 Vosk
                val success = SpeechRecognizerManager.init(context, modelPath)
                if (success && mode == AsrMode.COARSE_TO_FINE) {
                    Log.i(TAG, "COARSE_TO_FINE 模式：Vosk 初始化成功，在线精修已启用")
                }
                success
            }
        }
    }

    /**
     * 切换 ASR 模式
     *
     * @param newMode 新的 ASR 模式
     * @param context 切换到需要 Vosk 的模式时需要 Context 重新初始化
     * @param modelPath Vosk 模型路径
     * @return true 切换成功
     */
    fun switchMode(newMode: AsrMode, context: Context? = null, modelPath: String? = null): Boolean {
        if (isRunning) {
            Log.w(TAG, "运行中不允许切换模式")
            return false
        }
        val oldMode = mode
        mode = newMode
        Log.i(TAG, "ASR 模式切换: $oldMode → $newMode")

        // 从 ONLINE_ONLY 切换到需要 Vosk 的模式
        if (oldMode == AsrMode.ONLINE_ONLY && newMode != AsrMode.ONLINE_ONLY) {
            if (context != null && modelPath != null) {
                return init(context, modelPath)
            }
        }
        // 切换到 ONLINE_ONLY，释放 Vosk 资源
        if (newMode == AsrMode.ONLINE_ONLY && oldMode != AsrMode.ONLINE_ONLY) {
            SpeechRecognizerManager.release()
            vadStrategy = VadStrategy()
        }
        return true
    }

    /**
     * 启动 ASR 识别
     *
     * 1. 清空音频缓冲区
     * 2. 启动 Vosk（非 ONLINE_ONLY 模式）
     * 3. 启动录音（AudioRecorder 自动缓冲音频）
     * 4. 开始观察 Vosk 结果（非 ONLINE_ONLY 模式）
     */
    fun start() {
        if (isRunning) return
        isRunning = true

        audioRecorder.clearBuffer()

        if (mode != AsrMode.ONLINE_ONLY) {
            // 启动 Vosk 并观察其结果
            SpeechRecognizerManager.start()
            startObservingVosk()
        }

        _results.tryEmit(AsrResult.Started)

        // 启动录音（AudioRecorder 的 onAudioData 回调会调用 coordinator.onAudioData）
        val recorderStarted = audioRecorder.start()
        if (!recorderStarted) {
            _results.tryEmit(AsrResult.Error("无法启动录音，请检查权限"))
            isRunning = false
        }

        Log.i(TAG, "ASR 启动, mode=$mode")
    }

    /** 停止 ASR 识别 */
    fun stop() {
        if (!isRunning) return
        isRunning = false

        audioRecorder.stop()

        if (mode != AsrMode.ONLINE_ONLY) {
            SpeechRecognizerManager.stop()
            observeJob?.cancel()
            observeJob = null
        }

        refineJob?.cancel()
        refineJob = null

        _results.tryEmit(AsrResult.Stopped)
        Log.i(TAG, "ASR 停止")
    }

    /**
     * AudioRecorder 音频数据回调
     *
     * 由 AudioRecorder 在录音线程中调用，coordinator 根据 mode 分发：
     * - 非 ONLINE_ONLY：送入 Vosk 实时识别
     * - ONLINE_ONLY：送入 VAD 检测句末
     *
     * 注意：AudioRecorder 内部同时缓存了音频数据，句末时通过 drainBufferedPcm 提取
     */
    fun onAudioData(buffer: ByteArray, bytesRead: Int) {
        if (!isRunning) return

        if (mode != AsrMode.ONLINE_ONLY) {
            // 送入 Vosk 进行实时识别
            SpeechRecognizerManager.feedAudioData(buffer, bytesRead)
        }

        if (mode == AsrMode.ONLINE_ONLY) {
            // ONLINE_ONLY 模式：用 VAD 检测句末
            vadStrategy?.onAudioFrame(buffer, bytesRead) { isSilent ->
                if (isSilent && vadStrategy?.isTimeout() == true) {
                    Log.d(TAG, "VAD 检测到句末（静音超时）")
                    triggerOnlineOnlyAsr()
                    vadStrategy?.reset()
                }
            }
        }
    }

    /** 释放所有资源 */
    fun release() {
        stop()
        SpeechRecognizerManager.release()
        vadStrategy = null
        scope.coroutineContext[Job]?.cancel()
    }

    // ---------- 内部方法 ----------

    /** 观察 Vosk 结果流，转发并触发在线精修 */
    private fun startObservingVosk() {
        observeJob = scope.launch {
            SpeechRecognizerManager.results.collect { result ->
                when (result) {
                    is AsrResult.Partial -> {
                        // 部分结果直接转发
                        _results.tryEmit(result)
                    }
                    is AsrResult.Final -> {
                        // 粗结果立即转发
                        _results.tryEmit(result)
                        // COARSE_TO_FINE 模式：触发在线精修
                        if (mode == AsrMode.COARSE_TO_FINE && result.text.isNotBlank()) {
                            triggerRefinement()
                        }
                    }
                    is AsrResult.Timeout -> {
                        // 超时：如果有缓冲音频，触发在线精修
                        if (mode == AsrMode.COARSE_TO_FINE) {
                            triggerRefinement()
                        }
                        _results.tryEmit(result)
                    }
                    is AsrResult.Error -> {
                        _results.tryEmit(result)
                    }
                    is AsrResult.Started, is AsrResult.Stopped -> {
                        // 不转发这些事件（coordinator 自己管理）
                    }
                    is AsrResult.Refined -> {
                        // 不会从 Vosk 收到 Refined
                    }
                }
            }
        }
    }

    /**
     * 触发在线精修（COARSE_TO_FINE 模式）
     *
     * 1. 从 AudioRecorder 提取缓冲的 PCM 数据
     * 2. 上传到服务端进行精细识别
     * 3. 如果返回更准确的结果，发射 Refined 事件
     */
    private fun triggerRefinement() {
        refineJob?.cancel() // 取消上一次未完成的精修
        refineJob = scope.launch {
            val pcmData = audioRecorder.drainBufferedPcm()
            if (pcmData == null || pcmData.isEmpty()) {
                Log.d(TAG, "无缓冲音频，跳过在线精修")
                return@launch
            }

            Log.d(TAG, "开始在线精修, 音频大小=${pcmData.size}B")
            val refinedText = OnlineAsrClient.recognize(pcmData)

            if (refinedText != null && refinedText.isNotBlank()) {
                Log.i(TAG, "在线精修完成: '$refinedText'")
                _results.tryEmit(AsrResult.Refined(refinedText))
            } else {
                Log.d(TAG, "在线精修无结果，保留粗结果")
            }
        }
    }

    /**
     * ONLINE_ONLY 模式的在线识别触发
     *
     * VAD 检测到句末时，提取缓冲音频上传识别
     */
    private fun triggerOnlineOnlyAsr() {
        refineJob?.cancel()
        refineJob = scope.launch {
            val pcmData = audioRecorder.drainBufferedPcm()
            if (pcmData == null || pcmData.isEmpty()) return@launch

            // ONLINE_ONLY 模式需要等待结果，先发射 Started 状态
            _results.tryEmit(AsrResult.Partial("正在识别..."))

            val text = OnlineAsrClient.recognize(pcmData)
            if (text != null && text.isNotBlank()) {
                _results.tryEmit(AsrResult.Final(text))
            } else {
                _results.tryEmit(AsrResult.Error("在线识别失败，请重试"))
            }
        }
    }

    companion object {
        private const val TAG = "AsrCoordinator"
    }
}
