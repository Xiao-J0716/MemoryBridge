package com.memorybridge.asr

/**
 * ASR 识别结果密封类
 * 通过 SharedFlow 分发给 ViewModel
 */
sealed class AsrResult {
    /** 部分识别结果（实时显示，随语音持续更新） */
    data class Partial(val text: String) : AsrResult()

    /** 最终识别结果（一句话说完后输出，来自 Vosk 离线识别） */
    data class Final(val text: String) : AsrResult()

    /** 精修识别结果（云端 ASR 返回，替换 Final 的粗结果） */
    data class Refined(val text: String, val source: String = "cloud") : AsrResult()

    /** 静音超时，用户停顿超过阈值 */
    data object Timeout : AsrResult()

    /** 识别错误 */
    data class Error(val message: String) : AsrResult()

    /** 识别已开始 */
    data object Started : AsrResult()

    /** 识别已停止 */
    data object Stopped : AsrResult()
}
