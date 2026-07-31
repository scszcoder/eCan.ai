#!/bin/bash
# Linux build script for eCan (CN | Intl).
# Usage: ./build_linux.sh --app=cn|intl [version] [mode]
#
# Replaces the previous apps/{cn,intl}/build/build_linux.sh pair — they
# were textually identical except for the app_id passed to unified_build.
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
python build_system/unified_build.py "$MODE" \
    --app="$APP_ID" \
    --skip-signing \
    --version="$VERSION"

ls -lh dist/*.deb dist/*.AppImage 2>/dev/null || true
