#!/bin/bash
# ============================================================================
# Linux 构建验证脚本
# ============================================================================
# 用途：在 Linux 系统上验证构建流程是否正确
# 使用方法：
#   chmod +x verify_linux_build.sh
#   ./verify_linux_build.sh [--quick]
# ============================================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查是否为快速模式
QUICK_MODE=false
if [[ "$1" == "--quick" ]]; then
    QUICK_MODE=true
    echo -e "${YELLOW}⚡ 快速验证模式（跳过完整构建）${NC}"
fi

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Linux 构建环境验证脚本                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# 1. 系统环境检查
# ============================================================================
echo -e "${BLUE}[1/6] 检查系统环境...${NC}"

# 检查操作系统
if [[ "$(uname -s)" != "Linux" ]]; then
    echo -e "${RED}❌ 错误：此脚本只能在 Linux 系统上运行${NC}"
    echo -e "   当前系统：$(uname -s)"
    exit 1
fi
echo -e "${GREEN}✅ 操作系统：Linux ($(uname -r))${NC}"

# 检查发行版
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo -e "${GREEN}✅ 发行版：$NAME $VERSION${NC}"
else
    echo -e "${YELLOW}⚠️  无法检测发行版信息${NC}"
fi

# 检查架构
ARCH=$(uname -m)
echo -e "${GREEN}✅ 架构：$ARCH${NC}"

if [[ "$ARCH" != "x86_64" ]]; then
    echo -e "${YELLOW}⚠️  警告：当前架构为 $ARCH，推荐使用 x86_64${NC}"
fi

echo ""

# ============================================================================
# 2. Python 环境检查
# ============================================================================
echo -e "${BLUE}[2/6] 检查 Python 环境...${NC}"

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 错误：未找到 python3${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✅ Python 版本：$PYTHON_VERSION${NC}"

# 检查 Python 版本是否 >= 3.8
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 8 ]]; then
    echo -e "${RED}❌ 错误：需要 Python 3.8 或更高版本${NC}"
    exit 1
fi

# 检查 pip
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ 错误：未找到 pip3${NC}"
    exit 1
fi
echo -e "${GREEN}✅ pip3 已安装${NC}"

echo ""

# ============================================================================
# 3. 构建工具检查
# ============================================================================
echo -e "${BLUE}[3/6] 检查构建工具...${NC}"

# 检查 PyInstaller
if python3 -c "import PyInstaller" 2>/dev/null; then
    PYINSTALLER_VERSION=$(python3 -c "import PyInstaller; print(PyInstaller.__version__)")
    echo -e "${GREEN}✅ PyInstaller：$PYINSTALLER_VERSION${NC}"
else
    echo -e "${RED}❌ PyInstaller 未安装${NC}"
    echo -e "   安装命令：pip3 install pyinstaller"
    exit 1
fi

# 检查 appimagetool
if command -v appimagetool &> /dev/null; then
    echo -e "${GREEN}✅ appimagetool 已安装${NC}"
else
    echo -e "${YELLOW}⚠️  appimagetool 未安装（AppImage 构建将失败）${NC}"
    echo -e "   安装方法："
    echo -e "   wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    echo -e "   chmod +x appimagetool-x86_64.AppImage"
    echo -e "   sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool"
fi

# 检查 dpkg-deb
if command -v dpkg-deb &> /dev/null; then
    echo -e "${GREEN}✅ dpkg-deb 已安装${NC}"
else
    echo -e "${YELLOW}⚠️  dpkg-deb 未安装（DEB 构建将失败）${NC}"
    echo -e "   安装命令：sudo apt-get install dpkg"
fi

# 检查 patchelf（cv2 OpenSSL 冲突修复必需）
if command -v patchelf &> /dev/null; then
    PATCHELF_VERSION=$(patchelf --version 2>&1 | head -1)
    echo -e "${GREEN}✅ patchelf：$PATCHELF_VERSION${NC}"
else
    echo -e "${RED}❌ patchelf 未安装（cv2 SSL 修复将跳过，可能导致 SSL 启动失败）${NC}"
    echo -e "   安装命令：sudo apt-get install patchelf"
fi

echo ""

# ============================================================================
# 4. 系统依赖检查
# ============================================================================
echo -e "${BLUE}[4/6] 检查系统依赖...${NC}"

# Qt/PySide6 依赖
MISSING_DEPS=()

check_lib() {
    if ldconfig -p | grep -q "$1"; then
        echo -e "${GREEN}✅ $1${NC}"
    else
        echo -e "${RED}❌ $1 缺失${NC}"
        MISSING_DEPS+=("$1")
    fi
}

echo "Qt/PySide6 依赖："
check_lib "libxcb"
check_lib "libxkbcommon"
check_lib "libdbus-1"

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠️  缺少 ${#MISSING_DEPS[@]} 个依赖库${NC}"
    echo -e "   安装命令（Ubuntu/Debian）："
    echo -e "   sudo apt-get install libxcb1 libxkbcommon0 libdbus-1-3"
fi

echo ""

# ============================================================================
# 5. 项目结构检查
# ============================================================================
echo -e "${BLUE}[5/6] 检查项目结构...${NC}"

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# 检查关键文件
check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✅ $1${NC}"
    else
        echo -e "${RED}❌ $1 缺失${NC}"
        return 1
    fi
}

check_file "main.py"
check_file "build.py"
check_file "build_system/linux_builder.py"
check_file "build_system/unified_build.py"
check_file "build_system/build_config.json"

echo ""

# ============================================================================
# 6. 构建测试
# ============================================================================
echo -e "${BLUE}[6/6] 构建测试...${NC}"

if [ "$QUICK_MODE" = true ]; then
    echo -e "${YELLOW}⚡ 跳过完整构建（快速模式）${NC}"
    echo -e "${GREEN}✅ 快速验证完成${NC}"
else
    echo -e "${YELLOW}开始测试构建（这可能需要几分钟）...${NC}"
    echo ""
    
    # 清理旧的构建产物
    if [ -d "dist" ]; then
        echo "清理旧的 dist/ 目录..."
        rm -rf dist
    fi
    
    if [ -d "build" ]; then
        echo "清理旧的 build/ 目录..."
        rm -rf build
    fi
    
    # 运行构建
    echo "执行构建命令：python3 build.py prod"
    echo ""
    
    if python3 build.py prod 2>&1 | tee build_verify.log; then
        echo ""
        echo -e "${GREEN}✅ 构建成功！${NC}"
        
        # 检查构建产物
        echo ""
        echo -e "${BLUE}检查构建产物：${NC}"
        
        if [ -f "dist/eCan/eCan" ]; then
            SIZE=$(du -h "dist/eCan/eCan" | cut -f1)
            echo -e "${GREEN}✅ PyInstaller 可执行文件：dist/eCan/eCan ($SIZE)${NC}"
        else
            echo -e "${RED}❌ PyInstaller 可执行文件未找到${NC}"
        fi
        
        # 查找 AppImage
        APPIMAGE=$(find dist -name "*.AppImage" -type f | head -n 1)
        if [ -n "$APPIMAGE" ]; then
            SIZE=$(du -h "$APPIMAGE" | cut -f1)
            echo -e "${GREEN}✅ AppImage：$APPIMAGE ($SIZE)${NC}"
        else
            echo -e "${YELLOW}⚠️  AppImage 未找到${NC}"
        fi
        
        # 查找 DEB 包
        DEB=$(find dist -name "*.deb" -type f | head -n 1)
        if [ -n "$DEB" ]; then
            SIZE=$(du -h "$DEB" | cut -f1)
            echo -e "${GREEN}✅ DEB 包：$DEB ($SIZE)${NC}"
        else
            echo -e "${YELLOW}⚠️  DEB 包未找到${NC}"
        fi
        
    else
        echo ""
        echo -e "${RED}❌ 构建失败${NC}"
        echo -e "   查看日志：build_verify.log"
        exit 1
    fi
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   验证完成                                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# 总结
# ============================================================================
echo -e "${GREEN}✅ Linux 构建环境验证通过！${NC}"
echo ""
echo "下一步："
echo "  1. 本地测试：python3 build.py prod"
echo "  2. GitHub Actions：推送到仓库触发自动构建"
echo "  3. 手动触发：在 GitHub Actions 页面选择 'Linux' 平台"
echo ""
