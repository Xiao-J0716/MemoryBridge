package com.memorybridge.audio

import android.media.AudioRecord
import android.util.Log
import java.io.ByteArrayOutputStream
import kotlin.concurrent.thread

/**
 * AudioRecord 封装，采集 PCM 音频数据
 *
 * 工作流程：
 * 1. start() -> 初始化 AudioRecord 并启动后台录音线程
 * 2. 后台线程循环读取 PCM 数据，通过 onAudioData 回调输出
 * 3. stop() -> 停止录音并释放资源
 *
 * 双通道支持：
 * - onAudioData 回调 → 送入 Vosk 离线识别（实时）
 * - 内部 audioBuffer → 缓存 PCM 数据，句末提取送云端精修（在线 ASR）
 */
class AudioRecorder(
    private val onAudioData: (buffer: ByteArray, bytesRead: Int) -> Unit,
) {
    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var recordThread: Thread? = null

    /** 音频缓冲区：缓存当前句子的 PCM 数据，用于在线 ASR 精修 */
    private val audioBuffer = ByteArrayOutputStream()

    /**
     * 启动录音
     * @return true 启动成功，false 启动失败（权限缺失或初始化错误）
     */
    fun start(): Boolean {
        val minBufferSize = AudioRecord.getMinBufferSize(
            AudioConfig.SAMPLE_RATE,
            AudioConfig.CHANNEL_CONFIG,
            AudioConfig.AUDIO_FORMAT,
        )
        val bufferSize = maxOf(
            minBufferSize * AudioConfig.BUFFER_FACTOR,
            AudioConfig.READ_CHUNK_BYTES,
        )
        return try {
            audioRecord = AudioRecord(
                AudioConfig.AUDIO_SOURCE,
                AudioConfig.SAMPLE_RATE,
                AudioConfig.CHANNEL_CONFIG,
                AudioConfig.AUDIO_FORMAT,
                bufferSize,
            )
            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord 初始化失败")
                audioRecord?.release()
                audioRecord = null
                return false
            }
            isRecording = true
            audioBuffer.reset()
            audioRecord?.startRecording()
            recordThread = thread(name = "AudioRecorder") { recordingLoop() }
            Log.i(TAG, "录音已启动, bufferSize=$bufferSize")
            true
        } catch (e: SecurityException) {
            Log.e(TAG, "缺少录音权限", e)
            false
        } catch (e: Exception) {
            Log.e(TAG, "启动录音失败", e)
            false
        }
    }

    /** 录音线程主循环：持续读取 PCM 数据并回调 */
    private fun recordingLoop() {
        val buffer = ByteArray(AudioConfig.READ_CHUNK_BYTES)
        while (isRecording) {
            val readBytes = audioRecord?.read(buffer, 0, buffer.size) ?: -1
            if (readBytes > 0) {
                val chunk = buffer.copyOf(readBytes)
                // 1. 送入 ASR 引擎（Vosk 实时识别）
                onAudioData(chunk, readBytes)
                // 2. 同时缓存到缓冲区（供在线 ASR 精修使用）
                synchronized(audioBuffer) {
                    audioBuffer.write(chunk, 0, readBytes)
                }
            }
        }
    }

    /**
     * 获取当前缓冲的 PCM 数据并清空缓冲区
     *
     * 在一句话结束时调用，提取当前句子的音频用于在线 ASR。
     * 提取后自动清空缓冲区，开始缓存下一句。
     *
     * @return 当前句子的 PCM 数据，如果缓冲区为空返回 null
     */
    fun drainBufferedPcm(): ByteArray? {
        synchronized(audioBuffer) {
            if (audioBuffer.size() == 0) return null
            val pcm = audioBuffer.toByteArray()
            audioBuffer.reset()
            return pcm
        }
    }

    /**
     * 获取当前缓冲的 PCM 数据的 WAV 格式（不清空缓冲区）
     *
     * @return WAV 格式字节数组，缓冲区为空返回 null
     */
    fun getBufferedWav(): ByteArray? {
        synchronized(audioBuffer) {
            if (audioBuffer.size() == 0) return null
            return WavUtils.pcmToWav(audioBuffer.toByteArray())
        }
    }

    /** 清空音频缓冲区 */
    fun clearBuffer() {
        synchronized(audioBuffer) {
            audioBuffer.reset()
        }
    }

    /** 停止录音并释放资源 */
    fun stop() {
        if (!isRecording) return
        isRecording = false
        recordThread?.join(500)
        recordThread = null
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        clearBuffer()
        Log.i(TAG, "录音已停止")
    }

    companion object {
        private const val TAG = "AudioRecorder"
    }
}
