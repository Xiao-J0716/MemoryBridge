package com.memorybridge.audio

import java.io.ByteArrayOutputStream

/**
 * WAV 音频工具：将 PCM 原始数据包装为标准 WAV 格式
 *
 * WAV 文件结构（PCM 16-bit）：
 *   RIFF header (12 bytes)
 *   fmt  chunk  (24 bytes)
 *   data chunk  (8 bytes header + audio data)
 *
 * 服务端 ASR 接口要求 WAV 格式输入
 */
object WavUtils {

    /**
     * 将 PCM 字节数据包装为 WAV 格式
     *
     * @param pcmData 原始 PCM 16-bit 数据
     * @param sampleRate 采样率（默认 16000，与 AudioConfig 一致）
     * @param channels 声道数（默认 1 = 单声道）
     * @param bitsPerSample 每样本位数（默认 16）
     * @return 完整的 WAV 文件字节数组
     */
    fun pcmToWav(
        pcmData: ByteArray,
        sampleRate: Int = AudioConfig.SAMPLE_RATE,
        channels: Int = 1,
        bitsPerSample: Int = 16,
    ): ByteArray {
        val byteRate = sampleRate * channels * bitsPerSample / 8
        val blockAlign = channels * bitsPerSample / 8
        val dataSize = pcmData.size
        val chunkSize = 36 + dataSize // 36 = 文件头减去 RIFF 头的前 8 字节

        val wav = ByteArrayOutputStream(dataSize + 44)
        // RIFF header
        wav.write("RIFF".toByteArray())
        writeIntLE(wav, chunkSize)
        wav.write("WAVE".toByteArray())
        // fmt chunk
        wav.write("fmt ".toByteArray())
        writeIntLE(wav, 16) // fmt chunk 大小固定 16
        writeShortLE(wav, 1) // PCM = 1
        writeShortLE(wav, channels)
        writeIntLE(wav, sampleRate)
        writeIntLE(wav, byteRate)
        writeShortLE(wav, blockAlign)
        writeShortLE(wav, bitsPerSample)
        // data chunk
        wav.write("data".toByteArray())
        writeIntLE(wav, dataSize)
        wav.write(pcmData)

        return wav.toByteArray()
    }

    /** 写入小端 32 位整数 */
    private fun writeIntLE(out: ByteArrayOutputStream, value: Int) {
        out.write(value and 0xFF)
        out.write((value shr 8) and 0xFF)
        out.write((value shr 16) and 0xFF)
        out.write((value shr 24) and 0xFF)
    }

    /** 写入小端 16 位整数 */
    private fun writeShortLE(out: ByteArrayOutputStream, value: Int) {
        out.write(value and 0xFF)
        out.write((value shr 8) and 0xFF)
    }
}
