#!/bin/bash
# Windows build script for eCan (CN | Intl).
# Usage: ./build_windows.sh --app=cn|intl [version] [mode]
#
# Replaces the previous apps/{cn,intl}/build/build_windows.sh pair.
set -e

if [[ "$1" != --app=* ]]; then
    echo "Usage: $0 --app=cn|intl [version] [mode]"
    exit 1
fi
APP_ID=${1#--app=}
VERSION=${2:-$(cat ../VERSION | tr -d '[:space:]')}
MODE=${3:-prod}

if [ "$APP_ID" != "cn" ] && [ "$APP_ID" != "intl" ]; then
    echo "[ERROR] --app must be cn or intl (got: $APP_ID)"
    exit 1
fi

cd "$(dirname "$0")/../.."
export ECAN_APP_ID=$APP_ID

echo "========================================"
echo "Building eCan ($APP_ID) Windows"
echo "Version: $VERSION   Mode: $MODE"
echo "========================================"

echo "[1/2] Running unified build (PyInstaller + Inno)..."
python build_system/unified_build.py "$MODE" \
    --app="$APP_ID" \
    --skip-signing \
    --version="$VERSION"

ls -lh dist/*.exe 2>/dev/null || true
