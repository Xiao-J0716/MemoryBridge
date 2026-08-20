package com.memorybridge.asr

/**
 * VAD（语音活动检测）策略
 *
 * 针对认知症老人特点优化：
 * - 语速慢，停顿多，常在句子中间停顿思考
 * - 静音超时从默认 1-2 秒延长到 3-4 秒（默认 3500ms），避免误截断
 * - 基于能量阈值（RMS）判断是否为静音
 * - 能量阈值可动态调整，适应不同环境噪声
 *
 * 触发模型：超时在 onAudioFrame 中“确定性地置位” pendingTimeout，
 * 由 consumeTimeout() 消费，保证一段语音只触发一次、不漏帧。
 * 参数默认值取自 [AsrConfig]，调优时只改 AsrConfig 一处。
 */
class VadStrategy(
    /** 静音超时时间（毫秒），默认取 AsrConfig，老人语速慢需要更长 */
    private val silenceTimeoutMs: Long = AsrConfig.VAD_SILENCE_TIMEOUT_MS,
    /** 静音能量阈值（RMS），低于此值认为静音 */
    private var silenceEnergyThreshold: Double = AsrConfig.VAD_SILENCE_THRESHOLD,
    /** 最小说话时长（毫秒），避免短噪声误触发 */
    private val minSpeechMs: Long = AsrConfig.VAD_MIN_SPEECH_MS,
) {
    private var lastVoiceTimeMs: Long = 0L
    private var speechStartTimeMs: Long = 0L
    private var isInSpeech: Boolean = false

    /** 本段语音的确定性超时标志，由 onAudioFrame 置位、consumeTimeout 取走 */
    private var pendingTimeout: Boolean = false

    /**
     * 处理一帧音频数据
     * @param buffer PCM 16-bit 数据
     * @param bytesRead 有效字节数
     * @param onSilence 回调：检测到静音（>200ms 无能量）时触发 true
     */
    fun onAudioFrame(buffer: ByteArray, bytesRead: Int, onSilence: (Boolean) -> Unit) {
        val rms = calculateRms(buffer, bytesRead)
        val now = System.currentTimeMillis()
        val isVoice = rms > silenceEnergyThreshold
        if (isVoice) {
            if (!isInSpeech) {
                isInSpeech = true
                speechStartTimeMs = now
            }
            lastVoiceTimeMs = now
            pendingTimeout = false
            onSilence(false)
        } else if (isInSpeech) {
            val silenceDuration = now - lastVoiceTimeMs
            if (silenceDuration > 200) {
                // 超过 200ms 没有检测到语音能量
                onSilence(true)
            }
            // 静音超过阈值且说话时长达标：确定性地置位超时标志，
            // 由 consumeTimeout() 消费，避免再读一次时钟导致漏触发。
            if (silenceDuration > silenceTimeoutMs &&
                (lastVoiceTimeMs - speechStartTimeMs) > minSpeechMs
            ) {
                pendingTimeout = true
                isInSpeech = false
            }
        }
    }

    /**
     * 消费并清除超时标志。
     *
     * 超时在 onAudioFrame 中确定性地置位（pendingTimeout），这里只负责取出。
     * 调用方拿到 true 后应自行 reset() 开始新一段检测，保证一段语音只触发一次。
     */
    fun consumeTimeout(): Boolean {
        val t = pendingTimeout
        pendingTimeout = false
        return t
    }

    /** 重置状态，开始新的语音段检测 */
    fun reset() {
        isInSpeech = false
        lastVoiceTimeMs = 0L
        speechStartTimeMs = 0L
        pendingTimeout = false
    }

    /**
     * 动态调整静音阈值
     * 可在应用启动时采样环境噪声，自适应设置阈值
     * @param noiseLevel 环境噪声 RMS 值
     */
    fun adjustThreshold(noiseLevel: Double) {
        silenceEnergyThreshold = maxOf(noiseLevel * 3, AsrConfig.VAD_SILENCE_THRESHOLD)
    }

    companion object {
        /**
         * 计算 PCM 16-bit 数据的 RMS（均方根）能量
         * RMS 反映音频信号的整体能量水平
         */
        private fun calculateRms(buffer: ByteArray, bytesRead: Int): Double {
            if (bytesRead < 2) return 0.0
            var sum = 0L
            val sampleCount = bytesRead / 2
            for (i in 0 until sampleCount) {
                val lo = buffer[i * 2].toInt() and 0xFF
                val hi = buffer[i * 2 + 1].toInt() shl 8
                val sample = (lo or hi).toShort().toInt()
                sum += sample.toLong() * sample.toLong()
            }
            return Math.sqrt(sum.toDouble() / sampleCount)
        }
    }
}
