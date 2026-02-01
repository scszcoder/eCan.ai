#!/bin/bash
#
# build_lambda.sh - Build and deploy chatter Lambda
#
# Usage:
#   ./build_lambda.sh          # Build and deploy
#   ./build_lambda.sh --build-only  # Build zip only, don't deploy
#

set -e

LAMBDA_NAME="chatter"
REGION="us-east-1"
AWS_PROFILE="maipps8"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo " Building $LAMBDA_NAME Lambda"
echo "========================================"
echo "Script directory: $SCRIPT_DIR"
echo "Region: $REGION"
echo "AWS Profile: $AWS_PROFILE"
echo ""

# Navigate to script directory
cd "$SCRIPT_DIR"

# Clean up previous build
echo "[1/4] Cleaning up previous build..."
rm -f lambda.zip
rm -rf node_modules

# Install dependencies (if package.json exists)
if [ -f "package.json" ]; then
  echo "[2/4] Installing dependencies..."
  npm install --production
else
  echo "[2/4] No package.json, skipping npm install..."
fi

# Create deployment package
echo "[3/4] Creating deployment package..."
if [ -d "node_modules" ]; then
  zip -r lambda.zip index.mjs node_modules/
else
  zip lambda.zip index.mjs
fi

echo "Created lambda.zip ($(du -h lambda.zip | cut -f1))"

# Check for --build-only flag
if [ "$1" == "--build-only" ]; then
  echo ""
  echo "Build complete. Skipping deployment (--build-only flag)."
  exit 0
fi

# Deploy to AWS Lambda
echo "[4/4] Deploying to AWS Lambda..."
aws lambda update-function-code \
  --function-name "$LAMBDA_NAME" \
  --zip-file fileb://lambda.zip \
  --region "$REGION" \
  --profile "$AWS_PROFILE"

echo ""
echo "========================================"
echo " Deployment Complete!"
echo "========================================"
echo ""
echo "To test the lambda, you can invoke it with:"
echo ""
echo '  aws lambda invoke --function-name chatter \'
echo "    --profile $AWS_PROFILE --region $REGION \\"
echo '    --payload '"'"'{"test":"hello"}'"'"' \'
echo '    --cli-binary-format raw-in-base64-out \'
echo '    response.json && cat response.json'
echo ""
echo "View logs in CloudWatch:"
echo "  https://console.aws.amazon.com/cloudwatch/home?region=$REGION#logsV2:log-groups/log-group/%2Faws%2Flambda%2F$LAMBDA_NAME"
