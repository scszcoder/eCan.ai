#!/bin/bash

# ECBot Windows 构建脚本 (使用 cibuilds/windows2019)
# 专门用于Windows exe打包，与build.py跨平台构建兼容

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 检查Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker 未运行"
        exit 1
    fi
}

# 检查Windows容器支持
check_windows_support() {
    print_info "检查Windows容器支持..."
    
    # 检查是否支持Windows容器
    if ! docker version --format '{{.Server.Os}}' | grep -q "windows"; then
        print_warning "当前Docker可能不支持Windows容器"
        print_info "请确保Docker Desktop配置为Windows容器模式"
    fi
}

# 构建镜像
build_image() {
    print_info "构建 cibuilds/windows2019 镜像..."
    
    # 使用专门的Windows Dockerfile
    docker build -f build_system/Dockerfile.windows -t ecbot-windows-cibuilds .
}

# 运行构建
run_build() {
    local build_args="$@"
    
    print_info "启动Windows构建容器..."
    
    # 创建必要的目录
    mkdir -p dist build
    
    # 运行构建，传递所有参数给 build.py
    docker run --rm \
        -v "$(pwd):/app" \
        -v "$(pwd)/dist:/app/dist" \
        -v "$(pwd)/build:/app/build" \
        ecbot-windows-cibuilds \
        python build.py $build_args
}

# 清理容器
cleanup() {
    print_info "清理 Docker 容器..."
    docker rmi ecbot-windows-cibuilds 2>/dev/null || true
}

# 显示帮助信息
show_help() {
    echo "🚀 ECBot Windows 构建脚本 (cibuilds/windows2019)"
    echo ""
    echo "用法: $0 [build.py 参数]"
    echo ""
    echo "示例:"
    echo "  $0 prod                    # 生产模式构建 Windows exe"
    echo "  $0 dev                     # 开发模式构建 Windows exe"
    echo "  $0 prod --force            # 强制生产模式构建"
    echo "  $0 --clean                 # 清理 Docker 资源"
    echo "  $0 --rebuild               # 重新构建镜像"
    echo ""
    echo "注意: 所有参数都会传递给 build.py"
    echo "      使用 cibuilds/windows2019 镜像进行Windows打包"
}

# 主函数
main() {
    local rebuild=false
    local clean=false
    local build_args=()
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help)
                show_help
                exit 0
                ;;
            --clean)
                clean=true
                shift
                ;;
            --rebuild)
                rebuild=true
                shift
                ;;
            *)
                build_args+=("$1")
                shift
                ;;
        esac
    done
    
    # 检查依赖
    check_docker
    check_windows_support
    
    # 清理模式
    if [ "$clean" = true ]; then
        cleanup
        print_success "清理完成"
        exit 0
    fi
    
    # 重新构建模式
    if [ "$rebuild" = true ]; then
        print_info "重新构建 Docker 镜像..."
        docker build --no-cache -f build_system/Dockerfile.windows -t ecbot-windows-cibuilds .
    else
        # 构建镜像（如果不存在）
        build_image
    fi
    
    # 运行构建
    run_build "${build_args[@]}"
    
    # 检查构建结果
    if [ -f "dist/ECBot.exe" ]; then
        print_success "Windows exe 构建成功!"
        print_info "输出文件: dist/ECBot.exe"
        ls -la dist/
    else
        print_warning "未找到输出文件，请检查构建日志"
    fi
    
    # 清理
    cleanup
    
    print_success "构建完成!"
}

# 运行主函数
main "$@" 