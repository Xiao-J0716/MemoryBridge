# Memory Bridge

给认知症老人用的 AI 陪伴系统，以语音识别为核心。

## 架构概览

采用端云两级架构：

- **端侧（client/）**：Android 应用，使用 Vosk 离线 ASR 实时识别老人语音，原始音频不出端。
- **云侧（server/）**：Python + FastAPI，提供对话理解、记忆存储与检索、LLM 生成等能力。

```
[老人语音] → 端侧 Vosk 离线 ASR → 文本 → 云侧 FastAPI + LLM → 回复
```

## 目录结构

```
app/
├── client/          # 端侧 Android 应用（Kotlin）
│   ├── app/         # 主模块
│   └── ...
├── server/          # 云侧服务（Python/FastAPI）
│   ├── main.py      # 应用入口
│   └── ...
├── docker-compose.yml
└── README.md
```

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 端侧 ASR | Vosk | 离线中文语音识别，保护隐私 |
| 端侧平台 | Android / Kotlin | 移动端应用 |
| 云侧框架 | FastAPI | 高性能异步 Web 框架 |
| 数据库 | PostgreSQL 15 + pgvector | 结构化存储 + 向量检索 |
| 缓存 | Redis 7 | 会话缓存与任务队列 |
| 大模型 | LLM | 对话生成与理解 |

## 快速开始

### 方式 A：本地部署（P1 推荐，不用 Docker）

**1. 安装基础设施**

```bash
bash scripts/p1_step1_install_infra.sh
bash scripts/p1_step1_verify.sh
```

**2. 安装 Ollama 并拉取模型**

```bash
bash scripts/p1_step2_install_ollama.sh
# 若安装不完整，执行: bash scripts/p1_step2_repair_ollama.sh
```

**3. 配置环境变量**

```bash
cp server/.env.example server/.env
```

关键配置（Ollama 本地模式）：

```env
LLM_MODE=ollama
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```

**4. 启动服务并验证**

```bash
bash scripts/p1_step2_start_server.sh
```

**5. 测试 RAG 记忆（跨会话）**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"text":"我叫张奶奶，我喜欢喝小米粥","session_id":"session-A"}'

curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"text":"你还记得我叫什么吗？","session_id":"session-B"}'
```

**6. 稳定性测试（可选）**

```bash
python3 scripts/p1_step4_stability_test.py
```

### 方式 B：Docker 启动数据库

```bash
docker-compose up -d
```

### 启动云侧

```bash
cd server
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 打开端侧

用 Android Studio 打开 `client/` 目录，同步 Gradle 后运行。平板联调时将 `ApiClient.kt` 的 `BASE_URL` 指向服务端地址（如 `http://192.168.x.x:8000/`）。

## 脚本索引（P1）

| 脚本 | 作用 |
|------|------|
| `scripts/p1_step1_install_infra.sh` | 安装 PostgreSQL + pgvector + Redis |
| `scripts/p1_step1_verify.sh` | 验证基础设施 |
| `scripts/p1_step2_install_ollama.sh` | 安装 Ollama + 拉模型 |
| `scripts/p1_step2_repair_ollama.sh` | 修复不完整 Ollama 安装 |
| `scripts/p1_step2_start_server.sh` | 启动服务 + 验证 `/api/chat` |
| `scripts/p1_step4_stability_test.py` | 20 轮稳定性测试 |
| `scripts/seed_test_user.sql` | 插入测试用户 `user_id=1` |

## 关键设计决策

- **Vosk 离线**：ASR 完全在端侧离线运行，无需联网即可识别，降低延迟并保护隐私。
- **原始音频不出端**：仅将识别后的文本上传云侧，原始音频数据始终留在设备本地。
- **ASR 始终离线**：无论网络状态如何，语音识别能力保持可用，确保核心陪伴功能不中断。

## 模型下载说明

端侧需要 Vosk 中文离线模型：

- 模型名称：`vosk-model-small-cn-0.22`
- 下载地址：https://alphacephei.com/vosk/models
- 放置路径：将解压后的模型文件夹放入端侧 `client/app/src/main/assets/` 目录下，重命名为 `vosk-model-small-cn-0.22`。

> 小模型体积约 40MB，适合端侧部署；如需更高准确率可选用 `vosk-model-cn-0.22`（约 1.3GB）。
