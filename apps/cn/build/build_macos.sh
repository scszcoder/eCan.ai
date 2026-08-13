#!/bin/bash
# =============================================================================
# Build Script for eCan.cn (CN Version) - macOS
# =============================================================================
# Usage: ./build_macos.sh [options]
#
# Options:
#   --clean         Clean build artifacts before building
#   --test          Build for testing (no code signing)
#   --release       Build for release (with code signing)
#   --dmg           Create DMG installer
#
# Environment Variables:
#   ECAN_APP_ID     Set to 'cn' automatically
#   BUILD_NUMBER    CI build number (optional)
# =============================================================================

set -e

# Configuration
export ECAN_APP_ID="cn"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build"
DIST_DIR="$PROJECT_ROOT/dist"
VERSION="1.0.0"
BUILD_NUMBER="${BUILD_NUMBER:-1}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --clean    Clean build artifacts"
    echo "  --test     Build for testing (no signing)"
    echo "  --release  Build for release (with signing)"
    echo "  --dmg      Create DMG installer"
    echo "  --help     Show this help"
    echo ""
    exit 1
}

# Parse arguments
BUILD_MODE="test"
CREATE_DMG=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN_BUILD=true
            shift
            ;;
        --test)
            BUILD_MODE="test"
            shift
            ;;
        --release)
            BUILD_MODE="release"
            shift
            ;;
        --dmg)
            CREATE_DMG=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Pre-build checks
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed."
        exit 1
    fi

    if ! command -v pyinstaller &> /dev/null; then
        log_warn "PyInstaller not found, installing..."
        pip3 install pyinstaller
    fi

    log_info "Prerequisites OK"
}

# Clean build artifacts
clean_build() {
    log_info "Cleaning build artifacts..."

    rm -rf "$BUILD_DIR"
    rm -rf "$DIST_DIR"
    rm -rf "$PROJECT_ROOT/build"
    rm -rf "$PROJECT_ROOT/dist"
    rm -rf "$PROJECT_ROOT"/*.spec
    rm -rf "$PROJECT_ROOT"/*.egg-info
    rm -rf "$PROJECT_ROOT/__pycache__"
    find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$PROJECT_ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true

    log_info "Clean complete"
}

# Install dependencies
install_dependencies() {
    log_info "Installing dependencies..."
    cd "$PROJECT_ROOT"
    pip3 install -r requirements-cn.txt --quiet
    log_info "Dependencies installed"
}

# Run PyInstaller
build_app() {
    log_info "Building eCan.cn (CN Version)..."

    cd "$PROJECT_ROOT"

    # Use CN-specific spec file if exists
    SPEC_FILE="$PROJECT_ROOT/eCan_cn.spec"
    if [ ! -f "$SPEC_FILE" ]; then
        log_warn "CN-specific spec file not found, using default..."
        SPEC_FILE="$PROJECT_ROOT/eCan.spec"
    fi

    if [ "$BUILD_MODE" = "release" ]; then
        # Sign the app after building
        pyinstaller "$SPEC_FILE" --noconfirm --log-level=WARN

        # Code signing would go here
        if [ -f "$SCRIPT_DIR/signing_cn.json" ]; then
            log_info "Signing application..."
            # codesign --force --deep --sign "Developer ID Application: Company Name" "$DIST_DIR/eCan.cn.app"
        fi
    else
        pyinstaller "$SPEC_FILE" --noconfirm --log-level=WARN
    fi

    log_info "Build complete: $DIST_DIR"
}

# Create DMG
create_dmg() {
    log_info "Creating DMG installer..."

    local app_name="eCan.cn"
    local dmg_name="eCan_CN_v${VERSION}.dmg"
    local temp_dir="/tmp/ecan_dmg_$$"

    mkdir -p "$temp_dir"

    # Copy app to temp directory
    cp -R "$DIST_DIR/${app_name}.app" "$temp_dir/"

    # Create DMG
    hdiutil create -volname "$app_name" -srcfolder "$temp_dir" -ov -format UDZO -imagekey zlib-level=9 "$DIST_DIR/$dmg_name"

    # Cleanup
    rm -rf "$temp_dir"

    log_info "DMG created: $DIST_DIR/$dmg_name"
}

# Main
main() {
    log_info "Starting eCan.cn build..."
    log_info "Build mode: $BUILD_MODE"
    log_info "Version: $VERSION"
    log_info "Build number: $BUILD_NUMBER"

    check_prerequisites

    if [ "$CLEAN_BUILD" = true ]; then
        clean_build
    fi

    install_dependencies
    build_app

    if [ "$CREATE_DMG" = true ]; then
        create_dmg
    fi

    log_info "Build finished successfully!"
}

# Run
main
