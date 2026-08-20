# P4 交接提示词（供“合并用 AI”阅读）

> 本文件面向负责把 `MB-xiaoj` 分支合并进 `main` 的 AI / 人。自包含，读完即可执行合并与验证。

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

## 2. 改动清单（逐文件）

**新增文件**
| 文件 | 作用 |
|------|------|
| `client/app/src/main/java/org/vosk/`（LibVosk/Model/Recognizer/LogLevel/SpeakerModel） | Vosk Java 绑定源码，取自 alphacep/vosk-api release v0.3.45 的 android/lib 模块 |
| `client/app/src/main/java/com/memorybridge/asr/AsrConfig.kt` | 集中 VAD 参数，调优只改一处 |
| `client/app/src/main/jniLibs/.gitignore` | 忽略 `*.so`（原生库不入库，由脚本拉取） |
| `client/app/src/main/assets/models/.gitignore` + `README.md` | 忽略模型二进制 + 下载说明 |
| `scripts/setup-asr-assets.sh` | 一键下载模型 + 原生库 |
| `P4-ASR-开发方案.md` | P4 完整开发方案（含测试方法学） |
| `P4-HANDOFF.md` | 本文件 |

**修改文件**
| 文件 | 改动 |
|------|------|
| `client/app/build.gradle.kts` | 原 Vosk AAR 依赖被注释→项目无法编译；改为 `implementation("net.java.dev.jna:jna:5.13.0")` |
| `client/app/src/main/java/com/memorybridge/ui/ChatScreen.kt` | 补 RECORD_AUDIO 运行时权限请求（原仅 Manifest 声明，6.0+ 点录音必抛 SecurityException） |
| `client/app/src/main/java/com/memorybridge/asr/VadStrategy.kt` | 超时改 `consumeTimeout()` 确定性触发（原 `isTimeout()` 二次读时钟会漏帧）；参数默认取 AsrConfig |
| `client/app/src/main/java/com/memorybridge/asr/SpeechRecognizerManager.kt` | 消费 `consumeTimeout()` |
| `client/app/src/main/java/com/memorybridge/asr/AsrCoordinator.kt` | 消费 `consumeTimeout()`；并修复误 import `com.memorybridge.audio.VadStrategy`（实际同包 asr，原 import 不可解析，是 Vosk 外另一编译阻断） |
| `client/app/src/main/java/org/vosk/LibVosk.java` | 删除 Android 不可解析的 `java.nio.file.*` 等未使用 import |

**此前缺失、本次一并补入库（构建必需）**
- `client/build.gradle.kts`、`client/settings.gradle.kts`：初始提交 `7bdac74` 未含 gradle 构建文件，导致项目不可构建。本次补入。

## 3. 关键决策：为什么不是 AAR
Vosk 不再发布预编译 AAR；`alphacep/vosk-android` 仓库已 404；JitPack 不可用。故采用「源码内联 + JNA + 原生 .so」：
- `org.vosk.*` Java 绑定直接编译进 app
- JNA(`5.13.0`，Maven Central) 提供原生桥接
- `libvosk.so` 放 `jniLibs/<abi>/`，JNA `Native.register("vosk")` 加载
- 原生库与模型不入库，由脚本拉取，保持合并 diff 纯文本、便于合并

## 4. 合并指令
```bash
cd app
git fetch origin
git checkout main && git pull
git merge MB-xiaoj        # 或经 GitHub PR 合并
bash scripts/setup-asr-assets.sh   # 合并后必跑
```
然后用 Android Studio 打开 `client/` → Gradle Sync → 编译 `:app` → 装机。

## 5. 不要纳入合并的内容
`MB-xiaoj` 工作树里还有以下**非 P4** 文件，已用白名单 `git add` 排除，合并时勿带入：
- 服务端他人改动：`server/.env.example`、`server/models/database.py`、`server/routers/chat.py`、`server/routers/tts.py`、`server/services/session_service.py`
- UI 预览：`tablet-ui-preview.html`、`tablet-ui-v2.html`、`ui-preview.html`

## 6. 验证步骤（合并后）
1. Gradle Sync 成功（`org.vosk.*` 解析、JNA 从 Maven 拉取）
2. 编译 `:app` 通过
3. 装机首次点“开始说话”→ 弹录音权限请求并授权
4. Logcat tag `SpeechRecognizer` 见 `模型解压完成` 与 `Vosk 模型初始化成功`
5. 说一句话 → 实时 partial 上屏 → 停顿后 final 进消息列表

## 7. 已知限制 / 跨人依赖
- 服务端 `/api/asr` 后端默认 `simple`(Google Web API)，国内不可达 → 客户端“先粗后精”精修会**静默降级**保留 Vosk 粗结果（不报错）。需 P1/P2 切 `whisper`/`funasr` 才能演示真实精修提升。
- `ApiClient.BASE_URL` 硬编码（P5 范畴），联调前对齐本机局域网 IP。
- small 模型对方言/含噪弱，干净朗读预期字准确率约 80–90%。
- VAD 超时默认 3500ms，在 `AsrConfig` 调（调优方法见 `P4-ASR-开发方案.md` §四）。
