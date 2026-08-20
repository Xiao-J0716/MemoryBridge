#!/usr/bin/env bash
# 修复不完整的 Ollama 安装（缺少 llama-server 时执行）
set -euo pipefail

echo "==> 检查当前 Ollama 安装..."
if [ -f /usr/local/lib/ollama/llama-server ]; then
  echo "    llama-server 已存在，无需修复"
  exit 0
fi

echo "    检测到不完整安装：缺少 /usr/local/lib/ollama/llama-server"

if ! command -v zstd >/dev/null; then
  echo "==> 安装 zstd..."
  sudo apt-get update -qq
  sudo apt-get install -y zstd
fi

echo "==> 停止现有 Ollama 进程..."
pkill -f "ollama serve" 2>/dev/null || true
sleep 1

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
archive="$tmp_dir/ollama-linux-amd64.tar.zst"

echo "==> 下载完整 Ollama 安装包（约 1.3GB，带重试）..."
curl -fL --retry 5 --retry-delay 5 --retry-all-errors --connect-timeout 20 --max-time 0 \
  -o "$archive" "https://ollama.com/download/ollama-linux-amd64.tar.zst"

echo "==> 解压到 /usr/local（需要 sudo）..."
zstd -d < "$archive" | sudo tar -xf - -C /usr/local

if [ ! -f /usr/local/lib/ollama/llama-server ]; then
  echo "❌ 修复后仍未找到 llama-server"
  ls -la /usr/local/lib/ollama/ 2>/dev/null || true
  exit 1
fi

echo "==> 启动 Ollama..."
if [ -f /etc/systemd/system/ollama.service ] || [ -f /lib/systemd/system/ollama.service ]; then
  sudo systemctl enable --now ollama 2>/dev/null || true
fi
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  sleep 3
fi

echo "==> 验证 embeddings..."
curl -sf http://localhost:11434/api/embed \
  -d '{"model":"nomic-embed-text","input":"hello"}' >/tmp/ollama-embed-test.json

python3 - <<'PY'
import json
with open("/tmp/ollama-embed-test.json") as f:
    data = json.load(f)
emb = (data.get("embeddings") or [[]])[0] or data.get("embedding") or []
print(f"embedding dim = {len(emb)}")
if len(emb) < 100:
    raise SystemExit("embedding 验证失败")
print("✅ Ollama 修复完成，embeddings 可用")
PY

echo ""
echo "下一步：bash \"$(dirname "$0")/p1_step2_start_server.sh\""
