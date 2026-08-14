package com.memorybridge.asr

/**
 * ASR 识别模式
 *
 * 三种模式对应不同场景：
 * - OFFLINE_ONLY: 仅用 Vosk 离线识别，最快（毫秒级），无需网络，精度中等
 * - ONLINE_ONLY:  仅用云端 ASR，最准，需要网络，延迟较高（秒级）
 * - COARSE_TO_FINE: 先粗后精，Vosk 即时出粗结果，云端再出精结果替换
 */
enum class AsrMode {
    /** 仅离线：Vosk 实时识别，无需网络 */
    OFFLINE_ONLY,

    /** 仅在线：云端 ASR 精细识别，延迟较高 */
    ONLINE_ONLY,

    /** 先粗后精：Vosk 即时 + 云端精修，兼顾速度和精度 */
    COARSE_TO_FINE,
}
