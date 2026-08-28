#!/bin/bash
# macOS build script for eCan (CN | Intl).
# Usage: ./build_macos.sh --app=cn|intl [version] [mode]
#
# Replaces the previous apps/{cn,intl}/build/build_macos.sh pair.
set -e

if [[ "$1" != --app=* ]]; then
    echo "Usage: $0 --app=cn|intl [version] [mode]"
    exit 1
fi
APP_ID=${1#--app=}
VERSION=${2:-$(cat ../VERSION 2>/dev/null || cat ../../VERSION | tr -d '[:space:]')}
MODE=${3:-prod}

if [ "$APP_ID" != "cn" ] && [ "$APP_ID" != "intl" ]; then
    echo "[ERROR] --app must be cn or intl (got: $APP_ID)"
    exit 1
fi

APP_NAME="eCan.cn"
[ "$APP_ID" = "intl" ] && APP_NAME="eCan"

cd "$(dirname "$0")/../.."
export ECAN_APP_ID=$APP_ID

echo "========================================"
echo "Building $APP_NAME macOS PKG"
echo "Version: $VERSION   Mode: $MODE"
echo "========================================"

echo "[1/3] Running unified build..."
python build_system/unified_build.py "$MODE" \
    --app="$APP_ID" \
    --skip-installer \
    --skip-signing \
    --version="$VERSION"

echo "[2/3] Creating macOS PKG..."
productbuild \
    --component "dist/$APP_NAME.app" /Applications \
    --sign "" \
    --product "dist/Info.plist" \
    "dist/$APP_NAME-$VERSION-macos.pkg" || true

echo "[3/3] Creating app bundle tarball..."
mkdir -p "dist/macos"
tar -czf "dist/macos/$APP_NAME-$VERSION-macos.tar.gz" -C dist "$APP_NAME.app" || true

ls -lh dist/*.pkg dist/macos/ 2>/dev/null || true
