#!/bin/bash
# macOS PKG build script for CN app
# Usage: ./build_macos.sh [version] [mode]
set -e

VERSION=${1:-$(cat ../../../VERSION | tr -d '[:space:]')}
MODE=${2:-prod}
APP_NAME="eCan.cn"
BUNDLE_ID="com.ecan.cn.app"
URL_SCHEME="ecan-cn"

echo "========================================"
echo "Building eCan.cn macOS PKG"
echo "Version: $VERSION"
echo "Mode: $MODE"
echo "========================================"

cd "$(dirname "$0")/../../.."
export ECAN_APP_ID=cn

echo "[1/4] Running PyInstaller..."
python build_system/unified_build.py "$MODE" \
  --app=cn \
  --skip-installer \
  --skip-signing \
  --version="$VERSION"

echo "[2/4] Creating macOS PKG..."
productbuild \
  --component "dist/eCan.cn.app" /Applications \
  --sign "" \
  --product "dist/Info.plist" \
  "dist/eCan.cn-${VERSION}-macos.pkg" || true

echo "[3/4] Creating app bundle tarball..."
mkdir -p "dist/macos"
tar -czf "dist/macos/eCan.cn-${VERSION}-macos.tar.gz" -C dist eCan.cn.app || true

echo "[4/4] Done. Artifacts in dist/"
ls -lh dist/*.pkg dist/macos/ 2>/dev/null || true
