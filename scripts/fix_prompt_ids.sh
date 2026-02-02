#!/bin/bash
# fix_prompt_ids.sh - Fix prompt_id values to be just "pr-*" format
#
# Usage: ./fix_prompt_ids.sh [--dry-run]
#
# This script scans Agent_Prompts table and fixes prompt_id values
# from "name_pr-123456" to just "pr-123456"

set -e

TABLE="Agent_Prompts"
REGION="us-east-1"
PROFILE="maipps8"
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            echo "[DRY-RUN MODE] No actual writes will be performed"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "Fix Prompt IDs Script"
echo "=========================================="
echo "Table: $TABLE"
echo "Region: $REGION"
echo ""

# Scan all items from the table
items=$(aws dynamodb scan \
    --table-name "$TABLE" \
    --profile "$PROFILE" \
    --region "$REGION" \
    --output json)

count=$(echo "$items" | jq '.Count')
echo "Found $count items to check"
echo ""

updated=0
skipped=0

# Process each item
echo "$items" | jq -c '.Items[]' | while read -r item; do
    owner_id=$(echo "$item" | jq -r '.owner_id.S')
    agent_id=$(echo "$item" | jq -r '.agent_id.S')
    current_prompt_id=$(echo "$item" | jq -r '.prompt_id.S')
    prompt_name=$(echo "$item" | jq -r '.prompt_name.S // "unknown"')
    
    # Extract just the "pr-*" part from the prompt_id
    # Pattern: look for "pr-" followed by digits
    if [[ "$current_prompt_id" =~ (pr-[0-9]+) ]]; then
        new_prompt_id="${BASH_REMATCH[1]}"
    else
        echo "  [SKIP] No pr-* pattern found in: $current_prompt_id"
        ((skipped++)) || true
        continue
    fi
    
    # Check if already in correct format
    if [ "$current_prompt_id" = "$new_prompt_id" ]; then
        echo "  [OK] Already correct: $owner_id / $agent_id -> $current_prompt_id"
        continue
    fi
    
    echo "  Processing: $owner_id / $agent_id"
    echo "    Current prompt_id: $current_prompt_id"
    echo "    New prompt_id:     $new_prompt_id"
    
    if [ "$DRY_RUN" = true ]; then
        echo "    [DRY-RUN] Would update prompt_id"
        continue
    fi
    
    # Update the item in DynamoDB
    aws dynamodb update-item \
        --table-name "$TABLE" \
        --key "{\"owner_id\": {\"S\": \"$owner_id\"}, \"agent_id\": {\"S\": \"$agent_id\"}}" \
        --update-expression "SET prompt_id = :new_id" \
        --expression-attribute-values "{\":new_id\": {\"S\": \"$new_prompt_id\"}}" \
        --profile "$PROFILE" \
        --region "$REGION"
    
    echo "    [OK] Updated"
    ((updated++)) || true
done

echo ""
echo "=========================================="
echo "Complete!"
echo "=========================================="
