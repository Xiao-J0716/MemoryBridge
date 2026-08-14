package com.memorybridge.audio

import android.media.AudioFormat
import android.media.MediaRecorder

/**
 * 音频采集配置常量
 * - 16kHz 采样率：Vosk 中文小模型要求的采样率
 * - 单声道：语音识别无需立体声
 * - PCM 16-bit：Vosk 标准输入格式
 * - VOICE_RECOGNITION 音频源：系统会自动应用降噪和增益
 */
object AudioConfig {
    /** 采样率 16000Hz，Vosk 模型要求 */
    const val SAMPLE_RATE = 16000

    /** 单声道输入 */
    val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO

    /** PCM 16-bit 编码 */
    val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT

    /** 音频源：VOICE_RECOGNITION，系统自动降噪 */
    val AUDIO_SOURCE = MediaRecorder.AudioSource.VOICE_RECOGNITION

    /** 缓冲区倍数，取系统最小值的倍数以避免欠运行 */
    const val BUFFER_FACTOR = 1

    /** 每帧字节数 = 2 bytes (16-bit) * 1 channel (mono) */
    const val BYTES_PER_FRAME = 2

    /** 每次读取的帧数（约 100ms 音频 @16kHz） */
    const val READ_CHUNK_FRAMES = 1600

    /** 每次读取的字节数 */
    const val READ_CHUNK_BYTES = READ_CHUNK_FRAMES * BYTES_PER_FRAME
}
