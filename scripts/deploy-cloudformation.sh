#!/bin/bash
#
# Deploy eCan.ai Cloud Worker CloudFormation Stack
#
# Usage: ./deploy-cloudformation.sh --vpc-id vpc-xxx --subnet-ids subnet-xxx,subnet-yyy
#

set -e

# Default configuration
AWS_PROFILE="${AWS_PROFILE:-maipps8}"
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="ecan-cloud-worker"
TEMPLATE_FILE="$(dirname "$0")/../infrastructure/cloudformation/ecan-cloud-worker.yaml"

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

# Parameters
VPC_ID=""
SUBNET_IDS=""
IMAGE_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/ecan-cloud-worker:latest"
DESIRED_COUNT=1
ENVIRONMENT="production"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --vpc-id)
            VPC_ID="$2"
            shift 2
            ;;
        --subnet-ids)
            SUBNET_IDS="$2"
            shift 2
            ;;
        --image-uri)
            IMAGE_URI="$2"
            shift 2
            ;;
        --desired-count)
            DESIRED_COUNT="$2"
            shift 2
            ;;
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --stack-name)
            STACK_NAME="$2"
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
            echo "Required:"
            echo "  --vpc-id VPC_ID          VPC ID where ECS tasks will run"
            echo "  --subnet-ids IDS         Comma-separated subnet IDs (with internet access)"
            echo ""
            echo "Optional:"
            echo "  --image-uri URI          ECR image URI (default: current v1.0.0)"
            echo "  --desired-count N        Number of tasks (default: 1)"
            echo "  --environment ENV        Environment: production|staging|development"
            echo "  --stack-name NAME        CloudFormation stack name (default: ecan-cloud-worker)"
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
echo "  eCan.ai CloudFormation Deployment"
echo "=============================================="
echo ""

# Validate required parameters
if [[ -z "${VPC_ID}" ]]; then
    log_error "Missing required parameter: --vpc-id"
    echo ""
    echo "To find your VPC ID, run:"
    echo "  aws ec2 describe-vpcs --profile ${AWS_PROFILE} --query 'Vpcs[*].[VpcId,Tags[?Key==\`Name\`].Value|[0]]' --output table"
    echo ""
    exit 1
fi

if [[ -z "${SUBNET_IDS}" ]]; then
    log_error "Missing required parameter: --subnet-ids"
    echo ""
    echo "To find your subnet IDs, run:"
    echo "  aws ec2 describe-subnets --profile ${AWS_PROFILE} --filters \"Name=vpc-id,Values=${VPC_ID}\" --query 'Subnets[*].[SubnetId,AvailabilityZone,Tags[?Key==\`Name\`].Value|[0]]' --output table"
    echo ""
    exit 1
fi

log_info "Configuration:"
log_info "  Profile:       ${AWS_PROFILE}"
log_info "  Region:        ${AWS_REGION}"
log_info "  Stack Name:    ${STACK_NAME}"
log_info "  VPC ID:        ${VPC_ID}"
log_info "  Subnet IDs:    ${SUBNET_IDS}"
log_info "  Image URI:     ${IMAGE_URI}"
log_info "  Desired Count: ${DESIRED_COUNT}"
log_info "  Environment:   ${ENVIRONMENT}"
echo ""

# Export AWS profile
export AWS_PROFILE
export AWS_DEFAULT_REGION="${AWS_REGION}"

# Check if template file exists
if [[ ! -f "${TEMPLATE_FILE}" ]]; then
    log_error "Template file not found: ${TEMPLATE_FILE}"
    exit 1
fi

# Validate template
log_info "Validating CloudFormation template..."
aws cloudformation validate-template \
    --template-body "file://${TEMPLATE_FILE}" > /dev/null
log_success "Template is valid"

# Check if stack exists
STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

if [[ "${STACK_STATUS}" == "DOES_NOT_EXIST" ]]; then
    log_info "Creating new stack: ${STACK_NAME}"
    OPERATION="create-stack"
    WAIT_OPERATION="stack-create-complete"
else
    log_info "Updating existing stack: ${STACK_NAME} (current status: ${STACK_STATUS})"
    OPERATION="update-stack"
    WAIT_OPERATION="stack-update-complete"
fi

# Deploy the stack
log_info "Deploying CloudFormation stack..."

aws cloudformation ${OPERATION} \
    --stack-name "${STACK_NAME}" \
    --template-body "file://${TEMPLATE_FILE}" \
    --parameters \
        ParameterKey=VpcId,ParameterValue="${VPC_ID}" \
        ParameterKey=SubnetIds,ParameterValue="\"${SUBNET_IDS}\"" \
        ParameterKey=WorkerImageUri,ParameterValue="${IMAGE_URI}" \
        ParameterKey=DesiredCount,ParameterValue="${DESIRED_COUNT}" \
        ParameterKey=Environment,ParameterValue="${ENVIRONMENT}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --tags Key=Project,Value=eCan.ai Key=ManagedBy,Value=CloudFormation

log_info "Waiting for stack operation to complete..."
log_info "This may take several minutes..."

aws cloudformation wait ${WAIT_OPERATION} --stack-name "${STACK_NAME}"

log_success "Stack operation completed!"

# Get outputs
echo ""
echo "=============================================="
echo "  Stack Outputs"
echo "=============================================="
echo ""

aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

echo ""
log_info "To view service status:"
echo "  aws ecs describe-services --cluster ecan-cluster --services ecan-cloud-worker --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'"
echo ""
log_info "To view logs:"
echo "  aws logs tail /ecs/ecan-cloud-worker --follow"
echo ""
log_info "To exec into a running task:"
echo "  aws ecs execute-command --cluster ecan-cluster --task <TASK_ID> --container ecan-cloud-worker --interactive --command '/bin/bash'"
echo ""

echo "=============================================="
log_success "Deployment complete!"
echo "=============================================="
