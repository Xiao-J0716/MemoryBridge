#!/usr/bin/env bash
# P1 Step 2: 安装 Ollama 并拉取对话/向量模型
set -euo pipefail

retry_download() {
  local url="$1"
  local output="$2"
  curl -fL --retry 5 --retry-delay 5 --retry-all-errors --connect-timeout 20 --max-time 0 -o "$output" "$url"
}

ollama_installed_ok() {
  command -v ollama >/dev/null 2>&1 && [ -f /usr/local/lib/ollama/llama-server ]
}

install_ollama_package() {
  if ! command -v zstd >/dev/null; then
    echo "    安装 zstd..."
    sudo apt-get update -qq
    sudo apt-get install -y zstd
  fi

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT
  archive="$tmp_dir/ollama-linux-amd64.tar.zst"
  echo "    下载 Ollama 安装包（tar.zst，带重试）..."
  retry_download "https://ollama.com/download/ollama-linux-amd64.tar.zst" "$archive"
  echo "    解压到 /usr/local（需要 sudo）..."
  zstd -d < "$archive" | sudo tar -xf - -C /usr/local
}

echo "==> [1/3] 安装 Ollama..."
if ollama_installed_ok; then
  echo "    Ollama 已完整安装: $(ollama --version 2>/dev/null || true)"
else
  if command -v ollama >/dev/null 2>&1; then
    echo "    检测到不完整安装，重新安装完整包..."
    pkill -f "ollama serve" 2>/dev/null || true
    sleep 1
  fi
  install_ollama_package
  if [ ! -f /usr/local/lib/ollama/llama-server ]; then
    echo "❌ Ollama 安装后未找到 /usr/local/lib/ollama/llama-server"
    exit 1
  fi
fi

echo "==> [2/3] 启动 Ollama 服务..."
if systemctl is-active ollama >/dev/null 2>&1; then
  echo "    Ollama 服务已在运行"
else
  if [ -f /etc/systemd/system/ollama.service ] || [ -f /lib/systemd/system/ollama.service ]; then
    sudo systemctl enable --now ollama 2>/dev/null || true
  fi
  if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    sleep 3
  fi
fi

echo "==> [3/3] 拉取模型（约 4-5GB，需要几分钟）..."
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

echo ""
echo "✅ Ollama 安装完成！"
echo ""
ollama list
echo ""
echo "下一步：bash \"$(dirname "$0")/p1_step2_start_server.sh\""
