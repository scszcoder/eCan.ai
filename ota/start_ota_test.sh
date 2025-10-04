#!/bin/bash
# eCan.ai OTA 本地测试快速启动脚本

# 设置颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录（脚本在 ota 目录下，需要返回上一级）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  eCan.ai OTA 本地测试环境启动器${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 未安装${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python3: $(python3 --version)${NC}"

# 检查依赖
echo ""
echo -e "${YELLOW}检查依赖...${NC}"

check_package() {
    python3 -c "import $1" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $1 已安装${NC}"
        return 0
    else
        echo -e "${RED}❌ $1 未安装${NC}"
        return 1
    fi
}

missing_deps=0
for pkg in flask requests cryptography; do
    if ! check_package $pkg; then
        missing_deps=1
    fi
done

if [ $missing_deps -eq 1 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  缺少依赖，是否安装? (y/n)${NC}"
    read -r answer
    if [ "$answer" = "y" ]; then
        pip3 install flask requests cryptography
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ 依赖安装失败${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌ 无法继续，缺少必要的依赖${NC}"
        exit 1
    fi
fi

# 显示菜单
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}请选择操作:${NC}"
echo ""
echo -e "  ${GREEN}1${NC}. 启动本地 OTA 服务器"
echo -e "  ${GREEN}2${NC}. 运行 OTA 功能测试"
echo -e "  ${GREEN}3${NC}. 同时启动服务器和测试 (推荐)"
echo -e "  ${GREEN}4${NC}. 运行单元测试"
echo -e "  ${GREEN}5${NC}. 查看 OTA 文档"
echo -e "  ${GREEN}0${NC}. 退出"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -n "请输入选项 [0-5]: "
read -r choice

case $choice in
    1)
        echo ""
        echo -e "${GREEN}🚀 启动本地 OTA 服务器...${NC}"
        echo -e "${YELLOW}提示: 按 Ctrl+C 停止服务器${NC}"
        echo ""
        cd "$PROJECT_ROOT/ota/server"
        python3 update_server.py
        ;;
    
    2)
        echo ""
        echo -e "${GREEN}🧪 运行 OTA 功能测试...${NC}"
        echo ""
        export ECBOT_DEV_MODE=1
        cd "$PROJECT_ROOT"
        python3 ota/test_local_ota.py
        ;;
    
    3)
        echo ""
        echo -e "${GREEN}🚀 同时启动服务器和测试${NC}"
        echo ""
        
        # 启动服务器（后台）
        echo -e "${YELLOW}1. 启动本地 OTA 服务器（后台）...${NC}"
        cd "$PROJECT_ROOT/ota/server"
        python3 update_server.py > /tmp/ota_server.log 2>&1 &
        SERVER_PID=$!
        echo -e "${GREEN}✅ 服务器已启动 (PID: $SERVER_PID)${NC}"
        
        # 等待服务器启动
        echo -e "${YELLOW}2. 等待服务器就绪...${NC}"
        sleep 3
        
        # 检查服务器是否运行
        if curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ 服务器就绪${NC}"
        else
            echo -e "${YELLOW}⚠️  服务器可能未完全启动，但继续测试...${NC}"
        fi
        
        # 运行测试
        echo ""
        echo -e "${YELLOW}3. 运行功能测试...${NC}"
        echo ""
        export ECBOT_DEV_MODE=1
        cd "$PROJECT_ROOT"
        python3 ota/test_local_ota.py
        
        # 询问是否停止服务器
        echo ""
        echo -e "${YELLOW}是否停止服务器? (y/n)${NC}"
        read -r stop_server
        if [ "$stop_server" = "y" ]; then
            kill $SERVER_PID 2>/dev/null
            echo -e "${GREEN}✅ 服务器已停止${NC}"
        else
            echo -e "${YELLOW}ℹ️  服务器仍在运行 (PID: $SERVER_PID)${NC}"
            echo -e "${YELLOW}   手动停止: kill $SERVER_PID${NC}"
            echo -e "${YELLOW}   查看日志: tail -f /tmp/ota_server.log${NC}"
        fi
        ;;
    
    4)
        echo ""
        echo -e "${GREEN}🧪 运行单元测试...${NC}"
        echo ""
        cd "$PROJECT_ROOT"
        
        echo -e "${YELLOW}运行 test_ota_core.py...${NC}"
        python3 -m unittest tests.test_ota_core
        
        echo ""
        echo -e "${YELLOW}运行 test_ota_more.py...${NC}"
        python3 -m unittest tests.test_ota_more
        ;;
    
    5)
        echo ""
        echo -e "${GREEN}📚 查看 OTA 文档...${NC}"
        echo ""
        
        doc_file="$PROJECT_ROOT/ota/LOCAL_TEST_GUIDE.md"
        if [ -f "$doc_file" ]; then
            if command -v less &> /dev/null; then
                less "$doc_file"
            else
                cat "$doc_file"
            fi
        else
            echo -e "${RED}❌ 文档文件不存在: $doc_file${NC}"
        fi
        ;;
    
    0)
        echo ""
        echo -e "${GREEN}👋 再见!${NC}"
        exit 0
        ;;
    
    *)
        echo ""
        echo -e "${RED}❌ 无效的选项${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ 操作完成${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
