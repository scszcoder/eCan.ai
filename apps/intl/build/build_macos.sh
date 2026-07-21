#!/bin/bash
# macOS PKG build script for Intl app
# Usage: ./build_macos.sh [version] [mode]
set -e

VERSION=${1:-$(cat ../../../VERSION | tr -d '[:space:]')}
MODE=${2:-prod}
APP_NAME="eCan"
BUNDLE_ID="com.ecan.app"
URL_SCHEME="ecan"

echo "========================================"
echo "Building eCan macOS PKG"
echo "Version: $VERSION"
echo "Mode: $MODE"
echo "========================================"

cd "$(dirname "$0")/../../.."
export ECAN_APP_ID=intl

echo "[1/4] Running PyInstaller..."
python build_system/unified_build.py "$MODE" \
  --app=intl \
  --skip-installer \
  --skip-signing \
  --version="$VERSION"

echo "[2/4] Creating macOS PKG..."
productbuild \
  --component "dist/eCan.app" /Applications \
  --sign "" \
  --product "dist/Info.plist" \
  "dist/eCan-${VERSION}-macos.pkg" || true

echo "[3/4] Creating app bundle tarball..."
mkdir -p "dist/macos"
tar -czf "dist/macos/eCan-${VERSION}-macos.tar.gz" -C dist eCan.app || true

echo "[4/4] Done. Artifacts in dist/"
ls -lh dist/*.pkg dist/macos/ 2>/dev/null || true
