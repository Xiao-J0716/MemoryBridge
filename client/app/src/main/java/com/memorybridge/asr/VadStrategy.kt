package com.memorybridge.asr

/**
 * VAD（语音活动检测）策略
 *
 * 针对认知症老人特点优化：
 * - 语速慢，停顿多，常在句子中间停顿思考
 * - 静音超时从默认 1-2 秒延长到 3-4 秒（默认 3500ms），避免误截断
 * - 基于能量阈值（RMS）判断是否为静音
 * - 能量阈值可动态调整，适应不同环境噪声
 */
class VadStrategy(
    /** 静音超时时间（毫秒），默认 3500ms，老人语速慢需要更长 */
    private val silenceTimeoutMs: Long = DEFAULT_SILENCE_TIMEOUT_MS,
    /** 静音能量阈值（RMS），低于此值认为静音 */
    private var silenceEnergyThreshold: Double = DEFAULT_SILENCE_THRESHOLD,
    /** 最小说话时长（毫秒），避免短噪声误触发 */
    private val minSpeechMs: Long = DEFAULT_MIN_SPEECH_MS,
) {
    private var lastVoiceTimeMs: Long = 0L
    private var speechStartTimeMs: Long = 0L
    private var isInSpeech: Boolean = false

    /**
     * 处理一帧音频数据
     * @param buffer PCM 16-bit 数据
     * @param bytesRead 有效字节数
     * @param onSilence 回调：检测到静音时触发
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
            onSilence(false)
        } else {
            if (isInSpeech) {
                val silenceDuration = now - lastVoiceTimeMs
                if (silenceDuration > 200) {
                    // 超过 200ms 没有检测到语音能量
                    onSilence(true)
                }
                if (silenceDuration > silenceTimeoutMs) {
                    // 静音超时，结束当前语音段
                    isInSpeech = false
                }
            }
        }
    }

    /** 是否静音超时（当前语音段已结束） */
    fun isTimeout(): Boolean {
        if (!isInSpeech) return false
        val silenceDuration = System.currentTimeMillis() - lastVoiceTimeMs
        val speechDuration = lastVoiceTimeMs - speechStartTimeMs
        return silenceDuration > silenceTimeoutMs && speechDuration > minSpeechMs
    }

    /** 重置状态，开始新的语音段检测 */
    fun reset() {
        isInSpeech = false
        lastVoiceTimeMs = 0L
        speechStartTimeMs = 0L
    }

    /**
     * 动态调整静音阈值
     * 可在应用启动时采样环境噪声，自适应设置阈值
     * @param noiseLevel 环境噪声 RMS 值
     */
    fun adjustThreshold(noiseLevel: Double) {
        silenceEnergyThreshold = maxOf(noiseLevel * 3, DEFAULT_SILENCE_THRESHOLD)
    }

    companion object {
        /** 默认静音超时 3500ms（老人语速慢，比标准 1-2 秒更长） */
        const val DEFAULT_SILENCE_TIMEOUT_MS = 3500L

        /** 默认静音能量阈值 RMS */
        const val DEFAULT_SILENCE_THRESHOLD = 300.0

        /** 最小说话时长 300ms */
        const val DEFAULT_MIN_SPEECH_MS = 300L

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
