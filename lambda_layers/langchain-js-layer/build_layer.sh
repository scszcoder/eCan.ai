#!/bin/bash
#
# build_layer.sh - Build and deploy langchain-js Lambda layer
#
# Usage:
#   ./build_layer.sh              # Build and deploy
#   ./build_layer.sh --build-only # Build zip only, don't deploy
#

set -e

LAYER_NAME="langchain-js-layer"
REGION="us-east-1"
AWS_PROFILE="maipps8"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/tmp/langchain-js-layer-build"
ZIP_FILE="/tmp/${LAYER_NAME}.zip"

echo "========================================"
echo " Building Lambda Layer: $LAYER_NAME"
echo "========================================"
echo "Script directory: $SCRIPT_DIR"
echo "Build directory: $BUILD_DIR"
echo "Region: $REGION"
echo "AWS Profile: $AWS_PROFILE"
echo ""

# Navigate to script directory
cd "$SCRIPT_DIR"

# Clean up previous build
echo "[1/5] Cleaning up previous build..."
rm -rf "$BUILD_DIR"
rm -f "$ZIP_FILE"

# Create layer structure (nodejs/node_modules for Lambda layer)
echo "[2/5] Creating layer directory structure..."
mkdir -p "$BUILD_DIR/nodejs"

# Copy package.json and install dependencies
echo "[3/5] Installing dependencies..."
cp package.json "$BUILD_DIR/nodejs/"
cd "$BUILD_DIR/nodejs"
npm install --production --no-optional

# Show installed packages
echo ""
echo "Installed packages:"
ls -la node_modules/ | head -20
echo ""

# Get the size of node_modules
NODE_MODULES_SIZE=$(du -sh node_modules | cut -f1)
echo "node_modules size: $NODE_MODULES_SIZE"

# Create deployment package
echo "[4/5] Creating deployment package..."
cd "$BUILD_DIR"
zip -r "$ZIP_FILE" nodejs/

ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo "Created $ZIP_FILE ($ZIP_SIZE)"

# Lambda layer has a 250MB unzipped limit, 50MB zipped limit for direct upload
# For larger packages, we need to upload to S3 first
UNZIPPED_SIZE=$(du -sm "$BUILD_DIR" | cut -f1)
echo "Unzipped size: ${UNZIPPED_SIZE}MB"

if [ "$UNZIPPED_SIZE" -gt 250 ]; then
    echo ""
    echo "WARNING: Unzipped size exceeds Lambda layer limit of 250MB!"
    echo "You may need to trim dependencies."
    exit 1
fi

# Check for --build-only flag
if [ "$1" == "--build-only" ]; then
    echo ""
    echo "Build complete. Skipping deployment (--build-only flag)."
    echo "Layer package: $ZIP_FILE"
    exit 0
fi

# Deploy to AWS Lambda
echo "[5/5] Deploying layer to AWS Lambda..."

# Check zip size - if > 50MB, upload to S3 first
ZIP_SIZE_MB=$(du -sm "$ZIP_FILE" | cut -f1)
if [ "$ZIP_SIZE_MB" -gt 50 ]; then
    echo "Zip file is ${ZIP_SIZE_MB}MB (>50MB), uploading to S3 first..."
    S3_BUCKET="ecan-skills"
    S3_KEY="lambda-layers/${LAYER_NAME}.zip"
    
    aws s3 cp "$ZIP_FILE" "s3://${S3_BUCKET}/${S3_KEY}" --profile "$AWS_PROFILE" --region "$REGION"
    
    LAYER_VERSION=$(aws lambda publish-layer-version \
        --layer-name "$LAYER_NAME" \
        --description "LangChain.js with OpenAI, Anthropic, Google GenAI, and other LLM providers" \
        --content S3Bucket="$S3_BUCKET",S3Key="$S3_KEY" \
        --compatible-runtimes nodejs18.x nodejs20.x nodejs22.x \
        --profile "$AWS_PROFILE" \
        --region "$REGION" \
        --query 'Version' \
        --output text)
else
    LAYER_VERSION=$(aws lambda publish-layer-version \
        --layer-name "$LAYER_NAME" \
        --description "LangChain.js with OpenAI, Anthropic, Google GenAI, and other LLM providers" \
        --zip-file "fileb://$ZIP_FILE" \
        --compatible-runtimes nodejs18.x nodejs20.x nodejs22.x \
        --profile "$AWS_PROFILE" \
        --region "$REGION" \
        --query 'Version' \
        --output text)
fi

LAYER_ARN="arn:aws:lambda:${REGION}:667118410653:layer:${LAYER_NAME}:${LAYER_VERSION}"

echo ""
echo "========================================"
echo " Layer Deployment Complete!"
echo "========================================"
echo ""
echo "Layer Name: $LAYER_NAME"
echo "Version: $LAYER_VERSION"
echo "ARN: $LAYER_ARN"
echo ""
echo "To add this layer to a Lambda function:"
echo ""
echo "  aws lambda update-function-configuration \\"
echo "    --function-name YOUR_FUNCTION_NAME \\"
echo "    --layers $LAYER_ARN \\"
echo "    --profile $AWS_PROFILE --region $REGION"
echo ""
echo "Or in code, import packages like:"
echo '  import { ChatOpenAI } from "@langchain/openai";'
echo '  import { ChatAnthropic } from "@langchain/anthropic";'
echo '  import { ChatGoogleGenerativeAI } from "@langchain/google-genai";'
