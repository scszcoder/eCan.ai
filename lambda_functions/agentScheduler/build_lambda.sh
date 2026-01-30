#!/bin/bash
# Build and deploy script for agentScheduler Lambda
# This Lambda handles agents, skills, tasks, tools, orgs, avatars, prompts, vehicles, etc.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAMBDA_NAME="agentScheduler"
ZIP_FILE="/tmp/${LAMBDA_NAME}.zip"
AWS_PROFILE="${AWS_PROFILE:-maipps8}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "========================================"
echo "Building ${LAMBDA_NAME} package"
echo "========================================"
echo "SCRIPT_DIR: $SCRIPT_DIR"

# Clean up old zip
log_info "Cleaning up old package..."
rm -f "$ZIP_FILE"

# Create new zip from the source directory
log_info "Creating deployment package..."
cd "$SCRIPT_DIR"

# Exclude non-essential files
zip -r "$ZIP_FILE" . \
    -x "*.zip" \
    -x "*.sh" \
    -x ".git/*" \
    -x "__pycache__/*" \
    -x "*.pyc" \
    -x ".DS_Store" \
    -x "node_modules/*" \
    -x "test.js" \
    -x "README*.md"

ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
log_success "Package created: $ZIP_FILE ($ZIP_SIZE)"

# Deploy option
if [ "$1" == "--deploy" ] || [ "$1" == "-d" ]; then
    log_info "Deploying to AWS Lambda..."
    aws lambda update-function-code \
        --function-name "$LAMBDA_NAME" \
        --region "$AWS_REGION" \
        --zip-file "fileb://$ZIP_FILE" \
        --profile "$AWS_PROFILE" \
        --no-cli-pager
    
    log_success "Lambda $LAMBDA_NAME deployed successfully!"
else
    echo ""
    echo "To deploy:"
    echo "  $0 --deploy"
    echo ""
    echo "Or manually:"
    echo "  aws lambda update-function-code --function-name $LAMBDA_NAME --region $AWS_REGION --zip-file fileb://$ZIP_FILE --profile $AWS_PROFILE"
fi
