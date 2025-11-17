#!/bin/bash
# eCan.ai 本地 OTA 开发验证脚本
# 支持快速启动、验证和调试

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目根目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 配置
SERVER_PORT=8080
SERVER_URL="http://127.0.0.1:$SERVER_PORT"
LOG_FILE="/tmp/ota_dev_server.log"

print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}\n"
}

print_info() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

check_dependencies() {
    print_header "检查依赖"
    
    local missing=0
    for pkg in flask requests cryptography; do
        if python3 -c "import $pkg" 2>/dev/null; then
            print_info "$pkg 已安装"
        else
            print_error "$pkg 未安装"
            missing=1
        fi
    done
    
    if [ $missing -eq 1 ]; then
        print_warn "缺少依赖，正在安装..."
        pip3 install flask requests cryptography
    fi
}

start_server() {
    print_header "启动本地 OTA 服务器"
    
    # 检查端口是否被占用
    if lsof -i :$SERVER_PORT > /dev/null 2>&1; then
        print_warn "端口 $SERVER_PORT 已被占用"
        print_info "尝试杀死占用进程..."
        lsof -i :$SERVER_PORT | grep LISTEN | awk '{print $2}' | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
    
    print_info "启动服务器..."
    cd "$PROJECT_ROOT/ota/server"
    python3 update_server.py > "$LOG_FILE" 2>&1 &
    SERVER_PID=$!
    
    print_info "服务器 PID: $SERVER_PID"
    print_info "日志文件: $LOG_FILE"
    
    # 等待服务器启动
    sleep 2
    
    # 检查服务器是否运行
    if curl -s "$SERVER_URL/health" > /dev/null 2>&1; then
        print_info "服务器已就绪"
        echo $SERVER_PID > /tmp/ota_server.pid
        return 0
    else
        print_error "服务器启动失败"
        cat "$LOG_FILE"
        return 1
    fi
}

stop_server() {
    if [ -f /tmp/ota_server.pid ]; then
        local pid=$(cat /tmp/ota_server.pid)
        if kill -0 $pid 2>/dev/null; then
            print_info "停止服务器 (PID: $pid)..."
            kill $pid 2>/dev/null || true
            rm /tmp/ota_server.pid
        fi
    fi
}

run_validator() {
    print_header "运行 OTA 验证工具"
    
    export ECBOT_DEV_MODE=1
    cd "$PROJECT_ROOT"
    python3 ota/local_ota_validator.py
}

run_tests() {
    print_header "运行单元测试"
    
    cd "$PROJECT_ROOT"
    python3 -m unittest tests.test_ota_core -v
    python3 -m unittest tests.test_ota_more -v
}

run_functional_test() {
    print_header "运行功能测试"
    
    export ECBOT_DEV_MODE=1
    cd "$PROJECT_ROOT"
    python3 ota/test_local_ota.py
}

show_menu() {
    echo -e "${YELLOW}请选择操作:${NC}\n"
    echo -e "  ${GREEN}1${NC}. 启动服务器"
    echo -e "  ${GREEN}2${NC}. 运行验证工具"
    echo -e "  ${GREEN}3${NC}. 运行功能测试"
    echo -e "  ${GREEN}4${NC}. 运行单元测试"
    echo -e "  ${GREEN}5${NC}. 完整验证 (启动服务器 + 验证 + 测试)"
    echo -e "  ${GREEN}6${NC}. 查看服务器日志"
    echo -e "  ${GREEN}7${NC}. 停止服务器"
    echo -e "  ${GREEN}0${NC}. 退出\n"
}

main() {
    print_header "eCan.ai OTA 本地开发验证工具"
    
    check_dependencies
    
    while true; do
        show_menu
        read -p "请输入选项 [0-7]: " choice
        
        case $choice in
            1)
                start_server
                ;;
            2)
                run_validator
                ;;
            3)
                run_functional_test
                ;;
            4)
                run_tests
                ;;
            5)
                start_server && run_validator && run_functional_test
                ;;
            6)
                if [ -f "$LOG_FILE" ]; then
                    tail -f "$LOG_FILE"
                else
                    print_error "日志文件不存在"
                fi
                ;;
            7)
                stop_server
                ;;
            0)
                print_info "再见!"
                stop_server
                exit 0
                ;;
            *)
                print_error "无效的选项"
                ;;
        esac
    done
}

# 处理 Ctrl+C
trap 'echo ""; stop_server; exit 0' INT

main

