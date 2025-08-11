#!/bin/bash
# ECBot 快速日志查看脚本 (示例)
# NOTE: This is an example helper script intended for local debugging.
# It is not required for production builds and may be safely removed from packaging.
# 用于快速查看生产环境的启动日志和崩溃日志

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 检测操作系统
OS=$(uname -s)

# 设置日志路径
if [[ "$OS" == "Darwin" ]]; then
    # macOS
    PROD_LOG_DIR="$HOME/Library/Application Support/ecbot/runlogs"
    CRASH_LOG_DIR="$HOME/Library/Logs/DiagnosticReports"
    DEV_LOG_DIR="./runlogs"
elif [[ "$OS" == "Linux" ]] || [[ "$OS" == "MINGW"* ]] || [[ "$OS" == "CYGWIN"* ]]; then
    # Windows/Linux
    if [[ -n "$ECBOT_DATA_HOME" ]]; then
        PROD_LOG_DIR="$ECBOT_DATA_HOME/runlogs"
    else
        PROD_LOG_DIR=""
    fi
    CRASH_LOG_DIR=""
    DEV_LOG_DIR="./runlogs"
fi

# 获取主日志文件路径
get_main_log() {
    # 优先使用开发环境日志
    if [[ -f "$DEV_LOG_DIR/ecbot.log" ]]; then
        echo "$DEV_LOG_DIR/ecbot.log"
    elif [[ -f "$PROD_LOG_DIR/ecbot.log" ]]; then
        echo "$PROD_LOG_DIR/ecbot.log"
    else
        echo ""
    fi
}

# 显示帮助信息
show_help() {
    echo -e "${CYAN}ECBot 快速日志查看工具${NC}"
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help      显示此帮助信息"
    echo "  -l, --list      列出日志文件"
    echo "  -v, --view [N]  查看主日志最后N行 (默认50)"
    echo "  -f, --follow    实时跟踪主日志"
    echo "  -e, --errors    只显示错误和异常"
    echo "  -s, --startup   分析启动日志"
    echo "  -c, --crash     查看崩溃日志 (仅macOS)"
    echo "  -w, --warnings  显示警告和错误"
    echo "  --search TERM   搜索特定内容"
    echo ""
    echo "示例:"
    echo "  $0 -v 100       # 查看最后100行日志"
    echo "  $0 -f           # 实时跟踪日志"
    echo "  $0 -e           # 只显示错误"
    echo "  $0 --search 'startup'  # 搜索包含startup的日志"
}

# 列出日志文件
list_logs() {
    echo -e "${CYAN}📋 ECBot 日志文件列表${NC}"
    echo "=================================================="
    
    # 开发环境日志
    if [[ -d "$DEV_LOG_DIR" ]]; then
        echo -e "\n${GREEN}📁 开发环境: $DEV_LOG_DIR${NC}"
        ls -lah "$DEV_LOG_DIR"/*.log* 2>/dev/null | while read line; do
            echo "  $line"
        done
    fi
    
    # 生产环境日志
    if [[ -d "$PROD_LOG_DIR" ]]; then
        echo -e "\n${GREEN}📁 生产环境: $PROD_LOG_DIR${NC}"
        ls -lah "$PROD_LOG_DIR"/*.log* 2>/dev/null | while read line; do
            echo "  $line"
        done
        
        # 用户日志目录
        if ls "$PROD_LOG_DIR"/*/ >/dev/null 2>&1; then
            echo -e "\n${YELLOW}👤 用户日志目录:${NC}"
            for user_dir in "$PROD_LOG_DIR"/*/; do
                if [[ -d "$user_dir" ]]; then
                    user_name=$(basename "$user_dir")
                    echo "  📂 $user_name/"
                    
                    # 查找用户的日志文件
                    user_log_path="$user_dir/runlogs/$user_name"
                    if [[ -d "$user_log_path" ]]; then
                        for year_dir in "$user_log_path"/*/; do
                            if [[ -d "$year_dir" ]]; then
                                year=$(basename "$year_dir")
                                log_count=$(ls "$year_dir"/log*.txt 2>/dev/null | wc -l)
                                if [[ $log_count -gt 0 ]]; then
                                    echo "    📅 $year/ ($log_count 文件)"
                                fi
                            fi
                        done
                    fi
                fi
            done
        fi
    fi
}

# 查看主日志
view_main_log() {
    local lines=${1:-50}
    local main_log=$(get_main_log)
    
    if [[ -z "$main_log" ]]; then
        echo -e "${RED}❌ 未找到主日志文件${NC}"
        return 1
    fi
    
    echo -e "${CYAN}📖 查看主日志: $main_log${NC}"
    echo "=================================================="
    
    tail -n "$lines" "$main_log"
}

# 实时跟踪日志
follow_log() {
    local main_log=$(get_main_log)
    
    if [[ -z "$main_log" ]]; then
        echo -e "${RED}❌ 未找到主日志文件${NC}"
        return 1
    fi
    
    echo -e "${CYAN}📡 实时跟踪日志: $main_log${NC}"
    echo -e "${YELLOW}按 Ctrl+C 停止${NC}"
    echo "=================================================="
    
    tail -f "$main_log"
}

# 显示错误日志
show_errors() {
    local main_log=$(get_main_log)
    
    if [[ -z "$main_log" ]]; then
        echo -e "${RED}❌ 未找到主日志文件${NC}"
        return 1
    fi
    
    echo -e "${RED}🚨 错误和异常日志${NC}"
    echo "=================================================="
    
    grep -i -E "(error|exception|traceback|critical)" "$main_log" | tail -20
}

# 显示警告和错误
show_warnings() {
    local main_log=$(get_main_log)
    
    if [[ -z "$main_log" ]]; then
        echo -e "${RED}❌ 未找到主日志文件${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}⚠️  警告和错误日志${NC}"
    echo "=================================================="
    
    grep -i -E "(warning|error|exception|critical)" "$main_log" | tail -30
}

# 分析启动日志
analyze_startup() {
    local main_log=$(get_main_log)
    
    if [[ -z "$main_log" ]]; then
        echo -e "${RED}❌ 未找到主日志文件${NC}"
        return 1
    fi
    
    echo -e "${BLUE}🚀 启动日志分析${NC}"
    echo "=================================================="
    
    echo -e "\n${GREEN}📱 应用启动:${NC}"
    grep -i "app start\|main function run start" "$main_log" | tail -3
    
    echo -e "\n${GREEN}🔧 初始化:${NC}"
    grep -i "init.*object\|setup" "$main_log" | tail -5
    
    echo -e "\n${GREEN}🌐 运行模式:${NC}"
    grep -i "running in.*mode" "$main_log" | tail -2
    
    echo -e "\n${GREEN}📡 服务注册:${NC}"
    grep -i "registered.*handler" "$main_log" | tail -5
    
    echo -e "\n${RED}❌ 启动错误:${NC}"
    grep -i -A2 -B2 "error\|exception" "$main_log" | grep -A2 -B2 -i "start\|init\|setup" | tail -10
}

# 查看崩溃日志
view_crash_logs() {
    if [[ "$OS" != "Darwin" ]]; then
        echo -e "${RED}❌ 崩溃日志查看目前仅支持 macOS${NC}"
        return 1
    fi
    
    if [[ ! -d "$CRASH_LOG_DIR" ]]; then
        echo -e "${RED}❌ 未找到崩溃日志目录: $CRASH_LOG_DIR${NC}"
        return 1
    fi
    
    echo -e "${PURPLE}💥 ECBot 崩溃日志${NC}"
    echo "=================================================="
    
    # 查找 ECBot 相关的崩溃报告
    crash_files=$(find "$CRASH_LOG_DIR" -name "*ECBot*" -o -name "*ecbot*" 2>/dev/null | head -5)
    
    if [[ -z "$crash_files" ]]; then
        echo -e "${GREEN}✅ 未找到 ECBot 崩溃报告${NC}"
        return 0
    fi
    
    echo "$crash_files" | while read crash_file; do
        if [[ -f "$crash_file" ]]; then
            echo -e "\n${RED}📄 $(basename "$crash_file")${NC}"
            echo "  时间: $(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$crash_file")"
            echo "  大小: $(stat -f "%z bytes" "$crash_file")"
        fi
    done
    
    echo -e "\n${YELLOW}💡 查看详细崩溃报告:${NC}"
    echo "  open '$CRASH_LOG_DIR'"
}

# 搜索日志内容
search_logs() {
    local search_term="$1"
    local main_log=$(get_main_log)
    
    if [[ -z "$main_log" ]]; then
        echo -e "${RED}❌ 未找到主日志文件${NC}"
        return 1
    fi
    
    if [[ -z "$search_term" ]]; then
        echo -e "${RED}❌ 请提供搜索关键词${NC}"
        return 1
    fi
    
    echo -e "${CYAN}🔍 搜索: '$search_term'${NC}"
    echo "=================================================="
    
    grep -i -n -C3 "$search_term" "$main_log" | tail -50
}

# 主函数
main() {
    case "$1" in
        -h|--help)
            show_help
            ;;
        -l|--list)
            list_logs
            ;;
        -v|--view)
            view_main_log "$2"
            ;;
        -f|--follow)
            follow_log
            ;;
        -e|--errors)
            show_errors
            ;;
        -w|--warnings)
            show_warnings
            ;;
        -s|--startup)
            analyze_startup
            ;;
        -c|--crash)
            view_crash_logs
            ;;
        --search)
            search_logs "$2"
            ;;
        "")
            # 默认显示最后50行
            view_main_log 50
            ;;
        *)
            echo -e "${RED}❌ 未知选项: $1${NC}"
            echo "使用 $0 --help 查看帮助"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
