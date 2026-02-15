#!/bin/bash
# ============================================================================
# eCan.ai Ubuntu Server Deployment Script
# ============================================================================
# This script sets up and runs eCan.ai in headless/web mode on Ubuntu server.
#
# Usage:
#   chmod +x scripts/deploy-ubuntu.sh
#   ./scripts/deploy-ubuntu.sh [command]
#
# Commands:
#   setup     - Install dependencies and configure environment
#   start     - Start the web server
#   stop      - Stop the web server
#   restart   - Restart the web server
#   status    - Check server status
#   logs      - View server logs
#   help      - Show this help message
#
# Environment Variables:
#   ECAN_WS_HOST    - WebSocket host (default: 0.0.0.0)
#   ECAN_WS_PORT    - WebSocket port (default: 8765)
#   ECAN_LOG_LEVEL  - Logging level (default: INFO)
#   ECAN_VENV_PATH  - Virtual environment path (default: ./venv)
# ============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PATH="${ECAN_VENV_PATH:-$PROJECT_ROOT/venv}"
PID_FILE="$PROJECT_ROOT/.ecan-web.pid"
LOG_FILE="$PROJECT_ROOT/runlogs/web_server.log"

# Default environment variables
export ECAN_MODE="web"
export ECAN_WS_HOST="${ECAN_WS_HOST:-0.0.0.0}"
export ECAN_WS_PORT="${ECAN_WS_PORT:-8765}"
export ECAN_LOG_LEVEL="${ECAN_LOG_LEVEL:-INFO}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        log_error "Python not found. Please install Python 3.12+ first."
        exit 1
    fi
    
    # Check Python version
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log_info "Found Python $PYTHON_VERSION"
}

activate_venv() {
    if [ -d "$VENV_PATH" ]; then
        source "$VENV_PATH/bin/activate"
        log_info "Activated virtual environment: $VENV_PATH"
    else
        log_warning "Virtual environment not found at $VENV_PATH"
        log_info "Run './scripts/deploy-ubuntu.sh setup' first"
        exit 1
    fi
}

# Command: setup
cmd_setup() {
    log_info "Setting up eCan.ai for Ubuntu server deployment..."
    
    cd "$PROJECT_ROOT"
    check_python
    
    # Install system dependencies
    log_info "Installing system dependencies..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y \
            python3-venv \
            python3-pip \
            libpq-dev \
            gcc \
            libffi-dev \
            tesseract-ocr \
            poppler-utils
    else
        log_warning "apt-get not found. Please install dependencies manually."
    fi
    
    # Create virtual environment
    if [ ! -d "$VENV_PATH" ]; then
        log_info "Creating virtual environment at $VENV_PATH..."
        $PYTHON_CMD -m venv "$VENV_PATH"
    else
        log_info "Virtual environment already exists at $VENV_PATH"
    fi
    
    # Activate and install dependencies
    source "$VENV_PATH/bin/activate"
    
    log_info "Upgrading pip..."
    pip install --upgrade pip
    
    log_info "Installing web dependencies..."
    pip install -r requirements-web.txt
    
    # Install Playwright browsers (headless)
    log_info "Installing Playwright browsers..."
    playwright install chromium --with-deps || log_warning "Playwright browser installation failed (optional)"
    
    # Create runlogs directory
    mkdir -p "$PROJECT_ROOT/runlogs"
    
    # Create .env file if not exists
    if [ ! -f "$PROJECT_ROOT/.env.web" ]; then
        log_info "Creating .env.web configuration file..."
        cat > "$PROJECT_ROOT/.env.web" << EOF
# eCan.ai Web Server Configuration
ECAN_MODE=web
ECAN_WS_HOST=0.0.0.0
ECAN_WS_PORT=8765
ECAN_LOG_LEVEL=INFO

# Add your API keys here
# OPENAI_API_KEY=your_key_here
# ANTHROPIC_API_KEY=your_key_here
EOF
    fi
    
    log_success "Setup complete!"
    log_info "Next steps:"
    echo "  1. Edit .env.web to add your API keys"
    echo "  2. Run: ./scripts/deploy-ubuntu.sh start"
}

# Command: start
cmd_start() {
    log_info "Starting eCan.ai web server..."
    
    cd "$PROJECT_ROOT"
    activate_venv
    
    # Check if already running
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            log_warning "Server already running with PID $PID"
            log_info "Use './scripts/deploy-ubuntu.sh restart' to restart"
            exit 0
        else
            rm -f "$PID_FILE"
        fi
    fi
    
    # Load environment from .env.web if exists
    if [ -f "$PROJECT_ROOT/.env.web" ]; then
        log_info "Loading environment from .env.web..."
        set -a
        source "$PROJECT_ROOT/.env.web"
        set +a
    fi
    
    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")"
    
    # Start server
    log_info "Starting server on ws://$ECAN_WS_HOST:$ECAN_WS_PORT..."
    
    nohup python -m uvicorn web_server:app \
        --host "$ECAN_WS_HOST" \
        --port "$ECAN_WS_PORT" \
        --log-level "${ECAN_LOG_LEVEL,,}" \
        >> "$LOG_FILE" 2>&1 &
    
    echo $! > "$PID_FILE"
    
    sleep 2
    
    # Verify server started
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            log_success "Server started with PID $PID"
            log_info "WebSocket: ws://$ECAN_WS_HOST:$ECAN_WS_PORT"
            log_info "Health check: http://$ECAN_WS_HOST:$ECAN_WS_PORT/health"
            log_info "Logs: $LOG_FILE"
        else
            log_error "Server failed to start. Check logs: $LOG_FILE"
            rm -f "$PID_FILE"
            exit 1
        fi
    fi
}

# Command: stop
cmd_stop() {
    log_info "Stopping eCan.ai web server..."
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            kill "$PID"
            sleep 2
            
            # Force kill if still running
            if ps -p "$PID" > /dev/null 2>&1; then
                log_warning "Server not responding, force killing..."
                kill -9 "$PID"
            fi
            
            rm -f "$PID_FILE"
            log_success "Server stopped"
        else
            log_warning "Server not running (stale PID file)"
            rm -f "$PID_FILE"
        fi
    else
        log_warning "No PID file found. Server may not be running."
    fi
}

# Command: restart
cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

# Command: status
cmd_status() {
    echo "============================================"
    echo "eCan.ai Web Server Status"
    echo "============================================"
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "Status: ${GREEN}RUNNING${NC}"
            echo "PID: $PID"
            echo "WebSocket: ws://$ECAN_WS_HOST:$ECAN_WS_PORT"
            echo ""
            
            # Try health check
            if command -v curl &> /dev/null; then
                echo "Health Check:"
                curl -s "http://localhost:$ECAN_WS_PORT/health" 2>/dev/null || echo "  (health endpoint not responding)"
            fi
        else
            echo -e "Status: ${RED}STOPPED${NC} (stale PID file)"
            rm -f "$PID_FILE"
        fi
    else
        echo -e "Status: ${YELLOW}NOT RUNNING${NC}"
    fi
    
    echo ""
    echo "Log file: $LOG_FILE"
    echo "============================================"
}

# Command: logs
cmd_logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        log_warning "Log file not found: $LOG_FILE"
    fi
}

# Command: help
cmd_help() {
    echo "============================================"
    echo "eCan.ai Ubuntu Server Deployment Script"
    echo "============================================"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  setup     Install dependencies and configure environment"
    echo "  start     Start the web server (background)"
    echo "  stop      Stop the web server"
    echo "  restart   Restart the web server"
    echo "  status    Check server status"
    echo "  logs      View server logs (tail -f)"
    echo "  help      Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  ECAN_WS_HOST    WebSocket host (default: 0.0.0.0)"
    echo "  ECAN_WS_PORT    WebSocket port (default: 8765)"
    echo "  ECAN_LOG_LEVEL  Logging level (default: INFO)"
    echo "  ECAN_VENV_PATH  Virtual environment path (default: ./venv)"
    echo ""
    echo "Examples:"
    echo "  $0 setup              # First-time setup"
    echo "  $0 start              # Start server"
    echo "  ECAN_WS_PORT=9000 $0 start  # Start on custom port"
    echo ""
}

# Main
case "${1:-help}" in
    setup)
        cmd_setup
        ;;
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status)
        cmd_status
        ;;
    logs)
        cmd_logs
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        log_error "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
