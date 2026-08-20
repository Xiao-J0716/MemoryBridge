package com.memorybridge.tts

import android.content.Context
import android.media.MediaPlayer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import com.memorybridge.net.ApiClient
import com.memorybridge.net.TtsRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.util.Locale
import kotlin.coroutines.resume

/**
 * TTS 管理器
 *
 * 双通道语音合成，自动切换：
 * - 在线：调用云端 edge-tts API，音质更好，支持多种音色
 * - 离线：使用 Android 原生 TextToSpeech，无需网络
 *
 * 切换逻辑：先尝试在线 TTS，失败则降级到离线 TTS
 */
object TtsManager {
    private const val TAG = "TtsManager"

    private var androidTts: TextToSpeech? = null
    private var isTtsReady = false
    private var appContext: Context? = null

    // 在线 TTS 音频播放器（edge-tts 返回 MP3，用 MediaPlayer 播放）
    private var mediaPlayer: MediaPlayer? = null
    private var currentTempFile: File? = null

    fun init(context: Context) {
        appContext = context.applicationContext
        androidTts = TextToSpeech(context.applicationContext) { status ->
            if (status == TextToSpeech.SUCCESS) {
                // 设置中文语音
                val result = androidTts?.setLanguage(Locale.SIMPLIFIED_CHINESE)
                isTtsReady = result != TextToSpeech.LANG_MISSING_DATA &&
                    result != TextToSpeech.LANG_NOT_SUPPORTED
                // 老人语速稍慢，便于理解
                androidTts?.setSpeechRate(0.9f)
                Log.i(TAG, "Android TTS 初始化完成, ready=$isTtsReady")
            } else {
                Log.e(TAG, "Android TTS 初始化失败: $status")
            }
        }
    }

    /** 检测是否可以使用在线 TTS */
    private suspend fun isOnline(): Boolean = withContext(Dispatchers.IO) {
        ApiClient.isNetworkAvailable()
    }

    /**
     * 播放语音（自动选择在线/离线）
     * @param text 待播放文本
     * @param onCompleted 播放完成回调
     */
    suspend fun speak(text: String, onCompleted: () -> Unit = {}) {
        if (text.isBlank()) {
            onCompleted()
            return
        }
        if (isOnline()) {
            val success = speakOnline(text, onCompleted)
            if (!success) {
                speakOffline(text, onCompleted)
            }
        } else {
            speakOffline(text, onCompleted)
        }
    }

    /**
     * 在线 TTS：调用云端 edge-tts API
     * 云端使用微软 edge-tts，音质更好，支持多种中文音色
     */
    private suspend fun speakOnline(text: String, onCompleted: () -> Unit): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val response = ApiClient.chatApi.generateTts(
                    TtsRequest(text = text, voice = "zh-CN-XiaoxiaoNeural", rate = "-10%")
                )
                if (response.isSuccessful) {
                    val audioBytes = response.body()?.bytes()
                    if (audioBytes != null && audioBytes.isNotEmpty()) {
                        playAudioBytes(audioBytes, onCompleted)
                        true
                    } else {
                        Log.w(TAG, "在线 TTS 返回空音频")
                        false
                    }
                } else {
                    Log.w(TAG, "在线 TTS 请求失败: ${response.code()}")
                    false
                }
            } catch (e: Exception) {
                Log.e(TAG, "在线 TTS 失败，降级到离线", e)
                false
            }
        }
    }

    /**
     * 离线 TTS：Android 原生 TextToSpeech
     * 无需网络，但音质一般
     */
    private suspend fun speakOffline(text: String, onCompleted: () -> Unit) {
        if (!isTtsReady) {
            Log.e(TAG, "离线 TTS 未就绪")
            onCompleted()
            return
        }
        withContext(Dispatchers.Main) {
            androidTts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}
                override fun onDone(utteranceId: String?) { onCompleted() }
                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) { onCompleted() }
            })
            androidTts?.speak(
                text,
                TextToSpeech.QUEUE_FLUSH,
                null,
                "tts_${System.currentTimeMillis()}"
            )
        }
    }

    /**
     * 播放在线 TTS 返回的音频字节
     *
     * 实现流程：
     * 1. 将 edge-tts 返回的 MP3 字节数据写入临时文件（IO 线程）
     * 2. 使用 MediaPlayer 播放临时文件（主线程，因为回调需要 Looper）
     * 3. 播放完成后（或出错时）删除临时文件并回调 onCompleted
     *
     * 关键设计：
     * - 文件写入在 IO 线程（磁盘 I/O 密集）
     * - MediaPlayer 操作在主线程（OnCompletionListener/OnErrorListener
     *   回调需要 Looper，IO 线程没有 Looper 会导致回调不触发）
     * - 使用 suspendCancellableCoroutine 将回调转换为协程挂起点
     *
     * @param audioBytes edge-tts 返回的 MP3 音频数据
     * @param onCompleted 播放完成回调
     */
    private suspend fun playAudioBytes(audioBytes: ByteArray, onCompleted: () -> Unit) {
        val context = appContext ?: run {
            Log.e(TAG, "Context 为空，无法播放音频")
            onCompleted()
            return
        }
        // 清理上一次的播放资源（防止叠加播放）
        cleanupMediaPlayer()

        try {
            // 1. 写入临时文件（在当前 IO 线程执行，磁盘写入）
            currentTempFile = File.createTempFile("tts_", ".mp3", context.cacheDir)
            FileOutputStream(currentTempFile!!).use { it.write(audioBytes) }
            Log.d(TAG, "TTS 音频临时文件: ${currentTempFile!!.absolutePath}, size=${audioBytes.size}")

            // 2. MediaPlayer 操作切换到主线程
            //    MediaPlayer 的 OnCompletionListener / OnErrorListener 回调
            //    依赖 Looper 投递消息，IO 线程没有 Looper 会导致回调永远不触发
            withContext(Dispatchers.Main) {
                mediaPlayer = MediaPlayer()
                mediaPlayer!!.setDataSource(currentTempFile!!.absolutePath)

                // 使用挂起协程等待 MediaPlayer 播放完成
                suspendCancellableCoroutine<Unit> { cont ->
                    mediaPlayer!!.setOnPreparedListener { mp ->
                        // prepare 完成，开始播放
                        mp.start()
                        Log.d(TAG, "开始播放在线 TTS 音频")
                    }

                    mediaPlayer!!.setOnCompletionListener { mp ->
                        Log.d(TAG, "在线 TTS 播放完成")
                        cleanupMediaPlayer()
                        if (cont.isActive) cont.resume(Unit)
                        onCompleted()
                    }

                    mediaPlayer!!.setOnErrorListener { mp, what, extra ->
                        Log.e(TAG, "MediaPlayer 错误: what=$what, extra=$extra")
                        cleanupMediaPlayer()
                        if (cont.isActive) cont.resume(Unit)
                        onCompleted()
                        true // 表示错误已处理
                    }

                    try {
                        // 同步 prepare：本地小文件 prepare 很快（通常 <100ms）
                        // prepare 后 OnPreparedListener 会被同步调用 -> start()
                        mediaPlayer!!.prepare()
                    } catch (e: Exception) {
                        Log.e(TAG, "MediaPlayer prepare 失败", e)
                        cleanupMediaPlayer()
                        if (cont.isActive) cont.resume(Unit)
                        onCompleted()
                    }

                    // 协程被取消时，停止并释放 MediaPlayer
                    cont.invokeOnCancellation {
                        Log.d(TAG, "播放被取消")
                        cleanupMediaPlayer()
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "播放音频失败", e)
            cleanupMediaPlayer()
            onCompleted()
        }
    }

    /** 清理 MediaPlayer 和临时文件资源 */
    private fun cleanupMediaPlayer() {
        try {
            mediaPlayer?.let { mp ->
                if (mp.isPlaying) mp.stop()
                mp.reset()
                mp.release()
            }
        } catch (e: Exception) {
            Log.w(TAG, "释放 MediaPlayer 时异常", e)
        }
        mediaPlayer = null

        currentTempFile?.let { f ->
            if (f.exists()) {
                f.delete()
                Log.d(TAG, "已删除临时文件: ${f.name}")
            }
        }
        currentTempFile = null
    }

    /** 停止当前播放（在线 MediaPlayer + 离线 Android TTS） */
    fun stop() {
        androidTts?.stop()
        cleanupMediaPlayer()
    }

    /** 释放所有 TTS 资源 */
    fun release() {
        androidTts?.stop()
        androidTts?.shutdown()
        androidTts = null
        cleanupMediaPlayer()
    }
}
