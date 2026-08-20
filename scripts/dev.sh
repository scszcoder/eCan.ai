#!/usr/bin/env bash
# ==============================================================================
# dev.sh - 统一管理前后端开发环境
#
# Usage:
#   ./scripts/dev.sh cn       # 切换到 CN (CloudBase, 腾讯云)
#   ./scripts/dev.sh intl     # 切换到 Intl (Cognito, AWS) [默认]
#   ./scripts/dev.sh status   # 查看当前配置和运行状态
#   ./scripts/dev.sh help     # 显示帮助
#
# 原理:
#   - 写入 ECAN_APP_ID 到项目根目录 .env (Python 后端读取)
#   - 提示对应的 npm run dev 命令 (Vite 加载 gui_v2/.env.{product})
#
# 注意:
#   - 需要手动重启后端才能生效
#   - 前端需要用对应的 npm run dev:{product} 启动
# ==============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUI_DIR="$PROJECT_ROOT/gui_v2"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/.env.example"

# ==============================================================================
# Helpers
# ==============================================================================

print_header() {
    echo -e "${BLUE}${BOLD}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           eCan.ai Development Environment Switcher          ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

info()    { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()      { echo -e "${GREEN}✓${NC}  $*"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $*"; }
error()   { echo -e "${RED}✗${NC}  $*" >&2; }

section() { echo -e "\n${CYAN}${BOLD}━━━ $* ━━━${NC}"; }

# 获取当前 ECAN_APP_ID
get_current_product() {
    if [ -f "$ENV_FILE" ]; then
        grep '^ECAN_APP_ID=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "intl"
    else
        echo "intl"
    fi
}

# ==============================================================================
# 子命令: help
# ==============================================================================
cmd_help() {
    print_header
    cat << EOF

${BOLD}USAGE${NC}
    ./scripts/dev.sh <command>

${BOLD}COMMANDS${NC}
    ${GREEN}cn${NC}       切换到 CN 版本 (CloudBase 认证, 腾讯云)
    ${GREEN}intl${NC}     切换到 Intl 版本 (Cognito 认证, AWS) [默认]
    ${GREEN}status${NC}   查看当前配置和运行状态
    ${GREEN}help${NC}     显示此帮助信息

${BOLD}WHAT IT DOES${NC}
    1. 设置 ECAN_APP_ID (cn 或 intl) 到项目根目录 .env
    2. Python 后端启动时读取 ECAN_APP_ID 选择认证方式
    3. 前端通过 npm run dev:cn 或 npm run dev:intl 选择配置

${BOLD}QUICK START${NC}
    # 首次使用
    cp .env.example .env
    ./scripts/dev.sh intl   # 或 cn

    # 启动开发
    python main.py                    # 终端 1: 后端
    cd gui_v2 && npm run dev:intl    # 终端 2: 前端 (或 dev:cn)

${BOLD}FILES${NC}
    ${YELLOW}.env${NC}           Python 后端配置 (gitignored)
    ${YELLOW}.env.example${NC}   配置模板
    ${YELLOW}gui_v2/.env${NC}        前端基础配置 (git tracked)
    ${YELLOW}gui_v2/.env.cn${NC}     CN 产品覆盖
    ${YELLOW}gui_v2/.env.intl${NC}   Intl 产品覆盖

EOF
}

# ==============================================================================
# 子命令: status
# ==============================================================================
cmd_status() {
    local current_product
    current_product=$(get_current_product)

    print_header

    # Section: 当前配置
    section "当前配置"
    echo -e "   Product:   ${BOLD}${GREEN}${current_product}${NC}"
    if [ "$current_product" = "cn" ]; then
        echo -e "   认证:      CloudBase (腾讯云)"
        echo -e "   区域:      ap-guangzhou"
        echo -e ""
        echo -e "   ${BOLD}启动命令:${NC}"
        echo -e "   ${CYAN}cd gui_v2 && npm run dev${NC}"
    else
        echo -e "   认证:      Cognito (AWS)"
        echo -e "   区域:      us-east-1"
        echo -e ""
        echo -e "   ${BOLD}启动命令:${NC}"
        echo -e "   ${CYAN}cd gui_v2 && npm run dev${NC}"
    fi

    # Section: .env 文件
    section "配置文件"
    echo -e "   项目根目录:"
    if [ -f "$ENV_FILE" ]; then
        local ws_url line_count
        ws_url=$(grep '^ECAN_WS_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 | head -c 50 || echo "未设置")
        local app_id
        app_id=$(grep '^ECAN_APP_ID=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "未设置")
        local log_level
        log_level=$(grep '^LOG_LEVEL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "INFO")
        echo -e "      .env          ${GREEN}存在${NC} (ECAN_APP_ID=${app_id}, LOG_LEVEL=${log_level})"
        echo -e "      ECAN_WS_URL:  ${ws_url}..."
    else
        echo -e "      .env          ${YELLOW}不存在${NC} - 请运行: ${CYAN}cp .env.example .env${NC}"
    fi

# 新架构：前端不再使用 .env.cn / .env.intl。运行时配置由后端提供：
#   - desktop dev: IPC handler getAppConfig (see gui/ipc/w2p_handlers/app_config_handler.py)
#   - web deploy: web_server.py 同源 GET /api/config
echo -e "   前端配置: ${GREEN}运行时由后端提供 (无需前端 .env.cn/.env.intl)${NC}"

    # Section: 运行状态
    section "运行状态"
    echo -e "   Python 后端:"
    if pgrep -f "python.*main\.py" > /dev/null 2>&1; then
        local pids
        pids=$(pgrep -f "python.*main\.py" | head -3 | tr '\n' ' ')
        echo -e "      进程:     ${GREEN}运行中${NC} (PIDs: $pids)"
        echo -e "      ${YELLOW}注意: 切换 product 后需要重启才能生效${NC}"
    else
        echo -e "      进程:     ${YELLOW}未运行${NC}"
    fi

    echo -e "   Vite 前端:"
    if pgrep -f "$GUI_DIR/node_modules/.bin/vite" > /dev/null 2>&1; then
        local pids
        pids=$(pgrep -f "$GUI_DIR/node_modules/.bin/vite" | head -3 | tr '\n' ' ')
        echo -e "      进程:     ${GREEN}运行中${NC} (PIDs: $pids)"
    else
        echo -e "      进程:     ${YELLOW}未运行${NC}"
    fi

    # Section: 下一步
    section "下一步"
    echo -e "   ${BOLD}启动开发环境:${NC}"
    echo -e ""
    if [ "$current_product" = "cn" ]; then
        echo -e "      ${CYAN}# 终端 1: 启动后端${NC}"
        echo -e "      cd $PROJECT_ROOT"
        echo -e "      python main.py"
        echo -e ""
        echo -e "      ${CYAN}# 终端 2: 启动前端（前后端通过 IPC handler getAppConfig 自动同步 ECAN_APP_ID）${NC}"
        echo -e "      cd $GUI_DIR"
        echo -e "      npm run dev"
    else
        echo -e "      ${CYAN}# 终端 1: 启动后端${NC}"
        echo -e "      cd $PROJECT_ROOT"
        echo -e "      python main.py"
        echo -e ""
        echo -e "      ${CYAN}# 终端 2: 启动前端（前后端通过 IPC handler getAppConfig 自动同步 ECAN_APP_ID）${NC}"
        echo -e "      cd $GUI_DIR"
        echo -e "      npm run dev"
    fi

    echo ""
}

# ==============================================================================
# 子命令: switch
# ==============================================================================
cmd_switch() {
    local target="$1"

    # 校验
    if [ "$target" != "cn" ] && [ "$target" != "intl" ]; then
        error "无效的产品: $target (必须是 'cn' 或 'intl')"
        exit 1
    fi

    # 检查 .env.example 是否存在
    if [ ! -f "$ENV_EXAMPLE" ]; then
        error ".env.example 不存在，请先创建: cp .env.example .env"
        exit 1
    fi

    # 检查/创建后端 .env
    if [ ! -f "$ENV_FILE" ]; then
        info "创建后端 .env 文件..."
        cp "$ENV_EXAMPLE" "$ENV_FILE"
    fi

    # 更新后端 ECAN_APP_ID
    if grep -q "^ECAN_APP_ID=" "$ENV_FILE"; then
        sed -i '' "s/^ECAN_APP_ID=.*/ECAN_APP_ID=${target}/" "$ENV_FILE"
    else
        echo "" >> "$ENV_FILE"
        echo "# Set by dev.sh - $(date)" >> "$ENV_FILE"
        echo "ECAN_APP_ID=${target}" >> "$ENV_FILE"
    fi

# ========================================
# 新架构：前端不再读 VITE_APP_ID/VITE_IS_CN
# 运行时配置由后端提供：
#   - desktop dev: IPC handler getAppConfig
#   - web deploy: web_server.py 同源 GET /api/config
# ========================================

    print_header
    echo -e "   ${BOLD}切换完成${NC}"
    echo -e ""
    echo -e "   ${GREEN}ECAN_APP_ID = $target${NC} (后端)"

    if [ "$target" = "cn" ]; then
        echo -e ""
        echo -e "   认证:      ${GREEN}CloudBase (腾讯云)${NC}"
        echo -e "   区域:      ${GREEN}ap-guangzhou${NC}"
    else
        echo -e ""
        echo -e "   认证:      ${GREEN}Cognito (AWS)${NC}"
        echo -e "   区域:      ${GREEN}us-east-1${NC}"
    fi

    echo ""
    echo -e "   ${YELLOW}⚠  需要手动重启后端才能生效${NC}"
    echo ""

    ok "切换成功! 请使用 'npm run dev' 启动前端（前后端自动通过 IPC handler getAppConfig 同步 ECAN_APP_ID）"
}

# ==============================================================================
# 主入口
# ==============================================================================
main() {
    local command="${1:-status}"

    case "$command" in
        cn|intl)
            cmd_switch "$command"
            ;;
        status)
            cmd_status
            ;;
        -h|--help|help)
            cmd_help
            ;;
        *)
            error "未知命令: $command"
            echo "运行 './scripts/dev.sh help' 查看帮助"
            exit 1
            ;;
    esac
}

main "$@"
