#!/bin/bash
# 本地测试 S3 上传脚本
# 模拟 GitHub Actions 的上传流程

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== S3 上传测试脚本 ===${NC}"
echo ""

# 检查 AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}错误: 未安装 AWS CLI${NC}"
    echo "请先安装: brew install awscli"
    exit 1
fi

# 检查 AWS 凭证
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}错误: AWS 凭证未配置或无效${NC}"
    echo "请运行: aws configure"
    exit 1
fi

echo -e "${GREEN}✓ AWS CLI 已安装${NC}"
echo -e "${GREEN}✓ AWS 凭证有效${NC}"
echo ""

# 配置变量（从环境变量或使用默认值）
VERSION="${VERSION:-0.0.1-test}"
S3_BUCKET="${S3_BUCKET:-ecan-releases}"
S3_BASE_PATH="${S3_BASE_PATH:-releases}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "配置信息："
echo "  版本: $VERSION"
echo "  S3 存储桶: $S3_BUCKET"
echo "  S3 路径: $S3_BASE_PATH"
echo "  AWS 区域: $AWS_REGION"
echo ""

# 检查存储桶是否存在
echo -e "${YELLOW}检查 S3 存储桶...${NC}"
if aws s3 ls "s3://${S3_BUCKET}" 2>&1 | grep -q 'NoSuchBucket'; then
    echo -e "${RED}错误: 存储桶 ${S3_BUCKET} 不存在${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 存储桶存在${NC}"
echo ""

# 创建测试文件
echo -e "${YELLOW}创建测试文件...${NC}"
TEST_DIR="test_upload_$(date +%s)"
mkdir -p "$TEST_DIR/windows"
mkdir -p "$TEST_DIR/macos"
mkdir -p "$TEST_DIR/checksums"

# 创建模拟的安装包文件
echo "This is a test Windows installer" > "$TEST_DIR/windows/eCan-${VERSION}-windows-amd64-Setup.exe"
echo "This is a test Windows portable" > "$TEST_DIR/windows/eCan-${VERSION}-windows-amd64.exe"
echo "This is a test macOS Intel installer" > "$TEST_DIR/macos/eCan-${VERSION}-macos-amd64.pkg"
echo "This is a test macOS ARM installer" > "$TEST_DIR/macos/eCan-${VERSION}-macos-aarch64.pkg"

# 生成校验和
echo -e "${YELLOW}生成 SHA256 校验和...${NC}"
cd "$TEST_DIR"
find . -type f \( -name "*.exe" -o -name "*.pkg" \) -exec sha256sum {} \; > checksums/SHA256SUMS
cat checksums/SHA256SUMS
cd ..
echo ""

# 上传到 S3
S3_VERSION_PATH="${S3_BASE_PATH}/v${VERSION}"
echo -e "${YELLOW}上传文件到 S3...${NC}"
echo "目标路径: s3://${S3_BUCKET}/${S3_VERSION_PATH}/"
echo ""

aws s3 sync "$TEST_DIR/" "s3://${S3_BUCKET}/${S3_VERSION_PATH}/" \
  --acl public-read \
  --cache-control "max-age=31536000" \
  --metadata "version=${VERSION}" \
  --exclude "*" \
  --include "windows/*" \
  --include "macos/*" \
  --include "checksums/*"

echo ""
echo -e "${GREEN}✓ 上传完成${NC}"
echo ""

# 生成版本元数据
echo -e "${YELLOW}创建版本元数据...${NC}"
cat > version-metadata.json <<EOF
{
  "version": "${VERSION}",
  "release_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "tag": "v${VERSION}",
  "test": true,
  "s3_base_url": "https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}",
  "files": {
    "windows": [
      {
        "name": "eCan-${VERSION}-windows-amd64-Setup.exe",
        "url": "https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/windows/eCan-${VERSION}-windows-amd64-Setup.exe"
      },
      {
        "name": "eCan-${VERSION}-windows-amd64.exe",
        "url": "https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/windows/eCan-${VERSION}-windows-amd64.exe"
      }
    ],
    "macos": [
      {
        "name": "eCan-${VERSION}-macos-amd64.pkg",
        "url": "https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/macos/eCan-${VERSION}-macos-amd64.pkg"
      },
      {
        "name": "eCan-${VERSION}-macos-aarch64.pkg",
        "url": "https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/macos/eCan-${VERSION}-macos-aarch64.pkg"
      }
    ]
  }
}
EOF

# 上传元数据
aws s3 cp version-metadata.json "s3://${S3_BUCKET}/${S3_VERSION_PATH}/version-metadata.json" \
  --acl public-read \
  --content-type "application/json"

echo -e "${GREEN}✓ 元数据已上传${NC}"
echo ""

# 验证上传
echo -e "${YELLOW}验证上传的文件...${NC}"
echo ""
echo "S3 文件列表："
aws s3 ls "s3://${S3_BUCKET}/${S3_VERSION_PATH}/" --recursive

echo ""
echo -e "${GREEN}=== 测试完成 ===${NC}"
echo ""
echo "下载 URL："
echo "  Windows 安装包: https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/windows/eCan-${VERSION}-windows-amd64-Setup.exe"
echo "  macOS Intel 安装包: https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/macos/eCan-${VERSION}-macos-amd64.pkg"
echo "  macOS ARM 安装包: https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/macos/eCan-${VERSION}-macos-aarch64.pkg"
echo "  校验和: https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/checksums/SHA256SUMS"
echo "  元数据: https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/version-metadata.json"
echo ""

# 测试下载
echo -e "${YELLOW}测试下载...${NC}"
TEST_URL="https://${S3_BUCKET}.s3.${AWS_REGION}.amazonaws.com/${S3_VERSION_PATH}/checksums/SHA256SUMS"
if curl -f -s "$TEST_URL" > /dev/null; then
    echo -e "${GREEN}✓ 文件可以公开访问${NC}"
    echo ""
    echo "校验和内容："
    curl -s "$TEST_URL"
else
    echo -e "${RED}✗ 文件无法访问，请检查存储桶策略${NC}"
fi

echo ""
echo -e "${YELLOW}清理本地测试文件...${NC}"
rm -rf "$TEST_DIR" version-metadata.json
echo -e "${GREEN}✓ 本地文件已清理${NC}"
echo ""

echo -e "${YELLOW}要删除 S3 上的测试文件吗? (y/N)${NC}"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo -e "${YELLOW}删除 S3 测试文件...${NC}"
    aws s3 rm "s3://${S3_BUCKET}/${S3_VERSION_PATH}/" --recursive
    echo -e "${GREEN}✓ S3 测试文件已删除${NC}"
else
    echo "保留 S3 测试文件"
    echo "手动删除命令: aws s3 rm s3://${S3_BUCKET}/${S3_VERSION_PATH}/ --recursive"
fi

echo ""
echo -e "${GREEN}测试完成！${NC}"
