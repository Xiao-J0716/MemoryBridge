#!/usr/bin/env bash
# P1 Step 1: 本地安装 PostgreSQL 15 + pgvector + Redis（Ubuntu 22.04）
set -euo pipefail

# VS Code 源缺少 GPG 密钥会导致 apt update 整体失败，安装前先修复
fix_vscode_apt_source() {
  local vscode_list="/etc/apt/sources.list.d/vscode.list"
  if [ -f "$vscode_list" ] && ! grep -q "signed-by=" "$vscode_list"; then
    echo "==> 修复 VS Code apt 源 GPG 密钥（避免 apt update 失败）..."
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft.gpg
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/code stable main" | sudo tee "$vscode_list" > /dev/null
  fi
}

apt_update_safe() {
  if ! sudo apt-get update -qq; then
    echo "==> apt update 仍失败，临时禁用 VS Code 源后重试..."
    local vscode_list="/etc/apt/sources.list.d/vscode.list"
    if [ -f "$vscode_list" ]; then
      sudo mv "$vscode_list" "${vscode_list}.disabled"
      sudo apt-get update -qq
      echo "（VS Code 源已临时禁用为 ${vscode_list}.disabled，不影响 PostgreSQL 安装）"
    else
      echo "❌ apt update 失败，请检查 /etc/apt/sources.list.d/ 下的第三方源"
      exit 1
    fi
  fi
}

fix_vscode_apt_source

echo "==> [1/5] 添加 PostgreSQL 官方 apt 源..."
sudo install -d /usr/share/postgresql-common/pgdg
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo gpg --dearmor -o /usr/share/keyrings/postgresql.gpg
echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list > /dev/null

echo "==> [2/5] 安装 PostgreSQL 15、pgvector、Redis、Python venv..."
apt_update_safe
sudo apt-get install -y postgresql-15 postgresql-15-pgvector redis-server python3-venv python3-pip

echo "==> [3/5] 启动并设置开机自启..."
sudo systemctl enable --now postgresql
sudo systemctl enable --now redis-server

echo "==> [4/5] 创建数据库和用户 (memorybridge/memorybridge)..."
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'memorybridge') THEN
    CREATE USER memorybridge WITH PASSWORD 'memorybridge';
  END IF;
END
$$;

SELECT 'CREATE DATABASE memorybridge OWNER memorybridge'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'memorybridge')\gexec

GRANT ALL PRIVILEGES ON DATABASE memorybridge TO memorybridge;
SQL

echo "==> [5/5] 启用 pgvector 扩展..."
sudo -u postgres psql -v ON_ERROR_STOP=1 -d memorybridge <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
GRANT ALL ON SCHEMA public TO memorybridge;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO memorybridge;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO memorybridge;
SQL

echo ""
echo "✅ 基础设施安装完成！"
echo ""
echo "验证命令："
echo "  psql -h localhost -U memorybridge -d memorybridge -c \"SELECT extname FROM pg_extension WHERE extname='vector';\""
echo "  redis-cli ping"
echo ""
echo "PostgreSQL: localhost:5432  用户/密码/库: memorybridge"
echo "Redis:      localhost:6379  无密码"
