#!/bin/bash
# deploy-all.sh - Deploy Lambda, Cloud Worker, and Frontend in one go
#
# Usage:
#   ./scripts/deploy-all.sh              # Deploy all (lambda, worker, frontend)
#   ./scripts/deploy-all.sh lambda       # Deploy only all Lambdas
#   ./scripts/deploy-all.sh worker       # Deploy only Cloud Worker
#   ./scripts/deploy-all.sh frontend     # Deploy only Frontend
#   ./scripts/deploy-all.sh lambda worker # Deploy Lambda and Worker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AWS_PROFILE="${AWS_PROFILE:-maipps8}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ECR config
ECR_REPO="667118410653.dkr.ecr.${AWS_REGION}.amazonaws.com/ecan-cloud-worker"

deploy_lambda_skill_editor() {
    log_info "=========================================="
    log_info "Deploying Lambda: skill_editor_agent"
    log_info "=========================================="
    
    cd "$REPO_ROOT/lambda_functions/skill_editor_lambda"
    
    # Build the Lambda package
    log_info "Building Lambda package..."
    ./build_lambda.sh
    
    # Deploy to AWS
    log_info "Deploying to AWS Lambda..."
    aws lambda update-function-code \
        --function-name skill_editor_agent \
        --region "$AWS_REGION" \
        --zip-file fileb:///tmp/skill_editor_agent.zip \
        --profile "$AWS_PROFILE" \
        --no-cli-pager
    
    log_success "Lambda skill_editor_agent deployed successfully!"
}

deploy_lambda_cloud_tester() {
    log_info "=========================================="
    log_info "Deploying Lambda: cloud_tester"
    log_info "=========================================="
    
    cd "$REPO_ROOT/lambda_functions/cloud_tester"
    
    # Build and deploy (build_lambda.sh handles both)
    log_info "Building and deploying Lambda package..."
    ./build_lambda.sh
    
    log_success "Lambda cloud_tester deployed successfully!"
}

deploy_lambda_agent_scheduler() {
    log_info "=========================================="
    log_info "Deploying Lambda: agentScheduler"
    log_info "=========================================="
    
    cd "$REPO_ROOT/lambda_functions/agentScheduler"
    
    # Build the Lambda package
    log_info "Building Lambda package..."
    ./build_lambda.sh
    
    # Deploy to AWS
    log_info "Deploying to AWS Lambda..."
    aws lambda update-function-code \
        --function-name agentScheduler \
        --region "$AWS_REGION" \
        --zip-file fileb:///tmp/agentScheduler.zip \
        --profile "$AWS_PROFILE" \
        --no-cli-pager
    
    log_success "Lambda agentScheduler deployed successfully!"
}

deploy_lambda_chatter() {
    log_info "=========================================="
    log_info "Deploying Lambda: chatter"
    log_info "=========================================="
    
    cd "$REPO_ROOT/lambda_functions/chatter"
    
    # Build and deploy (build_lambda.sh handles both)
    log_info "Building and deploying Lambda package..."
    ./build_lambda.sh
    
    log_success "Lambda chatter deployed successfully!"
}

deploy_lambda() {
    # Deploy all Lambda functions
    deploy_lambda_skill_editor
    deploy_lambda_cloud_tester
    deploy_lambda_agent_scheduler
    deploy_lambda_chatter
}

deploy_worker() {
    log_info "=========================================="
    log_info "Deploying Cloud Worker"
    log_info "=========================================="
    
    cd "$REPO_ROOT"
    
    # Get current revision from worker_main.py
    REVISION=$(grep -oP 'WORKER_REVISION = "\K[^"]+' agent/cloud_worker/worker_main.py || echo "unknown")
    log_info "Worker revision: $REVISION"
    
    # Build Docker image
    log_info "Building Docker image..."
    docker build -f Dockerfile.worker -t ecan-cloud-worker:latest .
    
    # Login to ECR
    log_info "Logging in to ECR..."
    aws ecr get-login-password --region "$AWS_REGION" --profile "$AWS_PROFILE" | \
        docker login --username AWS --password-stdin "667118410653.dkr.ecr.${AWS_REGION}.amazonaws.com"
    
    # Tag and push
    log_info "Pushing to ECR..."
    docker tag ecan-cloud-worker:latest "$ECR_REPO:latest"
    docker push "$ECR_REPO:latest"
    
    log_success "Cloud Worker deployed successfully! (rev: $REVISION)"
}

deploy_frontend() {
    log_info "=========================================="
    log_info "Deploying Frontend (gui_v2)"
    log_info "=========================================="
    
    cd "$REPO_ROOT/gui_v2"
    
    # Build frontend (use npx pnpm or direct path)
    # Increase Node memory to handle large builds
    log_info "Building frontend..."

    # Vite builds can be killed by the OOM killer (exit 137) on smaller hosts.
    # Add extra swap (idempotent) and use a conservative Node heap cap.
    if ! swapon --show | awk '{print $1}' | grep -q '^/swapfile2$'; then
        if [ -f /swapfile2 ]; then
            log_warn "Enabling existing /swapfile2 swap..."
            sudo swapon /swapfile2 || true
        else
            log_warn "Creating extra swap /swapfile2 (8G) to reduce OOM kills during vite build..."
            sudo fallocate -l 8G /swapfile2 || sudo dd if=/dev/zero of=/swapfile2 bs=1M count=8192
            sudo chmod 600 /swapfile2
            sudo mkswap /swapfile2
            sudo swapon /swapfile2
        fi
    fi

    export NODE_OPTIONS="--max-old-space-size=3072"

    # Build modes:
    # - cn.desktop.production: CN desktop app (PyInstaller)
    # - intl.desktop.production: Intl desktop app (PyInstaller)
    # - cn.web.production: CN web deployment (base: /app/gui-v2/)
    # - intl.web.production: Intl web deployment (base: /app/gui-v2/)
    #
    # For desktop builds, omit VITE_BASE (defaults to './')
    # For web builds, set VITE_BASE to the deployment path
    #
    # The PRODUCT variable controls which .env file is loaded:
    # - PRODUCT=cn: .env.cn.* files (CloudBase auth)
    # - PRODUCT=intl: .env.intl.* files (Cognito auth)
    PRODUCT="${PRODUCT:-cn}"
    PLATFORM="${PLATFORM:-web}"
    ENVIRONMENT="${ENVIRONMENT:-production}"

    VITE_MODE="${PRODUCT}.${PLATFORM}.${ENVIRONMENT}"

    if [ "$PLATFORM" = "web" ]; then
        export VITE_BASE="${VITE_BASE:-/app/gui-v2/}"
    fi

    log_info "Building frontend: mode=$VITE_MODE, base=$VITE_BASE"

    if command -v pnpm &> /dev/null; then
        pnpm run build -- --mode "$VITE_MODE"
    elif [ -f "$HOME/.local/share/pnpm/pnpm" ]; then
        "$HOME/.local/share/pnpm/pnpm" run build -- --mode "$VITE_MODE"
    else
        npx pnpm run build -- --mode "$VITE_MODE"
    fi
    
    # Deploy to web server
    log_info "Deploying to /var/www/html/app/gui-v2/..."
    sudo cp -r dist/* /var/www/html/app/gui-v2/
    
    log_success "Frontend deployed successfully!"
}

# Parse arguments
DEPLOY_LAMBDA=false
DEPLOY_WORKER=false
DEPLOY_FRONTEND=false

if [ $# -eq 0 ]; then
    # No arguments - deploy all
    DEPLOY_LAMBDA=true
    DEPLOY_WORKER=true
    DEPLOY_FRONTEND=true
else
    for arg in "$@"; do
        case $arg in
            lambda|Lambda|LAMBDA)
                DEPLOY_LAMBDA=true
                ;;
            worker|Worker|WORKER)
                DEPLOY_WORKER=true
                ;;
            frontend|Frontend|FRONTEND|fe|FE)
                DEPLOY_FRONTEND=true
                ;;
            all|ALL)
                DEPLOY_LAMBDA=true
                DEPLOY_WORKER=true
                DEPLOY_FRONTEND=true
                ;;
            *)
                log_error "Unknown argument: $arg"
                echo "Usage: $0 [lambda] [worker] [frontend] [all]"
                exit 1
                ;;
        esac
    done
fi

# Show what we're deploying
log_info "Deployment targets:"
$DEPLOY_LAMBDA && log_info "  - Lambda (skill_editor_agent, cloud_tester, agentScheduler)"
$DEPLOY_WORKER && log_info "  - Cloud Worker"
$DEPLOY_FRONTEND && log_info "  - Frontend"
echo ""

START_TIME=$(date +%s)

# Run deployments
$DEPLOY_LAMBDA && deploy_lambda
$DEPLOY_WORKER && deploy_worker
$DEPLOY_FRONTEND && deploy_frontend

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
log_success "=========================================="
log_success "All deployments completed in ${ELAPSED}s"
log_success "=========================================="
