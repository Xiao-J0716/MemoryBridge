#!/usr/bin/env bash
# 准备 P4(ASR) 运行所需二进制资产：
#   1) Vosk 中文模型 vosk-model-small-cn-0.22（约42MB，不入库）
#   2) libvosk.so（4 个 ABI，正常随仓库已提交；此处仅在缺失时补全）
#
# 在仓库 app/ 目录下运行： bash scripts/setup-asr-assets.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS_MODELS="$ROOT/client/app/src/main/assets/models"
JNILIBS="$ROOT/client/app/src/main/jniLibs"
VOSK_VER="0.3.45"
MODEL_NAME="vosk-model-small-cn-0.22"
TMP="$ROOT/.tmp_asr"

mkdir -p "$ASSETS_MODELS" "$JNILIBS" "$TMP"

# 解压工具：优先 unzip，否则 python（团队均可用 python）
extract() { # $1=zip  $2=dest
  if command -v unzip >/dev/null 2>&1; then
    unzip -oq "$1" -d "$2"
  else
    python -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$1" "$2"
  fi
}

# ---------- 1) Vosk 中文模型 ----------
if [ -d "$ASSETS_MODELS/$MODEL_NAME/am" ]; then
  echo "[model] 已存在，跳过"
else
  url="https://alphacephei.com/vosk/models/${MODEL_NAME}.zip"
  echo "[model] 下载 $MODEL_NAME.zip (~42MB) ..."
  curl -L -o "$TMP/model.zip" "$url"
  echo "[model] 解压到 $ASSETS_MODELS"
  extract "$TMP/model.zip" "$ASSETS_MODELS"
  rm -f "$TMP/model.zip"
  [ -d "$ASSETS_MODELS/$MODEL_NAME/am" ] || { echo "[model] 解压后未找到 $MODEL_NAME/am，请检查 zip 结构" >&2; exit 1; }
  echo "[model] 完成：$ASSETS_MODELS/$MODEL_NAME"
fi

# ---------- 2) libvosk.so（仅在缺失时补全；正常已随仓库提交） ----------
if [ -f "$JNILIBS/arm64-v8a/libvosk.so" ]; then
  echo "[so] 已存在，跳过"
else
  url="https://github.com/alphacep/vosk-api/releases/download/v${VOSK_VER}/vosk-android-${VOSK_VER}.zip"
  echo "[so] 下载 vosk-android-${VOSK_VER}.zip (~12MB) ..."
  curl -L -o "$TMP/aar.zip" "$url"
  echo "[so] 解压 .so 到 $JNILIBS"
  extract "$TMP/aar.zip" "$TMP/aar_x"
  for abi in arm64-v8a armeabi-v7a x86 x86_64; do
    if [ -f "$TMP/aar_x/$abi/libvosk.so" ]; then
      mkdir -p "$JNILIBS/$abi"
      mv -f "$TMP/aar_x/$abi/libvosk.so" "$JNILIBS/$abi/libvosk.so"
      echo "[so] $abi ok"
    fi
  done
  rm -rf "$TMP/aar.zip" "$TMP/aar_x"
  [ -f "$JNILIBS/arm64-v8a/libvosk.so" ] || { echo "[so] 未提取到 libvosk.so，请手动" >&2; exit 1; }
  echo "[so] 完成"
fi

rmdir "$TMP" 2>/dev/null || true
echo "P4 ASR 资产准备完成。现在可以构建运行。"
