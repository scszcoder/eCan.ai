#!/bin/bash
#
# Deploy eCan.ai Cloud Worker to ECS Fargate
#
# Usage: ./deploy-worker.sh [--cluster CLUSTER_NAME] [--service SERVICE_NAME]
#

set -e

# Default configuration
AWS_PROFILE="${AWS_PROFILE:-maipps8}"
AWS_REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="${CLUSTER_NAME:-ecan-cluster}"
SERVICE_NAME="${SERVICE_NAME:-ecan-cloud-worker}"
TASK_DEFINITION_FILE="$(dirname "$0")/../infrastructure/ecs/task-definition-worker.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --cluster)
            CLUSTER_NAME="$2"
            shift 2
            ;;
        --service)
            SERVICE_NAME="$2"
            shift 2
            ;;
        --profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --cluster CLUSTER_NAME   ECS cluster name (default: ecan-cluster)"
            echo "  --service SERVICE_NAME   ECS service name (default: ecan-cloud-worker)"
            echo "  --profile AWS_PROFILE    AWS CLI profile (default: maipps8)"
            echo "  --region AWS_REGION      AWS region (default: us-east-1)"
            echo "  --help                   Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo ""
echo "=============================================="
echo "  eCan.ai Cloud Worker - ECS Deployment"
echo "=============================================="
echo ""

log_info "Configuration:"
log_info "  Profile:    ${AWS_PROFILE}"
log_info "  Region:     ${AWS_REGION}"
log_info "  Cluster:    ${CLUSTER_NAME}"
log_info "  Service:    ${SERVICE_NAME}"
echo ""

# Export AWS profile
export AWS_PROFILE
export AWS_DEFAULT_REGION="${AWS_REGION}"

# Check if task definition file exists
if [[ ! -f "${TASK_DEFINITION_FILE}" ]]; then
    log_error "Task definition file not found: ${TASK_DEFINITION_FILE}"
    exit 1
fi

# Step 1: Register the task definition
log_info "Registering task definition..."
TASK_DEF_ARN=$(aws ecs register-task-definition \
    --cli-input-json "file://${TASK_DEFINITION_FILE}" \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

if [[ -z "${TASK_DEF_ARN}" ]]; then
    log_error "Failed to register task definition"
    exit 1
fi
log_success "Task definition registered: ${TASK_DEF_ARN}"

# Step 2: Check if cluster exists
log_info "Checking if cluster '${CLUSTER_NAME}' exists..."
CLUSTER_STATUS=$(aws ecs describe-clusters \
    --clusters "${CLUSTER_NAME}" \
    --query 'clusters[0].status' \
    --output text 2>/dev/null || echo "MISSING")

if [[ "${CLUSTER_STATUS}" == "MISSING" || "${CLUSTER_STATUS}" == "None" ]]; then
    log_warning "Cluster '${CLUSTER_NAME}' not found. Creating..."
    aws ecs create-cluster --cluster-name "${CLUSTER_NAME}" > /dev/null
    log_success "Cluster created: ${CLUSTER_NAME}"
else
    log_info "Cluster exists with status: ${CLUSTER_STATUS}"
fi

# Step 3: Check if service exists
log_info "Checking if service '${SERVICE_NAME}' exists..."
SERVICE_STATUS=$(aws ecs describe-services \
    --cluster "${CLUSTER_NAME}" \
    --services "${SERVICE_NAME}" \
    --query 'services[0].status' \
    --output text 2>/dev/null || echo "MISSING")

if [[ "${SERVICE_STATUS}" == "MISSING" || "${SERVICE_STATUS}" == "None" ]]; then
    log_warning "Service '${SERVICE_NAME}' not found."
    log_info "To create a new service, you need to specify networking configuration."
    echo ""
    echo "Create the service with:"
    echo ""
    echo "  aws ecs create-service \\"
    echo "    --cluster ${CLUSTER_NAME} \\"
    echo "    --service-name ${SERVICE_NAME} \\"
    echo "    --task-definition ${TASK_DEF_ARN} \\"
    echo "    --desired-count 1 \\"
    echo "    --launch-type FARGATE \\"
    echo "    --network-configuration 'awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx],assignPublicIp=ENABLED}'"
    echo ""
    log_info "Or run a standalone task:"
    echo ""
    echo "  aws ecs run-task \\"
    echo "    --cluster ${CLUSTER_NAME} \\"
    echo "    --task-definition ${TASK_DEF_ARN} \\"
    echo "    --launch-type FARGATE \\"
    echo "    --network-configuration 'awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx],assignPublicIp=ENABLED}'"
    echo ""
else
    # Service exists, update it
    log_info "Service exists with status: ${SERVICE_STATUS}"
    log_info "Updating service with new task definition..."
    
    aws ecs update-service \
        --cluster "${CLUSTER_NAME}" \
        --service "${SERVICE_NAME}" \
        --task-definition "${TASK_DEF_ARN}" \
        --force-new-deployment > /dev/null
    
    log_success "Service updated! New deployment started."
    echo ""
    log_info "Monitor deployment with:"
    echo "  aws ecs describe-services --cluster ${CLUSTER_NAME} --services ${SERVICE_NAME}"
fi

echo ""
echo "=============================================="
log_success "Deployment complete!"
echo "=============================================="
