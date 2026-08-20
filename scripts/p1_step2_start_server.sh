#!/usr/bin/env bash
# P1 Step 2: 启动 FastAPI 并验证 /api/chat
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER="$ROOT/server"
export PGPASSWORD=memorybridge

echo "==> [1/4] 检查 Ollama..."
if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
  echo "❌ Ollama 未运行，请先执行: bash \"$ROOT/scripts/p1_step2_install_ollama.sh\""
  exit 1
fi
echo "    Ollama OK"

echo "==> [2/4] 启动 FastAPI（若 8000 已被占用则跳过启动）..."
if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
  echo "    服务已在运行"
else
  cd "$SERVER"
  nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/memorybridge-server.log 2>&1 &
  echo "    等待服务启动..."
  for i in $(seq 1 15); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! curl -sf http://localhost:8000/health >/dev/null; then
  echo "❌ 服务启动失败，查看日志: tail -50 /tmp/memorybridge-server.log"
  exit 1
fi
echo "    FastAPI OK: $(curl -s http://localhost:8000/health)"

echo "==> [3/4] 初始化测试用户 (user_id=1)..."
# 等服务建表后再插入
sleep 1
psql -h localhost -U memorybridge -d memorybridge -f "$ROOT/scripts/seed_test_user.sql" 2>/dev/null || {
  echo "    users 表尚未创建，触发一次 /api/chat 以建表..."
  curl -s -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" \
    -d '{"user_id":1,"text":"ping","session_id":"init"}' >/dev/null || true
  sleep 1
  psql -h localhost -U memorybridge -d memorybridge -f "$ROOT/scripts/seed_test_user.sql" || true
}

echo "==> [4/4] 测试 /api/chat..."
RESP=$(curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"text":"你好，请用一句话介绍你自己","session_id":"p1-test-001"}')

echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"

if echo "$RESP" | grep -q '"reply"'; then
  echo ""
  echo "✅ /api/chat 验证通过！"
  echo "   服务地址: http://$(hostname -I | awk '{print $1}'):8000"
  echo "   日志: tail -f /tmp/memorybridge-server.log"
else
  echo ""
  echo "❌ /api/chat 未返回有效回复，查看日志: tail -50 /tmp/memorybridge-server.log"
  exit 1
fi
