# P4 交接提示词（供"合并用 AI"阅读）

> 本文件面向负责把 `MB-xiaoj` 分支合并进 `main` 的 AI / 人。自包含，读完即可执行合并与验证。
> **本分支已在 Android 模拟器上真机跑通**（编译→安装→ASR 初始化→点麦克风启动录音，全程无崩溃），见 §8 验证记录。

## 0. 你是谁、要做什么
你是协助代码合并的 AI。仓库 `app/`（remote: github.com/Xiao-J0716/MemoryBridge）有分支 `MB-xiaoj`，承载 P4（客户端 ASR+音频）全部改动。目标：把 `MB-xiaoj` 合并进 `main`，并保证合并后客户端能**构建**且能**跑通语音识别链路**。

## 1. 合并前必做：环境准备（否则运行时崩溃）
在 `app/` 目录运行一次：
```bash
bash scripts/setup-asr-assets.sh
```
脚本下载：
1. Vosk 中文模型 `vosk-model-small-cn-0.22`（~42MB）→ `client/app/src/main/assets/models/`（不入库）
2. `libvosk.so`（4 个 ABI，~36MB）→ `client/app/src/main/jniLibs/<abi>/`（不入库）
未运行则 APK 缺原生库，运行时报 `UnsatisfiedLinkError: no vosk in java.library.path`。

> 还需写 `client/local.properties` 指向本机 SDK：`sdk.dir=C:\\Users\\<你>\\AppData\\Local\\Android\\Sdk`（不入库，gitignore 已排除）。gradle wrapper 已含在分支内，首次构建会自动下载 Gradle 8.2。

## 2. 改动清单（逐文件）

**新增文件**
| 文件 | 作用 |
|------|------|
| `client/app/src/main/java/org/vosk/`（LibVosk/Model/Recognizer/LogLevel/SpeakerModel） | Vosk Java 绑定源码，取自 alphacep/vosk-api release v0.3.45 的 android/lib 模块 |
| `client/app/src/main/java/com/memorybridge/asr/AsrConfig.kt` | 集中 VAD 参数，调优只改一处 |
| `client/app/src/main/jniLibs/.gitignore` | 忽略 `*.so`（原生库不入库，由脚本拉取） |
| `client/app/src/main/assets/models/.gitignore` + `README.md` | 忽略模型二进制 + 下载说明 |
| `client/gradlew` `client/gradlew.bat` `client/gradle/wrapper/gradle-wrapper.{jar,properties}` | gradle 包装器（初始提交缺失，本次补入；properties 锁 Gradle 8.2，匹配 AGP 8.2.2） |
| `scripts/setup-asr-assets.sh` | 一键下载模型 + 原生库 |
| `P4-ASR-开发方案.md` | P4 完整开发方案（含测试方法学） |
| `P4-HANDOFF.md` | 本文件 |

**修改文件（P4 范畴）**
| 文件 | 改动 |
|------|------|
| `client/app/build.gradle.kts` | 原 Vosk AAR 依赖被注释→项目无法编译；改为 `implementation("net.java.dev.jna:jna:5.13.0@aar")`（**必须 @aar**，见 §3） |
| `client/app/src/main/java/com/memorybridge/ui/ChatScreen.kt` | 补 RECORD_AUDIO 运行时权限请求（原仅 Manifest 声明，6.0+ 点录音必抛 SecurityException） |
| `client/app/src/main/java/com/memorybridge/asr/VadStrategy.kt` | 超时改 `consumeTimeout()` 确定性触发（原 `isTimeout()` 二次读时钟会漏帧）；参数默认取 AsrConfig |
| `client/app/src/main/java/com/memorybridge/asr/SpeechRecognizerManager.kt` | 消费 `consumeTimeout()`；更新集成指南注释 |
| `client/app/src/main/java/com/memorybridge/asr/AsrCoordinator.kt` | 消费 `consumeTimeout()`；并修复误 import `com.memorybridge.audio.VadStrategy`（实际同包 asr，原 import 不可解析，是 Vosk 外另一编译阻断） |
| `client/app/src/main/java/org/vosk/LibVosk.java` | 删除 Android 不可解析的 `java.nio.file.*` 等未使用 import |

**修改文件（非 P4，但为"让客户端能编译"必须修的既有 bug —— 真机上验证才发现，因初始提交无 gradlew 从未编译过）**
| 文件 | 改动 | 归属 | 说明 |
|------|------|------|------|
| `client/app/src/main/java/com/memorybridge/net/ApiClient.kt` | 私有 `var chatApi` 与公开 `val chatApi` 同名冲突 → 私有字段改名 `_chatApi` | P5 | 否则 `compileDebugKotlin` 报 "Conflicting declarations" |
| `client/app/src/main/java/com/memorybridge/tts/TtsManager.kt` | `currentTempFile` 可空智能转换失败 → 加 `!!` | P2 | 否则 `compileDebugKotlin` 报 "Smart cast impossible" |
| `client/app/src/main/res/drawable/ic_mic.xml` | `?attr/colorControlNormal` 在平台 Material 主题下不可解析 → 改 `?android:attr/colorControlNormal` | — | 否则 `processDebugResources` AAPT 链接失败 |
> 这三处请相应负责人（P5/P2）review；改动最小且不改语义，仅为让项目可编译。

**此前缺失、本次一并补入库（构建必需）**
- `client/build.gradle.kts`、`client/settings.gradle.kts`：初始提交 `7bdac74` 未含，导致项目不可构建。本次补入。

## 3. 关键决策：为什么不是 AAR，以及 JNA 必须 @aar
- Vosk 不再发布预编译 AAR；`alphacep/vosk-android` 仓库已 404；JitPack 不可用。故采用「源码内联 + JNA + 原生 .so」：`org.vosk.*` Java 绑定直接编译进 app；`libvosk.so` 放 `jniLibs/<abi>/`，JNA `Native.register("vosk")` 加载。
- **JNA 依赖必须用 `@aar` 制品**：`net.java.dev.jna:jna:5.13.0` 的普通 `.jar` **不含 Android 原生库**（只有 linux/darwin/win32 的 `libjnidispatch`），Android 上 `System.loadLibrary("jnidispatch")` 找不到 → `UnsatisfiedLinkError: com/sun/jna/android-x86-64/libjnidispatch.so not found`。`@aar` 制品自带 `jni/<abi>/libjnidispatch.so`，AGP 合并入 APK 才能运行。**这是真机验证踩出的坑，务必用 @aar。**
- 原生库与模型不入库，由脚本拉取，保持合并 diff 纯文本、便于合并。

## 4. 合并指令
```bash
cd app
git fetch origin
git checkout main && git pull
git merge MB-xiaoj        # 或经 GitHub PR 合并
# 合并后：
printf 'sdk.dir=C:\\Users\\<你>\\AppData\\Local\\Android\\Sdk\n' > client/local.properties
bash scripts/setup-asr-assets.sh
```
然后用 Android Studio 打开 `client/` → Gradle Sync → 编译 `:app` → 装机。

## 5. 不要纳入合并的内容
`MB-xiaoj` 工作树里还有以下**非 P4** 文件，已用白名单 `git add` 排除，合并时勿带入：
- 服务端他人改动：`server/.env.example`、`server/models/database.py`、`server/routers/chat.py`、`server/routers/tts.py`、`server/services/session_service.py`
- UI 预览：`tablet-ui-preview.html`、`tablet-ui-v2.html`、`ui-preview.html`
- 本机环境配置（不入库）：`client/local.properties`、`client/gradle.properties` 里的 `android.overridePathCheck=true`

## 6. 验证步骤（合并后）
1. Gradle Sync 成功（`org.vosk.*` 解析、JNA `@aar` 从 Maven 拉取）
2. 编译 `:app` 通过（`./gradlew :app:assembleDebug`）
3. 装机首次点"开始说话"→ 弹录音权限请求并授权
4. Logcat tag `SpeechRecognizer` 见 `模型解压完成` 与 `Vosk 模型初始化成功`；tag `VoskAPI` 见模型加载日志
5. 说一句话 → 实时 partial 上屏 → 停顿后 final 进消息列表

## 7. 已知限制 / 跨人依赖
- 服务端 `/api/asr` 后端默认 `simple`(Google Web API)，国内不可达 → 客户端"先粗后精"精修会**静默降级**保留 Vosk 粗结果（不报错）。需 P1/P2 切 `whisper`/`funasr` 才能演示真实精修提升。
- `ApiClient.BASE_URL` 硬编码（P5 范畴），联调前对齐本机局域网 IP。
- small 模型对方言/含噪弱，干净朗读预期字准确率约 80–90%。
- VAD 超时默认 3500ms，在 `AsrConfig` 调（调优方法见 `P4-ASR-开发方案.md` §四）。

## 8. 真机验证记录（2026-08-20，本机模拟器）
已在本机完成端到端验证（Android 模拟器 MB_Phone，API 36.1 google_apis x86_64，AGP 8.2.2 + Gradle 8.2 + JDK 21）：
- ✅ `./gradlew :app:assembleDebug` **BUILD SUCCESSFUL**，APK 136MB（含 42MB 模型 + 36MB 原生库）
- ✅ 安装启动无崩溃；Logcat 完整链路：
  `ChatViewModel: 初始化 ASR 引擎, mode=COARSE_TO_FINE` → `SpeechRecognizer: 模型解压完成` → `VoskAPI: ReadDataFiles…` → `SpeechRecognizer: Vosk 模型初始化成功` → `AsrCoordinator: COARSE_TO_FINE 模式：Vosk 初始化成功` → `ChatViewModel: ASR 引擎初始化成功`
- ✅ 点麦克风按钮：`SpeechRecognizer: 启动 Vosk 识别` → `AudioRecorder: 录音已启动, bufferSize=3200` → `AsrCoordinator: ASR 启动, mode=COARSE_TO_FINE`（**无 SecurityException**，运行时权限修复生效）
- ⚠️ 未能在模拟器验证"说出文字→识别上屏"：本次模拟器以 headless + `-no-audio` 启动，虚拟麦克风无真实音频输入（HAL 报 `pcm_readi I/O error`，属模拟器环境限制非 App bug）。**真实识别需真机或有麦克风透传的模拟器**。录音循环对 I/O 错误已优雅处理（`readBytes>0` 才处理），不崩溃。
- 复现命令（本机）：
  ```bash
  export JAVA_HOME=".../jdk-21" ANDROID_HOME=".../Android/Sdk"
  cd client && ./gradlew :app:assembleDebug
  <启动模拟器> && adb install -r app/build/outputs/apk/debug/app-debug.apk
  adb shell am start -n com.memorybridge/.MainActivity
  adb logcat | grep -iE "SpeechRecognizer|ChatViewModel|AsrCoordinator|VoskAPI"
  ```

## 9. 本机构建环境备注（仅当你在中文路径下构建）
若仓库检出到含中文的路径（如 `…\AI主理人\app`），AGP 会因非 ASCII 路径拒绝构建。在 `client/gradle.properties` 加一行（官方逃生开关，不入库）：
```
android.overridePathCheck=true
```
