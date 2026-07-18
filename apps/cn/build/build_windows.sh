#!/bin/bash
# Windows build script for CN app (GitHub Actions / CI)
# Usage: ./build_windows.bat [version] [mode]
set -e

VERSION=${1:-$(cat ../../VERSION | tr -d '[:space:]')}
MODE=${2:-prod}

echo "========================================"
echo "Building eCan.cn Windows"
echo "Version: $VERSION"
echo "Mode: $MODE"
echo "========================================"

cd "$(dirname "$0")/../.."
export ECAN_APP_ID=cn

echo "[1/2] Running unified build..."
python build_system/unified_build.py "$MODE" \
  --app=cn \
  --skip-signing \
  --version="$VERSION"

echo "[2/2] Done."
ls -lh dist/*.exe 2>/dev/null || true
