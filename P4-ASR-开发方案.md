# P4 客户端·ASR+音频 完整开发方案

> 范围：`app/client/` 下 ASR + 音频链路（Kotlin / Vosk Android SDK / AudioRecord）
> 周期：8/20–8/23（4 天）｜交付：Vosk 中文模型可用 + 录音识别链路调通 + VAD 调优报告 + ASR 准确率数据

---

## 一、现状评估（代码已通读，脚手架完成度约 90%）

P4 相关代码框架已基本写好，**主要缺的是“接线”和“真机验证”**，不是从零开发。逐文件状态：

| 文件 | 状态 | 说明 |
|------|------|------|
| `asr/SpeechRecognizerManager.kt` | ✅ 已实现，⚠️ 无法编译 | 直接引用 `org.vosk.Model/Recognizer`，AAR 未引入则报红；含 assets 解压、喂数据、VAD、JSON 解析 |
| `asr/AsrCoordinator.kt` | ✅ 已实现 | 三模式（OFFLINE_ONLY / ONLINE_ONLY / COARSE_TO_FINE）协调器，逻辑完整 |
| `asr/AsrMode.kt` / `AsrResult.kt` | ✅ 已实现 | 枚举与密封结果类，无需改 |
| `asr/OnlineAsrClient.kt` | ✅ 已实现 | PCM→WAV→multipart 上传 `/api/asr`，超时 10s 静默降级 |
| `asr/VadStrategy.kt` | ✅ 已实现，⚠️ 触发脆弱 | RMS 能量 VAD，默认 3500ms 超时；超时判定依赖两次 `System.currentTimeMillis()` 一致 |
| `audio/AudioRecorder.kt` | ✅ 已实现 | VOICE_RECOGNITION 源 / 16k 单声道 16bit，双通道（喂 Vosk + 缓存 PCM 供精修） |
| `audio/AudioConfig.kt` / `WavUtils.kt` | ✅ 已实现 | 采样常量 + PCM→WAV 封装，无需改 |
| `offline/OfflineTemplateEngine.kt` | ✅ 已实现 | 恰好 8 个场景模板 + 兜底，满足 day3 任务，仅需验证 |
| `ui/ChatViewModel.kt` | ✅ 已接线 | 观察 AsrResult、在线/离线切换、TTS 播放全通（P5 负责，P4 保证事件正确） |
| `build.gradle.kts` | ❌ Vosk 依赖被注释 | 第 77–82 行 TODO，`org.vosk.*` 解析不到 → **项目无法编译** |
| `assets/models/` | ❌ 为空 | 模型未下载 |
| `AndroidManifest.xml` | ⚠️ 权限声明有，运行时未请求 | `RECORD_AUDIO` 已声明，但 6.0+ 需运行时授权 |
| `MainActivity.kt` | ⚠️ 无权限请求 | 只 `setContent{ChatScreen()}`，点录音必抛 SecurityException |

### 1.1 必须当场修掉的 4 个阻断点

1. **编译阻断（day1 头等）**：`build.gradle.kts` Vosk 依赖注释 → 整个客户端编不过。
2. **模型缺失**：`assets/models/` 空，Vosk 初始化会失败。
3. **运行时录音权限缺失（计划里没写，但会卡死整条链路）**：`MainActivity`/`ChatScreen` 没有请求 `RECORD_AUDIO` 运行时权限。minSdk=26，全新安装时权限未授予，`AudioRecord` 构造抛 `SecurityException` → `AudioRecorder.start()` 返回 false → 仅弹一句“无法启动录音，请检查权限”。**不补这步，day2 录音永远录不进去。**
4. **VAD 触发脆弱 + 参数不可配**：超时只在“单帧跨阈值”那一帧触发，且 `isTimeout()` 重新读时钟，与 `onAudioFrame` 的 `now` 有几 ms 偏差就可能漏触发；3500ms 硬编码在 `VadStrategy` 默认值里，调优要改多处。

### 1.2 需要知晓但不归 P4 修的点

- **服务端 ASR 后端 = `simple`（Google Web API）**（`server/.env`）。中国大陆网络不可达 → `/api/asr` 永远返回空文本 → 客户端“精修”永远拿不到结果，自动降级保留 Vosk 粗结果（功能不挂，但“先粗后精”演示无意义）。要让精修真正提升准确率，需 P1/P2 把 `ASR_BACKEND` 切到本地 `whisper`/`funasr`（较重）。day2 联调前向 P1/P2 确认。
- **`ApiClient.BASE_URL = http://192.168.1.100:8000/`** 硬编码（P5 范畴）。P4 联调精修前需对齐本机 IP。
- **`AndroidManifest` 锁 `portrait`**，P3 要改平板横屏——不归 P4。

---

## 二、4 天任务分解（精确到文件 / 可执行）

### Day 1 — 8/20（周四）：环境就绪 + 编译通过 + 模型解压验证

**目标：客户端能装上平板、点按钮不崩、Logcat 看到“Vosk 模型初始化成功”。**

1. **引入 Vosk AAR（AAR-in-libs 优先，最稳）**
   - 到 `https://github.com/alphacep/vosk-android/releases` 下载 `vosk-android-0.3.47.aar`（代码与注释里已用此版本；若 release 有更新版可取最新，方法名兼容）。
   - 新建 `app/client/app/libs/`，把 aar 放进去。
   - `app/build.gradle.kts` 第 77–82 行 TODO 替换为：
     ```kotlin
     // Vosk SDK - 离线语音识别（AAR 本地引入，避免 JitPack 原生库构建不稳）
     implementation(files("libs/vosk-android-0.3.47.aar"))
     ```
   - 备选（JitPack，已在 `settings.gradle.kts` 配好 `maven("https://jitpack.io")`）：
     ```kotlin
     implementation("com.github.alphacep:vosk-android:0.3.47")
     ```
     若 JitPack 构建原生库失败（历史常见），回退 AAR-in-libs。
   - `proguard-rules.pro` 已含 `-keep class org.vosk.** { *; }` 和 `com.sun.jna.**`，无需改（release 当前 `isMinifyEnabled=false` 也没启用）。

2. **下载并放置中文模型**
   - 下载：`https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip`（约 42MB，Apache-2.0，官方标注“Lightweight model for Android and RPi”）。
   - 解压后得到 `vosk-model-small-cn-0.22/`（含 `am/ conf/ graph/ ivector/` 等）。
   - 放到 `app/client/app/src/main/assets/models/vosk-model-small-cn-0.22/`（即让 `assets/models/vosk-model-small-cn-0.22/am/` 存在）。目录若不存在先建 `assets/models/`。
   - 注意：42MB 进 assets 会使 APK 增大约 30–42MB、首次启动解压到 `filesDir/models/` 需 1–3s（`ChatViewModel` 已有 `isAsrLoading` 转圈，够用）。Demo 阶段可接受。

3. **补运行时录音权限（阻断点 3）**
   - 在 `ChatScreen.kt` 顶层加 `rememberLauncherForActivityResult`，点“开始说话”前检查并请求 `RECORD_AUDIO`，授权后再 `viewModel.startListening()`。详见 §3.2 代码。
   - 这一步建议 P4 自己落（直接卡 ASR 链路），和 P5 打个招呼即可。

4. **验证初始化 + 模型解压**
   - 编译安装到平板。
   - 观察 Logcat tag `SpeechRecognizer` / `ChatViewModel`：应看到 `模型解压完成: /data/.../models/vosk-model-small-cn-0.22` 与 `Vosk 模型初始化成功`。
   - `ChatScreen` 底部应从“正在准备语音识别”转成“点击下方按钮开始说话”（`isAsrReady=true`）。
   - 若报 `模型加载失败`：多为 assets 路径错（检查 `assets/models/vosk-model-small-cn-0.22/am/` 是否存在）或 aar 版本 API 不匹配。

**Day1 验收**：装机能进主界面、ASR 就绪、点按钮能触发权限弹窗；Logcat 见模型加载成功。

### Day 2 — 8/21（周五）：录音→Vosk→文本链路 + VAD 调优 + WAV 精修

1. **调通录音→识别→文本**
   - 授权后点按钮 → 说“你好” → `AsrResult.Partial` 实时上屏（底部状态“正在听…”变文字）→ 停顿后 `AsrResult.Final` 进消息列表。
   - 串不通的常见原因：权限没授（回 day1）、`AudioRecord` 用了模拟器无麦克风（用真机/平板）、`VOICE_RECOGNITION` 源在某些 ROM 降噪过强（可临时换 `MIC` 对比）。

2. **VAD 超时调优（3500ms → 测老人语速）**
   - 先做 §3.3 把超时参数集中到一处可改。
   - 测试矩阵（同一段老人慢速语音，句中停顿 2–4s）：

     | 超时 | 预期表现 | 判定 |
     |------|----------|------|
     | 2000ms | 句中停顿易被误截断 | 偏短 |
     | 3500ms（默认） | 多数句中停顿能撑住 | 基线 |
     | 5000ms | 几乎不误截断，但响应变慢 | 偏长 |

   - 记录“误截断次数 / 漏触发次数 / 平均响应延迟”，选误截断=0 且延迟可接受的最小值。预期落点 3500–4500ms。
   - 顺带验证 Vosk 自带端点检测与自定义 VAD 的协作：`acceptWaveForm` 返回 true 时已出 Final（Vosk 端点），自定义 VAD 是兜底（处理 Vosk 不出端点但人已说完）。若 Vosk 端点偏早，可用 `recognizer?.setEndpointerDelays(tStart, tEnd)` 调（day2 可选）。
   - 同时做 §3.4 加固 VAD 触发，避免漏触发。

3. **验证 WAV 封装用于云端精修**
   - 联调前先和 P5 对齐 `BASE_URL` 为本机局域网 IP。
   - `OnlineAsrClient.recognize()` 会把缓冲 PCM 经 `WavUtils.pcmToWav` 封装后 multipart 上传 `/api/asr`。
   - 服务端 `asr.py._parse_wav_header` 用 Python `wave` 解析；客户端生成的是标准 RIFF/WAVE/fmt/data，已对齐。
   - 抓包/Logcat 确认：上传成功返回 `backend` 与 `text`；若服务端 `ASR_BACKEND=simple` 且无外网，会返回空 → 客户端保留粗结果（预期降级）。向 P1/P2 确认是否切 `whisper` 以演示真实精修提升。

**Day2 验收**：能完整“点按钮→说话→出文字→停顿自动结束”；VAD 超时选定一个值；WAV 上传链路通（或确认降级符合预期）。

### Day 3 — 8/22（周六）：离线模板验证 + 10 句准确率 + P5 联调

1. **验证 OfflineTemplateEngine（8 场景）**
   - 代码已是 8 个模板（问候/吃饭/家人/身体/日期/感谢/寂寞/回忆）+ 兜底，**只需测**：断网状态下说各场景关键词，确认命中对应回复、无命中走兜底。
   - 可补强：加几条老人高频但当前缺的词（如“吃药”“睡觉”“冷/热”“孙子里短句”），但仍保持 8 个主场景，不破坏“8 场景”交付口径。

2. **10 句常用语准确率测试**
   - 用 §4 的 10 句测试集（含 demo 用的“我叫张奶奶，我喜欢喝小米粥”），每句念 1–2 遍。
   - 记录：识别文本、字错率（CER）、首 partial 延迟、final 延迟。
   - 期望：Vosk small-cn-0.22 在干净朗读下字准确率约 80–90%，老人/方言/含噪会下降——这正是“先粗后精”的价值，报告里如实写并展示精修前后对比（若服务端有可用后端）。

3. **配合 P5 联调**
   - P4 保证 `AsrCoordinator` 事件流（Partial/Final/Refined/Timeout/Error/Started/Stopped）稳定；P5 负责 `ChatViewModel` 状态机串联。
   - 重点对齐：`Timeout` 时若有 partial 要提交、`Refined` 要替换最后一条用户粗消息（`updateLastUserMessage`，已实现）、离线时 `isOnline=false` 走模板。

**Day3 验收**：8 场景离线回复命中；10 句准确率数据成表；与 P5 跑通“说→识别→AI 回复→TTS”单轮。

### Day 4 — 8/23（周日）：ASR 测试报告 + Demo 配合

- 整理报告（§4 模板）：准确率表、延迟分布、VAD 三档对比结论、精修前后对比、已知限制（small 模型对方言/含噪弱、首启动解压耗时）。
- 配合 P5 录 Demo 语音交互；把 VAD 超时最终值固化进 `AsrConfig`。

---

## 三、关键代码改动（精确到文件）

### 3.1 `app/client/app/build.gradle.kts`（day1）

把第 77–82 行 TODO 段替换为 AAR 引入（见 §二 Day1.1）。其余不动。

### 3.2 运行时录音权限 — `ChatScreen.kt`（day1）

在 `ChatScreen` 顶层加 launcher，把权限检查包进 `onStartListening`。新增 import：

```kotlin
import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
```

`ChatScreen` 内（`val uiState by ...` 之后）加：

```kotlin
val context = LocalContext.current
val permissionLauncher = rememberLauncherForActivityResult(
    ActivityResultContracts.RequestPermission()
) { granted ->
    if (granted) viewModel.startListening()
}

fun startListeningWithPermission() {
    val granted = ContextCompat.checkSelfPermission(
        context, Manifest.permission.RECORD_AUDIO
    ) == PackageManager.PERMISSION_GRANTED
    if (granted) viewModel.startListening()
    else permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
}
```

把 `BottomBar(... onStartListening = viewModel::startListening ...)` 改为 `onStartListening = ::startListeningWithPermission`（或 `onStartListening = { startListeningWithPermission() }`）。

> 说明：不新增依赖，用 Compose 原生 `rememberLauncherForActivityResult`。权限属 UI 层，P4 落最顺，落完告知 P5。

### 3.3 VAD 参数集中 — 新增 `asr/AsrConfig.kt`（day2）

```kotlin
package com.memorybridge.asr

/** ASR 调优参数集中处，改一处即生效，便于 VAD 调优。 */
object AsrConfig {
    /** VAD 静音超时（ms）。老人语速慢，默认 3500，调优区间 2000–5000。 */
    const val VAD_SILENCE_TIMEOUT_MS = 3500L
    /** VAD 静音能量阈值（RMS）。 */
    const val VAD_SILENCE_THRESHOLD = 300.0
    /** 最小说话时长（ms），防短噪声误触发。 */
    const val VAD_MIN_SPEECH_MS = 300L
}
```

改 `VadStrategy` 构造默认值引用 `AsrConfig`，并把 `SpeechRecognizerManager.init` 与 `AsrCoordinator` 里 `VadStrategy()` 改成：

```kotlin
VadStrategy(
    silenceTimeoutMs = AsrConfig.VAD_SILENCE_TIMEOUT_MS,
    silenceEnergyThreshold = AsrConfig.VAD_SILENCE_THRESHOLD,
    minSpeechMs = AsrConfig.VAD_MIN_SPEECH_MS,
)
```

### 3.4 VAD 触发加固 — `VadStrategy.kt`（day2）

当前 `isTimeout()` 重新读时钟，与 `onAudioFrame` 的 `now` 有偏差，跨阈值帧漏触发的风险。改为“计算结果存字段，超时即时置位、消费时取走”：

```kotlin
private var lastVoiceTimeMs = 0L
private var speechStartTimeMs = 0L
private var isInSpeech = false
private var pendingTimeout = false   // 新增：确定性的超时标志

fun onAudioFrame(buffer: ByteArray, bytesRead: Int, onSilence: (Boolean) -> Unit) {
    val rms = calculateRms(buffer, bytesRead)
    val now = System.currentTimeMillis()
    val isVoice = rms > silenceEnergyThreshold
    if (isVoice) {
        if (!isInSpeech) { isInSpeech = true; speechStartTimeMs = now }
        lastVoiceTimeMs = now
        pendingTimeout = false
        onSilence(false)
    } else if (isInSpeech) {
        val silenceDuration = now - lastVoiceTimeMs
        if (silenceDuration > 200) onSilence(true)
        if (silenceDuration > silenceTimeoutMs &&
            (lastVoiceTimeMs - speechStartTimeMs) > minSpeechMs) {
            pendingTimeout = true      // 确定触发，不再依赖二次读时钟
            isInSpeech = false
        }
    }
}

/** 消费并清除超时标志，调用方拿到 true 后自行 reset。 */
fun consumeTimeout(): Boolean {
    val t = pendingTimeout
    pendingTimeout = false
    return t
}
```

`SpeechRecognizerManager.feedAudioData` 与 `AsrCoordinator.onAudioData` 里把 `if (isSilent && vadStrategy?.isTimeout() == true)` 换成在 `onSilence(true)` 分支里 `if (vadStrategy?.consumeTimeout() == true) { ... }`。这样超时只触发一次、确定性。

### 3.5（可选）延迟埋点 — 便于报告

在 `AsrCoordinator.start()` 记 `t0`，收到首个 `Partial` 记 `tPartial`，`Final` 记 `tFinal`，`Refined` 记 `tRefined`，Logcat 输出各段延迟。报告直接取数。

---

## 四、测试方法学（day3–4 报告用）

### 4.1 10 句常用语测试集（建议固定，可复现）

| # | 句子（含 demo 句） | 场景 |
|---|---|---|
| 1 | 我叫张奶奶，我喜欢喝小米粥 | demo 记忆句 |
| 2 | 今天天气怎么样 | 日常 |
| 3 | 我有点头晕 | 身体 |
| 4 | 我想我儿子了 | 家人 |
| 5 | 中午吃了面条 | 吃饭 |
| 6 | 你能给我讲个故事吗 | 陪伴 |
| 7 | 现在几点了 | 时间 |
| 8 | 谢谢你陪我聊天 | 感谢 |
| 9 | 我以前是当老师的 | 回忆 |
| 10 | 我有点冷 | 身体 |

每句念 1–2 遍，记录：识别文本、CER = 编辑距离/参考字数、`tPartial`、`tFinal`、`tRefined`。

### 4.2 VAD 三档对比表

| 超时 | 测试句数 | 误截断（句中被切） | 漏触发（说完不出 Final） | 平均 tFinal |
|------|---|---|---|---|
| 2000ms | 10 |  |  |  |
| 3500ms | 10 |  |  |  |
| 5000ms | 10 |  |  |  |

结论取“误截断=0 且 tFinal 可接受”的最小值。

### 4.3 精修前后对比（若服务端有可用后端）

| 句子 | Vosk 粗结果 | 云端精修 | 是否替换 |
|---|---|---|---|

### 4.4 报告章节

准确率（CER 表）→ 延迟分布（partial/final/refined）→ VAD 调优结论 → 精修价值 → 已知限制（small 模型对方言/含噪弱、首启动解压 1–3s、Google 后端国内不可用）。

---

## 五、风险与跨人依赖

| 风险 | 影响 | 处理 |
|------|------|------|
| Vosk aar API 与代码假设不符 | day1 编译/运行错 | 先用已知 0.3.47；导入后核对 `Recognizer` 方法签名（`acceptWaveForm(byte[],int)`、`getResult`、`getPartialResult`、`reset`、`setWords`、`close`），不符则按实际 aar 改 `SpeechRecognizerManager` |
| JitPack 构建原生库失败 | 依赖拉不到 | 回退 AAR-in-libs |
| 42MB 模型致 APK 过大/解压慢 | 首启体验 | Demo 可接受；后续可改“首启动下载到 filesDir” |
| 服务端 ASR=simple 国内不可用 | 精修无意义 | 联动 P1/P2 切 `whisper`（或 demo 只演示降级，不强求精修提升） |
| 平板 `VOICE_RECOGNITION` 源降噪过强 | 识别差 | 临时换 `AudioSource.MIC` 对比 |
| 运行时权限被拒 | 录不进音 | UI 引导“需要麦克风权限才能语音对话”+ 重试 |

**跨人**：P1/P2（服务端 ASR 后端、`/api/asr` 可用）→ P4 精修验证；P5（BASE_URL、状态机）→ P4 联调。day2 前对齐。

---

## 六、交付物对照

- [x] 代码框架就位（无需从零写）→ [ ] AAR 引入编译通过
- [ ] `vosk-model-small-cn-0.22` 进 assets，初始化解压成功
- [ ] 运行时录音权限打通
- [ ] 录音→Vosk→文本链路调通
- [ ] VAD 超时定值 + 调优报告
- [ ] WAV 上传精修链路验证（或降级确认）
- [ ] 8 场景离线模板命中验证
- [ ] 10 句准确率数据表
- [ ] ASR 测试报告（准确率/延迟/VAD/限制）
- [ ] 配合 P5 Demo 录制
