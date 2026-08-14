package com.memorybridge.asr

import android.content.Context
import android.util.Log
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream

/**
 * 语音识别接口 - 抽象 Vosk SDK
 * 通过接口抽象，使得在 Vosk SDK 未引入时项目可编译运行
 */
interface SpeechRecognizer {
    /** 初始化模型，成功返回 true */
    fun init(context: Context, modelPath: String): Boolean

    /** 开始识别 */
    fun start()

    /** 停止识别 */
    fun stop()

    /** 释放资源 */
    fun release()

    /** 识别结果流 */
    val results: SharedFlow<AsrResult>
}

/**
 * Vosk 离线语音识别管理器（单例）
 *
 * ===== Vosk SDK 集成指南 =====
 *
 * 1. 引入 SDK：
 *    - 方式A: 从 https://github.com/alphacep/vosk-android/releases
 *      下载 vosk-android-0.3.47.aar 放入 app/libs/
 *      app/build.gradle.kts 添加: implementation(files("libs/vosk-android-0.3.47.aar"))
 *    - 方式B: 通过 JitPack
 *      implementation("com.github.alphacep:vosk-android:0.3.47")
 *
 * 2. 下载模型：
 *    - 从 https://alphacephei.com/vosk/models 下载 vosk-model-small-cn-0.22 (42MB)
 *    - 解压后放入 app/src/main/assets/models/vosk-model-small-cn-0.22/
 *
 * 3. Vosk 关键类说明：
 *    - org.vosk.Model: 加载离线模型文件夹
 *    - org.vosk.Recognizer: 识别器，acceptWaveForm() 接收 PCM 数据
 *      - partialResult: 返回 {"partial": "部分文字"} JSON
 *      - result: 返回 {"text": "完整文字"} JSON
 *
 * 4. 本项目采用手动喂数据方式（而非 SpeechService 内置录音）：
 *    - AudioRecorder 采集 PCM -> feedAudioData() -> recognizer.acceptWaveForm()
 *    - 这样可以与自定义 VAD 策略配合，实现 3-4 秒静音超时
 */
object SpeechRecognizerManager : SpeechRecognizer {

    private const val TAG = "SpeechRecognizer"
    private const val MODEL_NAME = "vosk-model-small-cn-0.22"

    // Vosk SDK 对象（引入 AAR 后直接可用）
    private var model: org.vosk.Model? = null
    private var recognizer: org.vosk.Recognizer? = null

    private var isInitialized = false
    private var isRecognizing = false
    private var vadStrategy: VadStrategy? = null
    private var lastPartialText: String = ""

    private val _results = MutableSharedFlow<AsrResult>(extraBufferCapacity = 64)
    override val results: SharedFlow<AsrResult> = _results.asSharedFlow()

    override fun init(context: Context, modelPath: String): Boolean {
        return try {
            // 从 assets 解压模型到内部存储（Vosk 需要文件系统路径，不能直接读 assets）
            val modelDir = extractModelFromAssets(context, MODEL_NAME)
            Log.i(TAG, "模型解压完成: $modelDir")

            // 加载 Vosk 模型（耗时操作，应在后台线程调用）
            model = org.vosk.Model(modelDir)
            // 创建识别器，采样率必须与 AudioRecord 一致（16000Hz）
            recognizer = org.vosk.Recognizer(model, 16000.0f)
            // 启用词级时间戳（可用于分析老人语速和停顿）
            recognizer?.setWords(true)

            vadStrategy = VadStrategy()
            isInitialized = true
            Log.i(TAG, "Vosk 模型初始化成功")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Vosk 模型初始化失败", e)
            _results.tryEmit(AsrResult.Error("模型加载失败: ${e.message}"))
            false
        }
    }

    override fun start() {
        if (!isInitialized || isRecognizing) return
        isRecognizing = true
        lastPartialText = ""
        vadStrategy?.reset()
        // 重置识别器，清空上一轮的缓存
        recognizer?.reset()
        Log.i(TAG, "启动 Vosk 识别")
        _results.tryEmit(AsrResult.Started)
    }

    /**
     * 接收原始 PCM 音频数据并送入识别器
     * 由 AudioRecorder 的 onAudioData 回调调用
     *
     * @param buffer PCM 16-bit 数据
     * @param bytesRead 有效字节数
     */
    fun feedAudioData(buffer: ByteArray, bytesRead: Int) {
        if (!isRecognizing) return
        val rec = recognizer ?: return

        // 将 PCM 数据送入 Vosk 识别器
        // acceptWaveForm 返回 true 表示检测到句子结束（静音超时）
        // 返回 false 表示还在同一句中
        val isEndOfSentence = rec.acceptWaveForm(buffer, bytesRead)

        if (isEndOfSentence) {
            // 句子结束，获取最终识别结果
            val resultJson = rec.result
            val text = parseResultText(resultJson)
            if (text.isNotBlank()) {
                Log.d(TAG, "最终识别: $text")
                _results.tryEmit(AsrResult.Final(text))
                lastPartialText = ""
            }
        } else {
            // 句子进行中，获取部分识别结果（实时显示）
            val partialJson = rec.partialResult
            val partialText = parsePartialText(partialJson)
            if (partialText.isNotBlank() && partialText != lastPartialText) {
                Log.d(TAG, "部分识别: $partialText")
                _results.tryEmit(AsrResult.Partial(partialText))
                lastPartialText = partialText
            }
        }

        // VAD 检测：判断是否静音超时（补充 Vosk 自身端点检测的不足）
        vadStrategy?.onAudioFrame(buffer, bytesRead) { isSilent ->
            if (isSilent && vadStrategy?.isTimeout() == true) {
                // 静音超时，如果有 partial 文本则作为最终结果提交
                if (lastPartialText.isNotBlank()) {
                    _results.tryEmit(AsrResult.Final(lastPartialText))
                    lastPartialText = ""
                }
                _results.tryEmit(AsrResult.Timeout)
                vadStrategy?.reset()
            }
        }
    }

    override fun stop() {
        if (!isRecognizing) return
        isRecognizing = false
        // 停止前获取最终识别结果
        val rec = recognizer
        if (rec != null) {
            val finalJson = rec.result
            val text = parseResultText(finalJson)
            if (text.isNotBlank()) {
                _results.tryEmit(AsrResult.Final(text))
            }
            // 如果没有最终结果但有 partial，提交 partial
            if (text.isBlank() && lastPartialText.isNotBlank()) {
                _results.tryEmit(AsrResult.Final(lastPartialText))
            }
        }
        lastPartialText = ""
        Log.i(TAG, "停止 Vosk 识别")
        _results.tryEmit(AsrResult.Stopped)
    }

    override fun release() {
        stop()
        recognizer?.close()
        model?.close()
        recognizer = null
        model = null
        isInitialized = false
        Log.i(TAG, "Vosk 资源已释放")
    }

    // ============================================================
    //  模型文件管理
    // ============================================================

    /**
     * 从 assets 解压模型到内部存储
     * Vosk Model 需要文件系统路径，不能直接从 assets 读取
     *
     * @param context 应用上下文
     * @param modelName 模型文件夹名（如 vosk-model-small-cn-0.22）
     * @return 解压后的模型目录绝对路径
     */
    private fun extractModelFromAssets(context: Context, modelName: String): String {
        val targetDir = File(context.filesDir, "models/$modelName")
        // 如果已解压过且完整，直接返回
        if (targetDir.exists() && File(targetDir, "am/").exists()) {
            Log.i(TAG, "模型已存在，跳过解压: ${targetDir.absolutePath}")
            return targetDir.absolutePath
        }
        targetDir.mkdirs()
        // 递归复制 assets/models/modelName/ → filesDir/models/modelName/
        copyAssetDir(context, "models/$modelName", targetDir)
        return targetDir.absolutePath
    }

    /**
     * 递归复制 assets 目录到文件系统
     */
    private fun copyAssetDir(context: Context, assetPath: String, targetDir: File) {
        val assetManager = context.assets
        val children = assetManager.list(assetPath) ?: return
        if (children.isEmpty()) {
            // 是文件，直接复制
            copyAssetFile(context, assetPath, File(targetDir, assetPath.substringAfterLast('/')))
        } else {
            // 是目录，递归复制
            for (child in children) {
                val childAssetPath = "$assetPath/$child"
                val childTarget = File(targetDir, child)
                val subChildren = assetManager.list(childAssetPath)
                if (subChildren == null || subChildren.isEmpty()) {
                    copyAssetFile(context, childAssetPath, childTarget)
                } else {
                    childTarget.mkdirs()
                    copyAssetDir(context, childAssetPath, childTarget)
                }
            }
        }
    }

    /**
     * 复制单个 asset 文件到目标路径
     */
    private fun copyAssetFile(context: Context, assetPath: String, targetFile: File) {
        targetFile.parentFile?.mkdirs()
        var input: InputStream? = null
        var output: FileOutputStream? = null
        try {
            input = context.assets.open(assetPath)
            output = FileOutputStream(targetFile)
            val buffer = ByteArray(8192)
            var read: Int
            while (input.read(buffer).also { read = it } != -1) {
                output.write(buffer, 0, read)
            }
            output.flush()
        } catch (e: Exception) {
            Log.e(TAG, "复制模型文件失败: $assetPath", e)
        } finally {
            input?.close()
            output?.close()
        }
    }

    // ============================================================
    //  JSON 解析
    // ============================================================

    /**
     * 解析 Vosk 最终结果 JSON
     * 格式: {"text": "你好世界", "result": [...]}
     */
    private fun parseResultText(json: String): String {
        return try {
            val obj = JSONObject(json)
            obj.optString("text", "").trim()
        } catch (e: Exception) {
            Log.e(TAG, "解析最终结果 JSON 失败: $json", e)
            ""
        }
    }

    /**
     * 解析 Vosk 部分结果 JSON
     * 格式: {"partial": "你好"}
     */
    private fun parsePartialText(json: String): String {
        return try {
            val obj = JSONObject(json)
            obj.optString("partial", "").trim()
        } catch (e: Exception) {
            Log.e(TAG, "解析部分结果 JSON 失败: $json", e)
            ""
        }
    }
}
