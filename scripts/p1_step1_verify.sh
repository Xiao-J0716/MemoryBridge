#!/usr/bin/env bash
# P1 Step 1 验证：检查 PostgreSQL / pgvector / Redis 是否正常
set -euo pipefail

export PGPASSWORD=memorybridge

echo "==> Redis"
redis-cli ping

echo ""
echo "==> PostgreSQL 连接"
psql -h localhost -U memorybridge -d memorybridge -c "SELECT version();" | head -3

echo ""
echo "==> pgvector 扩展"
psql -h localhost -U memorybridge -d memorybridge -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"

echo ""
echo "✅ 基础设施验证通过"
