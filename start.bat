@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM  MemoryBridge 一键启动脚本 (Windows)
REM  1. 检查 .env 文件
REM  2. 启动数据库（Docker 优先，无 Docker 则跳过）
REM  3. 安装 Python 依赖
REM  4. 启动 uvicorn 服务
REM  5. 健康检查
REM ============================================================

setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
set "SERVER_DIR=%PROJECT_ROOT%server"

echo ========================================
echo   MemoryBridge Server 启动
echo ========================================
echo.

REM ---- 1. 检查 .env ----
if not exist "%SERVER_DIR%\.env" (
    if exist "%SERVER_DIR%\.env.example" (
        echo [警告] 未找到 .env 文件，从 .env.example 复制...
        copy "%SERVER_DIR%\.env.example" "%SERVER_DIR%\.env" >nul
        echo [提示] 请编辑 server\.env 填入 API Key 等配置后重新运行
        echo.
    ) else (
        echo [错误] 未找到 .env 或 .env.example
        pause
        exit /b 1
    )
)

REM ---- 2. 启动数据库 ----
where docker >nul 2>&1
if !errorlevel! equ 0 (
    echo [1/4] 启动数据库容器...
    docker compose -f "%PROJECT_ROOT%docker-compose.yml" up -d
    if !errorlevel! neq 0 (
        echo [警告] Docker 启动失败，假设数据库已在本地运行
    ) else (
        echo [OK] 数据库容器已启动
    )
) else (
    echo [1/4] 未检测到 Docker，假设 PostgreSQL + Redis 已本地安装
    echo       如未安装，请联系 P1 同事配置数据库
)
echo.

REM ---- 3. 安装依赖 ----
echo [2/4] 检查 Python 依赖...
cd /d "%SERVER_DIR%"
python -m pip install -r requirements.txt --quiet 2>nul
if !errorlevel! neq 0 (
    echo [警告] pip install 有警告，尝试 uv...
    uv pip install -r requirements.txt 2>nul
)
echo [OK] 依赖检查完成
echo.

REM ---- 4. 启动 uvicorn ----
echo [3/4] 启动 FastAPI 服务...
echo       地址: http://localhost:8000
echo       Swagger: http://localhost:8000/docs
echo       按 Ctrl+C 停止
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

REM ---- 5. 健康检查（服务退出后） ----
echo.
echo [4/4] 服务已停止
pause
