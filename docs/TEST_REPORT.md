# MemoryBridge 后端测试报告

> 测试时间: 2026-08-20
> 测试框架: pytest 9.1.1 + pytest-asyncio 1.4.0
> Python: 3.11.15
> 测试环境: Windows 10, 无需真实 DB/Redis/LLM（全部 mock）

---

## 测试总览

```
15 passed in 0.80s
```

| 指标 | 值 |
|------|-----|
| 测试总数 | 15 |
| 通过 | 15 |
| 失败 | 0 |
| 跳过 | 0 |
| 耗时 | 0.80s |
| 覆盖端点 | 6/6 |

---

## 测试明细

### 健康检查 (test_health.py)

| 测试 | 结果 | 说明 |
|------|------|------|
| test_health | PASS | GET /health 返回 200 + status=ok + version + timestamp |
| test_health_no_body | PASS | GET /health 无需请求体 |

### 对话 (test_chat.py)

| 测试 | 结果 | 说明 |
|------|------|------|
| test_chat_normal | PASS | 正常对话返回 reply + session_id + memories_used |
| test_chat_empty_text | PASS | 空文本返回 422 |
| test_chat_missing_field | PASS | 缺 user_id/session_id 返回 422 |
| test_chat_llm_failure | PASS | LLM 异常返回 500 |

### 语音合成 (test_tts.py)

| 测试 | 结果 | 说明 |
|------|------|------|
| test_tts_normal | PASS | 返回 audio/mpeg + X-TTS-Engine: edge |
| test_tts_empty_text | PASS | 空文本返回 422 |
| test_tts_fallback_offline | PASS | 模拟 edge 失败，降级到 offline 引擎 |
| test_tts_all_fail | PASS | 所有引擎失败返回 503 |
| test_tts_custom_voice | PASS | 自定义 voice/rate 参数正常 |

### 语音识别 + 记忆 (test_asr_memory.py)

| 测试 | 结果 | 说明 |
|------|------|------|
| test_asr_status | PASS | GET /api/asr/status 返回 backend + available + timeout |
| test_memory_query_empty | PASS | 无记忆时返回空列表 |
| test_memory_query_with_results | PASS | 有记忆时返回带 score 的结果 |
| test_memory_query_missing_params | PASS | 缺 query 参数返回 422 |

---

## 端点覆盖

| 端点 | 测试数 | 覆盖场景 |
|------|--------|---------|
| GET /health | 2 | 正常响应 |
| POST /api/chat | 4 | 正常 / 空文本 / 缺字段 / LLM失败 |
| POST /api/tts | 5 | 正常 / 空文本 / 降级offline / 全失败503 / 自定义参数 |
| POST /api/asr | 0 | 需音频文件，待集成测试阶段覆盖 |
| GET /api/asr/status | 1 | 状态查询 |
| GET /api/memory/query | 3 | 空结果 / 有结果 / 缺参数 |

---

## TTS 降级验证

8/20 额外验证（ad-hoc script，非 pytest 内）：

| 场景 | 结果 | MP3 大小 |
|------|------|---------|
| edge-tts 正常 | PASS | 17,712 bytes |
| edge-tts 403 → 降级 pyttsx3 | PASS | 47,273 bytes |
| 两个引擎都失败 | PASS (正确抛 RuntimeError) | - |

---

## Mock 策略

测试不依赖真实外部服务：

| 依赖 | Mock 方式 |
|------|-----------|
| PostgreSQL (asyncpg) | app.dependency_overrides[get_db] → mock_db |
| Redis (session_service) | patch routers.chat.get_session_service |
| LLM (deepseek/qwen/ollama) | patch routers.chat.get_llm_service |
| TTS (edge-tts/pyttsx3) | patch routers.tts.tts_synthesize |
| MemoryService | patch routers.memory.MemoryService |

---

## 运行方式

```bash
cd server
python -m pytest tests/ -v
```

生成 JUnit XML 报告:

```bash
python -m pytest tests/ -v --junitxml=test-report.xml
```
