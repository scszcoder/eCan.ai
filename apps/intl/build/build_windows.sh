#!/bin/bash
# Windows build script for Intl app (GitHub Actions / CI)
# Usage: ./build_windows.sh [version] [mode]
set -e

VERSION=${1:-$(cat ../../VERSION | tr -d '[:space:]')}
MODE=${2:-prod}

echo "========================================"
echo "Building eCan Windows"
echo "Version: $VERSION"
echo "Mode: $MODE"
echo "========================================"

cd "$(dirname "$0")/../.."
export ECAN_APP_ID=intl

echo "[1/2] Running unified build..."
python build_system/unified_build.py "$MODE" \
  --app=intl \
  --skip-signing \
  --version="$VERSION"

echo "[2/2] Done."
ls -lh dist/*.exe 2>/dev/null || true
