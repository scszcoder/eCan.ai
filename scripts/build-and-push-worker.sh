#!/bin/bash
# ============================================================================
# eCan.ai Cloud Worker - Build and Push to ECR
# ============================================================================
# This script builds the Docker image and pushes it to Amazon ECR.
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Docker installed and running
#   - IAM permissions: ecr:GetAuthorizationToken, ecr:CreateRepository,
#     ecr:BatchCheckLayerAvailability, ecr:PutImage, ecr:InitiateLayerUpload,
#     ecr:UploadLayerPart, ecr:CompleteLayerUpload
#
# Usage:
#   ./scripts/build-and-push-worker.sh [options]
#
# Options:
#   --region REGION       AWS region (default: us-east-1)
#   --profile PROFILE     AWS CLI profile (default: maipps8)
#   --repo-name NAME      ECR repository name (default: ecan-cloud-worker)
#   --tag TAG             Image tag (default: latest)
#   --no-cache            Build without Docker cache
#   --skip-push           Build only, don't push to ECR
#   --create-repo         Create ECR repository if it doesn't exist
#   --help                Show this help message
#
# Examples:
#   ./scripts/build-and-push-worker.sh
#   ./scripts/build-and-push-worker.sh --tag v1.0.0
#   ./scripts/build-and-push-worker.sh --region ap-southeast-1 --no-cache
# ============================================================================

set -e  # Exit on error

# Default configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-maipps8}"
REPO_NAME="ecan-cloud-worker"
IMAGE_TAG="latest"
NO_CACHE=""
SKIP_PUSH=false
CREATE_REPO=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Show help
show_help() {
    head -35 "$0" | tail -30
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        --repo-name)
            REPO_NAME="$2"
            shift 2
            ;;
        --tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --skip-push)
            SKIP_PUSH=true
            shift
            ;;
        --create-repo)
            CREATE_REPO=true
            shift
            ;;
        --help|-h)
            show_help
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            ;;
    esac
done

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log_info "Project root: $PROJECT_ROOT"

# Export AWS profile for all AWS CLI commands
export AWS_PROFILE
export AWS_DEFAULT_REGION="$AWS_REGION"

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install AWS CLI first."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    fi
    
    log_success "All prerequisites met"
}

# Get AWS account ID
get_aws_account_id() {
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        log_error "Failed to get AWS account ID"
        exit 1
    fi
    log_info "AWS Account ID: $AWS_ACCOUNT_ID"
}

# Create ECR repository if needed
create_ecr_repo() {
    if [ "$CREATE_REPO" = true ]; then
        log_info "Checking if ECR repository exists..."
        
        if aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$AWS_REGION" &> /dev/null; then
            log_info "Repository '$REPO_NAME' already exists"
        else
            log_info "Creating ECR repository: $REPO_NAME"
            aws ecr create-repository \
                --repository-name "$REPO_NAME" \
                --region "$AWS_REGION" \
                --image-scanning-configuration scanOnPush=true \
                --encryption-configuration encryptionType=AES256
            log_success "Repository created: $REPO_NAME"
        fi
    fi
}

# Login to ECR
ecr_login() {
    log_info "Logging in to ECR..."
    
    ECR_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
    
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$ECR_URI"
    
    log_success "Logged in to ECR: $ECR_URI"
}

# Build Docker image
build_image() {
    log_info "Building Docker image..."
    
    cd "$PROJECT_ROOT"
    
    FULL_IMAGE_NAME="$REPO_NAME:$IMAGE_TAG"
    
    log_info "Image: $FULL_IMAGE_NAME"
    log_info "Dockerfile: Dockerfile.worker"
    
    # Build with progress output
    docker build \
        $NO_CACHE \
        -f Dockerfile.worker \
        -t "$FULL_IMAGE_NAME" \
        --progress=plain \
        .
    
    log_success "Image built: $FULL_IMAGE_NAME"
    
    # Show image size
    IMAGE_SIZE=$(docker images "$FULL_IMAGE_NAME" --format "{{.Size}}")
    log_info "Image size: $IMAGE_SIZE"
}

# Tag and push to ECR
push_to_ecr() {
    if [ "$SKIP_PUSH" = true ]; then
        log_warn "Skipping push to ECR (--skip-push)"
        return
    fi
    
    log_info "Tagging image for ECR..."
    
    ECR_IMAGE="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO_NAME:$IMAGE_TAG"
    
    docker tag "$REPO_NAME:$IMAGE_TAG" "$ECR_IMAGE"
    
    log_info "Pushing to ECR: $ECR_IMAGE"
    docker push "$ECR_IMAGE"
    
    log_success "Image pushed to ECR!"
    echo ""
    echo "=============================================="
    echo -e "${GREEN}ECR Image URI:${NC}"
    echo "$ECR_IMAGE"
    echo "=============================================="
    echo ""
    echo "Use this URI in your ECS task definition:"
    echo "  \"image\": \"$ECR_IMAGE\""
    echo ""
}

# Also tag as latest if using a version tag
tag_latest() {
    if [ "$IMAGE_TAG" != "latest" ] && [ "$SKIP_PUSH" = false ]; then
        log_info "Also tagging as 'latest'..."
        
        ECR_LATEST="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO_NAME:latest"
        docker tag "$REPO_NAME:$IMAGE_TAG" "$ECR_LATEST"
        docker push "$ECR_LATEST"
        
        log_success "Also pushed as: $ECR_LATEST"
    fi
}

# Cleanup old images (optional)
cleanup_local() {
    log_info "Local images:"
    docker images "$REPO_NAME" --format "table {{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
}

# Main execution
main() {
    echo ""
    echo "=============================================="
    echo "  eCan.ai Cloud Worker - Build & Push to ECR"
    echo "=============================================="
    echo ""
    
    log_info "Configuration:"
    log_info "  Profile:    $AWS_PROFILE"
    log_info "  Region:     $AWS_REGION"
    log_info "  Repository: $REPO_NAME"
    log_info "  Tag:        $IMAGE_TAG"
    echo ""
    
    check_prerequisites
    get_aws_account_id
    create_ecr_repo
    
    if [ "$SKIP_PUSH" = false ]; then
        ecr_login
    fi
    
    build_image
    push_to_ecr
    tag_latest
    cleanup_local
    
    echo ""
    log_success "Done!"
}

# Run main
main
