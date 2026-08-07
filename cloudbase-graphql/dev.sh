#!/bin/bash
# ============================================================
# eCan.ai 本地开发启动脚本
# ============================================================
# 使用方式：
#   ./dev.sh                    # 启动本地服务器
#   ./dev.sh init               # 初始化数据库
#   ./dev.sh test               # 运行测试

set -e

# 项目目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  eCan.ai 本地开发${NC}"
echo -e "${BLUE}========================================${NC}\n"

# 加载环境变量
if [ -f ".env.local" ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
fi

# 处理命令参数
COMMAND="${1:-start}"

case "$COMMAND" in
    start)
        echo -e "${YELLOW}🚀 启动本地开发服务器...${NC}\n"
        
        # 检查环境变量
        if [ -z "$DATABASE_URL" ]; then
            echo -e "${RED}❌ 错误: DATABASE_URL 未配置${NC}"
            echo -e "   请复制 .env.local.example 为 .env.local 并配置"
            exit 1
        fi
        
        # 安装依赖
        if [ ! -d "node_modules" ]; then
            echo -e "${YELLOW}📦 安装依赖...${NC}"
            npm install
        fi
        
        # 生成 Prisma Client
        echo -e "${YELLOW}🔧 生成 Prisma Client...${NC}"
        npx prisma generate
        
        echo ""
        echo -e "${GREEN}✅ 准备就绪！${NC}"
        echo -e "   启动服务器: ${BLUE}node index.js${NC}"
        echo -e "   API 地址:   ${BLUE}http://localhost:${LOCAL_PORT:-3000}/api/graphql${NC}"
        echo -e "   Playground:  ${BLUE}http://localhost:${LOCAL_PORT:-3000}/api/graphql${NC}"
        echo ""
        
        # 启动服务器
        PORT="${LOCAL_PORT:-3000}" node index.js
        ;;
        
    init)
        echo -e "${YELLOW}🗄️  初始化数据库...${NC}\n"
        
        # 检查环境变量
        if [ -z "$DATABASE_URL" ]; then
            echo -e "${RED}❌ 错误: DATABASE_URL 未配置${NC}"
            echo -e "   请复制 .env.local.example 为 .env.local 并配置"
            exit 1
        fi
        
        # 安装依赖
        if [ ! -d "node_modules" ]; then
            echo -e "${YELLOW}📦 安装依赖...${NC}"
            npm install
        fi
        
        # 生成 Prisma Client
        echo -e "${YELLOW}🔧 生成 Prisma Client...${NC}"
        npx prisma generate
        
        # 推送 Schema 到数据库
        echo -e "${YELLOW}📤 推送 Schema 到数据库...${NC}"
        npx prisma db push
        
        # 运行初始化脚本
        echo -e "${YELLOW}📝 运行初始化脚本...${NC}"
        node prisma/init.js
        
        echo ""
        echo -e "${GREEN}✅ 数据库初始化完成！${NC}"
        ;;
        
    seed)
        echo -e "${YELLOW}🌱 运行数据库种子脚本...${NC}\n"
        node prisma/init.js
        ;;
        
    studio)
        echo -e "${YELLOW}🗄️  启动 Prisma Studio...${NC}\n"
        
        if [ -z "$PG_HOST" ]; then
            echo -e "${RED}❌ 错误: PG_HOST 未配置${NC}"
            exit 1
        fi
        
        npx prisma studio
        ;;
        
    generate)
        echo -e "${YELLOW}🔧 生成 Prisma Client...${NC}\n"
        npx prisma generate
        ;;
        
    db:push)
        echo -e "${YELLOW}📤 推送 Schema 到数据库...${NC}\n"
        npx prisma db push
        ;;
        
    migrate)
        echo -e "${YELLOW}🔄 运行数据库迁移...${NC}\n"
        npx prisma migrate dev
        ;;
        
    test)
        echo -e "${YELLOW}🧪 运行测试...${NC}\n"
        ./test-api.sh
        ;;
        
    deploy)
        echo -e "${YELLOW}☁️  部署到 TCB...${NC}\n"
        ./deploy.sh
        ;;
        
    help)
        echo -e "${GREEN}可用命令：${NC}"
        echo ""
        echo -e "  ${BLUE}./dev.sh start${NC}      启动本地开发服务器"
        echo -e "  ${BLUE}./dev.sh init${NC}       初始化数据库（创建表 + 种子数据）"
        echo -e "  ${BLUE}./dev.sh seed${NC}        运行种子脚本"
        echo -e "  ${BLUE}./dev.sh studio${NC}      启动 Prisma Studio（数据库可视化）"
        echo -e "  ${BLUE}./dev.sh generate${NC}     生成 Prisma Client"
        echo -e "  ${BLUE}./dev.sh db:push${NC}      推送 Schema 到数据库"
        echo -e "  ${BLUE}./dev.sh migrate${NC}      运行数据库迁移"
        echo -e "  ${BLUE}./dev.sh test${NC}         测试 API"
        echo -e "  ${BLUE}./dev.sh deploy${NC}       部署到 TCB"
        echo ""
        ;;
        
    *)
        echo -e "${RED}❌ 未知命令: $COMMAND${NC}"
        echo -e "   运行 ${BLUE}./dev.sh help${NC} 查看帮助"
        exit 1
        ;;
esac
