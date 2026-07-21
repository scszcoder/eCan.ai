#!/bin/bash
# Linux build script for Intl app
# Usage: ./build_linux.sh [version] [mode]
set -e

VERSION=${1:-$(cat ../../VERSION | tr -d '[:space:]')}
MODE=${2:-prod}

echo "Building eCan Linux (DEB)"
cd "$(dirname "$0")/../.."
export ECAN_APP_ID=intl

python build_system/unified_build.py "$MODE" \
  --app=intl \
  --skip-signing \
  --version="$VERSION"

ls -lh dist/*.deb dist/*.AppImage 2>/dev/null || true
