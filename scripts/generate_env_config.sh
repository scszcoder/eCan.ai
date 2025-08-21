#!/bin/bash
# ECBot Environment Variables Configuration Generator - macOS/Linux Version
# Automatically find ECan installation path and generate .env file

set -e  # Exit on error

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored messages
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

print_error() {
    print_message "$RED" "❌ $1"
}

print_success() {
    print_message "$GREEN" "✅ $1"
}

print_info() {
    print_message "$BLUE" "ℹ️  $1"
}

print_warning() {
    print_message "$YELLOW" "⚠️  $1"
}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo
echo "========================================"
echo "  ECBot Environment Config Generator ($(uname -s))"
echo "========================================"
echo

# Find ECan installation path and bundle directory
ECAN_PATH=""
BUNDLE_DIR=""
ENV_PATH=""

print_info "Searching for ECan installation path..."

# 1. Check for running ECan processes
if command -v pgrep &> /dev/null; then
    ECAN_PID=$(pgrep -f "ECan\|eCan" | head -1)
    if [ -n "$ECAN_PID" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS: Use ps to get process path
            ECAN_EXEC=$(ps -p $ECAN_PID -o comm= 2>/dev/null)
            if [ -n "$ECAN_EXEC" ] && [ -f "$ECAN_EXEC" ]; then
                if [[ "$ECAN_EXEC" == *.app/* ]]; then
                    # Extract Resources path from .app bundle
                    ECAN_PATH=$(echo "$ECAN_EXEC" | sed 's|/Contents/MacOS/.*|/Contents/Resources|')
                else
                    ECAN_PATH="$(dirname "$ECAN_EXEC")"
                fi
                print_success "Detected running ECan process"
            fi
        else
            # Linux: Use /proc to get process path
            ECAN_EXEC=$(readlink -f "/proc/$ECAN_PID/exe" 2>/dev/null)
            if [ -n "$ECAN_EXEC" ] && [ -f "$ECAN_EXEC" ]; then
                ECAN_PATH="$(dirname "$ECAN_EXEC")"
                print_success "Detected running ECan process"
            fi
        fi
    fi
fi

# 2. Check common installation paths
if [ -z "$ECAN_PATH" ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        COMMON_PATHS=(
            "/Applications/eCan.app"
            "/Applications/ECan.app"
            "$HOME/Applications/eCan.app"
            "$HOME/Applications/eCan.app"
            "/usr/local/bin/eCan"
            "/usr/local/bin/eCan"
        )

        for path in "${COMMON_PATHS[@]}"; do
            if [ -e "$path" ]; then
                if [[ "$path" == *.app ]]; then
                    ECAN_PATH="$path/Contents/Resources"
                else
                    ECAN_PATH="$(dirname "$path")"
                fi
                break
            fi
        done
    else
        # Linux paths
        COMMON_PATHS=(
            "/usr/local/bin/eCan"
            "/usr/local/bin/ECan"
            "/usr/bin/eCan"
            "/usr/bin/ECan"
            "$HOME/.local/bin/eCan"
            "$HOME/.local/bin/ECan"
            "/opt/eCan"
            "/opt/ECan"
        )

        for path in "${COMMON_PATHS[@]}"; do
            if [ -e "$path" ]; then
                ECAN_PATH="$(dirname "$path")"
                break
            fi
        done
    fi
fi

# 3. Check current directory and parent directory
if [ -z "$ECAN_PATH" ]; then
    if [ -f "$SCRIPT_DIR/../ECan" ] || [ -f "$SCRIPT_DIR/../eCan" ] || [ -f "$SCRIPT_DIR/../ECan.exe" ] || [ -f "$SCRIPT_DIR/../eCan.exe" ]; then
        ECAN_PATH="$(dirname "$SCRIPT_DIR")"
    fi
fi

# 4. Check temporary directory (PyInstaller runtime)
if [ -z "$ECAN_PATH" ]; then
    # Check _MEI temporary directories in /tmp
    for tmpdir in /tmp/_MEI* /var/tmp/_MEI* 2>/dev/null; do
        if [ -d "$tmpdir" ] && ([ -f "$tmpdir/ECan" ] || [ -f "$tmpdir/eCan" ]); then
            BUNDLE_DIR="$tmpdir"
            ECAN_PATH="$tmpdir"
            print_success "Detected PyInstaller runtime environment"
            break
        fi
    done
fi

# 5. Manual path input
if [ -z "$ECAN_PATH" ]; then
    print_error "Could not automatically find ECan installation path"
    echo
    print_info "💡 Tips:"
    echo "   - If ECan is running, please close ECan before running this script"
    echo "   - For PyInstaller packaged applications, run this script while ECan is running"
    echo
    echo "Please choose:"
    echo "1. Manually enter ECan installation directory path"
    echo "2. Manually enter bundle directory path (PyInstaller temporary directory)"
    read -p "Please choose (1/2): " CHOICE

    if [ "$CHOICE" = "2" ]; then
        echo
        echo "Please enter bundle directory path (usually starts with /tmp/_MEI):"
        read -p "Bundle path: " BUNDLE_DIR
        if [ -d "$BUNDLE_DIR" ]; then
            ECAN_PATH="$BUNDLE_DIR"
        else
            print_error "Specified bundle directory does not exist: $BUNDLE_DIR"
            exit 1
        fi
    else
        echo
        echo "Please manually enter ECan installation directory path:"
        read -p "ECan path: " ECAN_PATH

        if [ ! -d "$ECAN_PATH" ]; then
            print_error "Specified path does not exist: $ECAN_PATH"
            exit 1
        fi
    fi
fi

print_success "Found ECan path: $ECAN_PATH"

# Determine .env file path
if [ -n "$BUNDLE_DIR" ]; then
    ENV_PATH="$BUNDLE_DIR/.env"
    print_info "📄 .env file will be saved to bundle directory: $ENV_PATH"
    print_warning "⚠️  Note: PyInstaller temporary directory will be deleted after application closes"
    echo "   Consider placing configuration file in a persistent directory"
else
    ENV_PATH="$ECAN_PATH/.env"
    print_info "📄 .env file will be saved to: $ENV_PATH"
fi
echo

# Check existing configuration
if [ -f "$ENV_PATH" ]; then
    print_info "📁 Found existing configuration file: $ENV_PATH"
    read -p "Do you want to update existing configuration? (Y/n): " UPDATE_CONFIG
    if [[ "$UPDATE_CONFIG" =~ ^[Nn]$ ]]; then
        echo "Operation cancelled"
        exit 0
    fi
fi

# Collect configuration information
echo "📋 Please enter API key configuration:"
echo "========================================"
echo

# API key configuration
echo "🔑 API Key Configuration:"
echo "----------------------------------------"

echo "OpenAI API Key (input will be hidden, optional):"
read -s OPENAI_API_KEY

echo "DashScope API Key (input will be hidden, optional):"
read -s DASHSCOPE_API_KEY

echo "Claude API Key (input will be hidden, optional):"
read -s CLAUDE_API_KEY

echo "Gemini API Key (input will be hidden, optional):"
read -s GEMINI_API_KEY

echo

# Basic configuration
echo "⚙️ Basic Configuration:"
echo "----------------------------------------"
read -p "Debug mode (true/false) [false]: " DEBUG_MODE
DEBUG_MODE=${DEBUG_MODE:-false}

read -p "Log level (DEBUG/INFO/WARNING/ERROR) [INFO]: " LOG_LEVEL
LOG_LEVEL=${LOG_LEVEL:-INFO}

echo

# Display configuration summary
echo "========================================"
echo "📋 Configuration Summary:"
echo "========================================"
[ -n "$OPENAI_API_KEY" ] && echo "OpenAI API: Configured"
[ -n "$DASHSCOPE_API_KEY" ] && echo "DashScope API: Configured"
[ -n "$CLAUDE_API_KEY" ] && echo "Claude API: Configured"
[ -n "$GEMINI_API_KEY" ] && echo "Gemini API: Configured"
echo "Log level: $LOG_LEVEL"
echo "Debug mode: $DEBUG_MODE"
echo
echo "📂 Target file: $ENV_PATH"
echo

read -p "Confirm generating .env file? (Y/n): " CONFIRM
if [[ "$CONFIRM" =~ ^[Nn]$ ]]; then
    echo "Operation cancelled"
    exit 0
fi

# Generate .env file
echo
print_info "📝 Generating .env file..."

cat > "$ENV_PATH" << EOF
# ECBot Environment Variables Configuration File
# Generated: $(date)
# Platform: $(uname -s)
# ECan Path: $ECAN_PATH$(if [ -n "$BUNDLE_DIR" ]; then echo "
# Bundle Directory: $BUNDLE_DIR
# Runtime Mode: PyInstaller Package"; else echo "
# Runtime Mode: Standard Installation"; fi)

# API Key Configuration$(if [ -n "$OPENAI_API_KEY" ]; then echo "
# OpenAI API Key
OPENAI_API_KEY=$OPENAI_API_KEY"; fi)$(if [ -n "$DASHSCOPE_API_KEY" ]; then echo "
# DashScope API Key
DASHSCOPE_API_KEY=$DASHSCOPE_API_KEY"; fi)$(if [ -n "$CLAUDE_API_KEY" ]; then echo "
# Claude API Key
CLAUDE_API_KEY=$CLAUDE_API_KEY"; fi)$(if [ -n "$GEMINI_API_KEY" ]; then echo "
# Gemini API Key
GEMINI_API_KEY=$GEMINI_API_KEY"; fi)

# Basic Configuration
# Log Level
LOG_LEVEL=$LOG_LEVEL
# Debug Mode
DEBUG_MODE=$DEBUG_MODE
EOF

if [ -f "$ENV_PATH" ]; then
    print_success ".env file generated successfully!"
    print_info "📄 File location: $ENV_PATH"
    echo
    print_info "💡 Tips:"
    echo "   - Restart ECan application to apply new configuration"
    echo "   - Please keep this configuration file secure, it contains sensitive information"
    echo "   - Do not share this file with others"

    # macOS specific tips
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo
        print_info "macOS specific tips:"
        echo "   - If ECan was installed through App Store, you may need to reinstall"
        echo "   - Configuration file is located in the application bundle's Resources directory"
        echo "   - You can use 'open' command to view configuration file location"
    fi
else
    print_error ".env file generation failed!"
    echo "Please check if you have write permissions"
    exit 1
fi

echo
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Press Enter to exit..."
    read
fi

exit 0
