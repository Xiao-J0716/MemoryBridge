package com.memorybridge.asr

/**
 * ASR 调优参数集中处。
 *
 * 把 VAD（语音活动检测）相关阈值从 VadStrategy 的散落默认值集中到这里，
 * 调优时只改一处即全链路生效（SpeechRecognizerManager 与 AsrCoordinator 共用）。
 *
 * 数值针对认知症老人场景：
 * - 语速慢、句中停顿多，静音超时比标准 1–2s 更长（默认 3500ms）。
 * - 阈值基于 PCM 16-bit RMS，300 为经验值，可用 VadStrategy.adjustThreshold 按环境噪声自适应。
 */
object AsrConfig {
    /** VAD 静音超时（ms）。调优区间 2000–5000，默认 3500（老人语速慢）。 */
    const val VAD_SILENCE_TIMEOUT_MS = 3500L

    /** VAD 静音能量阈值（RMS）。低于此值视为静音。 */
    const val VAD_SILENCE_THRESHOLD = 300.0

    /** 最小说话时长（ms），过滤短噪声误触发。 */
    const val VAD_MIN_SPEECH_MS = 300L
}
