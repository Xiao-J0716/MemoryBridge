#!/usr/bin/env bash
# ============================================================
#  MemoryBridge 一键启动脚本 (Linux/macOS/git-bash)
#  1. 检查 .env 文件
#  2. 启动数据库（Docker 优先，无 Docker 则跳过）
#  3. 安装 Python 依赖
#  4. 启动 uvicorn 服务
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$SCRIPT_DIR/server"

echo "========================================"
echo "  MemoryBridge Server 启动"
echo "========================================"
echo

# ---- 1. 检查 .env ----
if [ ! -f "$SERVER_DIR/.env" ]; then
    if [ -f "$SERVER_DIR/.env.example" ]; then
        echo "[警告] 未找到 .env 文件，从 .env.example 复制..."
        cp "$SERVER_DIR/.env.example" "$SERVER_DIR/.env"
        echo "[提示] 请编辑 server/.env 填入 API Key 等配置后重新运行"
        echo
    else
        echo "[错误] 未找到 .env 或 .env.example"
        exit 1
    fi
fi

# ---- 2. 启动数据库 ----
echo "[1/4] 启动数据库..."
if command -v docker &>/dev/null; then
    if docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d 2>/dev/null; then
        echo "[OK] 数据库容器已启动"
    else
        echo "[警告] Docker 启动失败，假设数据库已在本地运行"
    fi
else
    echo "      未检测到 Docker，假设 PostgreSQL + Redis 已本地安装"
    echo "      如未安装，请联系 P1 同事配置数据库"
fi
echo

# ---- 3. 安装依赖 ----
echo "[2/4] 检查 Python 依赖..."
cd "$SERVER_DIR"
if command -v uv &>/dev/null; then
    uv pip install -r requirements.txt --quiet 2>/dev/null || true
else
    python -m pip install -r requirements.txt --quiet 2>/dev/null || true
fi
echo "[OK] 依赖检查完成"
echo

# ---- 4. 启动 uvicorn ----
echo "[3/4] 启动 FastAPI 服务..."
echo "      地址: http://localhost:8000"
echo "      Swagger: http://localhost:8000/docs"
echo "      按 Ctrl+C 停止"
echo

# 健康检查函数（启动后后台检测）
health_check() {
    local retries=0
    while [ $retries -lt 10 ]; do
        if curl -s http://localhost:8000/health >/dev/null 2>&1; then
            echo "[OK] 健康检查通过 — 服务就绪"
            return 0
        fi
        retries=$((retries + 1))
        sleep 1
    done
    echo "[警告] 健康检查超时，请手动访问 http://localhost:8000/health"
    return 1
}

# 后台启动健康检查
( sleep 3; health_check ) &

# [4/4] 启动服务（前台运行，Ctrl+C 退出）
echo "[4/4] 启动 uvicorn..."
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
