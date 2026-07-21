#!/bin/bash
# Linux build script for CN app
# Usage: ./build_linux.sh [version] [mode]
set -e

VERSION=${1:-$(cat ../../VERSION | tr -d '[:space:]')}
MODE=${2:-prod}

echo "Building eCan.cn Linux (DEB)"
cd "$(dirname "$0")/../.."
export ECAN_APP_ID=cn

python build_system/unified_build.py "$MODE" \
  --app=cn \
  --skip-signing \
  --version="$VERSION"

ls -lh dist/*.deb dist/*.AppImage 2>/dev/null || true
