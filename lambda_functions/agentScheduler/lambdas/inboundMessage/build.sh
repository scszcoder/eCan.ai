#!/bin/bash
# Build and deploy script for the inboundMessage Lambda.
#
# This Lambda receives SNS notifications for inbound SMS (AWS End User Messaging
# SMS two-way) and inbound email (SES Receipt Rule) and publishes a
# publishIncomingMessage GraphQL mutation against AppSync.
#
# Dependencies: only AWS SDK v3 modules already provided by the Node 20 Lambda
# runtime (@aws-sdk/client-dynamodb, @aws-sdk/client-s3). No npm install needed.
#
# Usage:
#   ./build.sh              # build only
#   ./build.sh --deploy     # build + deploy via aws lambda update-function-code
#   ./build.sh --create     # build + create the function for the first time
#
# Env overrides:
#   LAMBDA_NAME, AWS_PROFILE, AWS_REGION, ROLE_ARN,
#   APPSYNC_API_URL, APPSYNC_API_KEY,
#   MESSAGING_ROUTING_TABLE, INBOUND_EMAIL_S3_BUCKET

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAMBDA_NAME="${LAMBDA_NAME:-inboundMessage}"
ZIP_FILE="/tmp/${LAMBDA_NAME}.zip"
AWS_PROFILE="${AWS_PROFILE:-maipps8}"
AWS_REGION="${AWS_REGION:-us-east-1}"
RUNTIME="${RUNTIME:-nodejs20.x}"
HANDLER="${HANDLER:-index.handler}"
TIMEOUT="${TIMEOUT:-30}"
MEMORY="${MEMORY:-256}"
ROLE_ARN="${ROLE_ARN:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

echo "========================================"
echo "Building ${LAMBDA_NAME} package"
echo "========================================"
echo "SCRIPT_DIR: $SCRIPT_DIR"

log_info "Syntax-checking JS sources…"
( cd "$SCRIPT_DIR" && node --check index.js )

log_info "Cleaning up old package…"
rm -f "$ZIP_FILE"

log_info "Creating deployment package…"
cd "$SCRIPT_DIR"
zip -r "$ZIP_FILE" . \
    -x "*.zip" \
    -x "*.sh" \
    -x ".git/*" \
    -x ".DS_Store" \
    -x "node_modules/*" \
    -x "README*.md"

ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
log_success "Package created: $ZIP_FILE ($ZIP_SIZE)"

# Build env-vars string for create/update calls. Only set env if at least
# APPSYNC_API_URL is provided (this Lambda is useless without it).
ENV_VARS=""
if [ -n "${APPSYNC_API_URL:-}" ]; then
    ENV_VARS="Variables={"
    ENV_VARS+="APPSYNC_API_URL=${APPSYNC_API_URL},"
    ENV_VARS+="APPSYNC_API_KEY=${APPSYNC_API_KEY:-},"
    ENV_VARS+="MESSAGING_ROUTING_TABLE=${MESSAGING_ROUTING_TABLE:-messaging_inbound_routing}"
    if [ -n "${INBOUND_EMAIL_S3_BUCKET:-}" ]; then
        ENV_VARS+=",INBOUND_EMAIL_S3_BUCKET=${INBOUND_EMAIL_S3_BUCKET}"
    fi
    ENV_VARS+="}"
fi

case "$1" in
  --deploy|-d)
    log_info "Updating Lambda function code…"
    aws lambda update-function-code \
        --function-name "$LAMBDA_NAME" \
        --region "$AWS_REGION" \
        --zip-file "fileb://$ZIP_FILE" \
        --profile "$AWS_PROFILE" \
        --no-cli-pager
    log_success "Lambda $LAMBDA_NAME code updated."

    if [ -n "$ENV_VARS" ]; then
        log_info "Updating Lambda configuration (env vars)…"
        aws lambda update-function-configuration \
            --function-name "$LAMBDA_NAME" \
            --region "$AWS_REGION" \
            --environment "$ENV_VARS" \
            --profile "$AWS_PROFILE" \
            --no-cli-pager > /dev/null
        log_success "Env vars updated."
    fi
    ;;

  --create|-c)
    if [ -z "$ROLE_ARN" ]; then
        log_error "ROLE_ARN must be set to create the function. e.g.:"
        log_error "  ROLE_ARN=arn:aws:iam::ACCOUNT:role/inboundMessageRole \\"
        log_error "  APPSYNC_API_URL=https://...graphql APPSYNC_API_KEY=da2-... \\"
        log_error "  $0 --create"
        exit 1
    fi
    if [ -z "$ENV_VARS" ]; then
        log_warn "APPSYNC_API_URL not set — function will be created without env vars."
        log_warn "Set them with --deploy after creation, or rerun --create with the vars set."
    fi

    log_info "Creating Lambda function $LAMBDA_NAME…"
    CREATE_ARGS=(
        --function-name "$LAMBDA_NAME"
        --runtime "$RUNTIME"
        --role "$ROLE_ARN"
        --handler "$HANDLER"
        --zip-file "fileb://$ZIP_FILE"
        --timeout "$TIMEOUT"
        --memory-size "$MEMORY"
        --region "$AWS_REGION"
        --profile "$AWS_PROFILE"
        --no-cli-pager
    )
    if [ -n "$ENV_VARS" ]; then
        CREATE_ARGS+=( --environment "$ENV_VARS" )
    fi
    aws lambda create-function "${CREATE_ARGS[@]}"
    log_success "Lambda $LAMBDA_NAME created."
    log_info "Next: subscribe this Lambda to the inbound SNS topic(s)."
    log_info "  aws sns subscribe --topic-arn <sms-topic-arn> --protocol lambda --notification-endpoint <fn-arn>"
    ;;

  *)
    echo ""
    echo "Built. To deploy or create:"
    echo "  $0 --deploy            # update existing function code (+ env if vars set)"
    echo "  ROLE_ARN=... APPSYNC_API_URL=... APPSYNC_API_KEY=... $0 --create"
    echo ""
    echo "Or manually:"
    echo "  aws lambda update-function-code --function-name $LAMBDA_NAME \\"
    echo "      --region $AWS_REGION --zip-file fileb://$ZIP_FILE \\"
    echo "      --profile $AWS_PROFILE"
    ;;
esac
