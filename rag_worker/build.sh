#!/usr/bin/env bash
# Build and push the RAG worker Docker image to ECR.
# Usage: ./build.sh [--push]
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
ECR_REPO="ecan-rag-worker"
IMAGE_TAG="${IMAGE_TAG:-latest}"
FULL_IMAGE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Building RAG Worker Docker image ==="
echo "Image: ${FULL_IMAGE}"

docker build -t "${ECR_REPO}:${IMAGE_TAG}" "${SCRIPT_DIR}"

if [[ "${1:-}" == "--push" ]]; then
    echo "=== Pushing to ECR ==="
    # Create repo if it doesn't exist
    aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${AWS_REGION}" 2>/dev/null || \
        aws ecr create-repository --repository-name "${ECR_REPO}" --region "${AWS_REGION}"
    # Login
    aws ecr get-login-password --region "${AWS_REGION}" | \
        docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    # Tag and push
    docker tag "${ECR_REPO}:${IMAGE_TAG}" "${FULL_IMAGE}"
    docker push "${FULL_IMAGE}"
    echo "=== Pushed ${FULL_IMAGE} ==="
else
    echo "(Skipping push. Use --push to push to ECR)"
fi
