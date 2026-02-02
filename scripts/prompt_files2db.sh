#!/bin/bash
# prompt_files2db.sh - Import prompts from S3 to DynamoDB Agent_Prompts table
#
# Usage: ./prompt_files2db.sh [--dry-run]
#
# This script reads prompt JSON files from S3 bucket ecan-skills:
#   - public/prompts/sample_prompts/*.json (owner_id="public", agent_id="any")
#   - <user>/prompts/*.json (owner_id=<user>, agent_id="any")
#
# And inserts them into DynamoDB table Agent_Prompts

set -e

BUCKET="ecan-skills"
TABLE="Agent_Prompts"
REGION="us-east-1"
PROFILE="maipps8"
DRY_RUN=false
TEMP_DIR="/tmp/prompt_import_$$"

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

# Cleanup function
cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

mkdir -p "$TEMP_DIR"

echo "=========================================="
echo "Prompt Files to DynamoDB Import Script"
echo "=========================================="
echo "Bucket: s3://$BUCKET"
echo "Table: $TABLE"
echo "Region: $REGION"
echo ""

# Function to get file last modified date from S3
get_s3_last_modified() {
    local s3_path="$1"
    aws s3api head-object --bucket "$BUCKET" --key "$s3_path" --profile "$PROFILE" --region "$REGION" \
        --query 'LastModified' --output text 2>/dev/null || echo ""
}

# Function to process a single prompt file
process_prompt_file() {
    local s3_key="$1"
    local owner_id="$2"
    local base_agent_id="$3"
    
    local filename=$(basename "$s3_key")
    local prompt_id="${filename%.json}"
    local local_file="$TEMP_DIR/$filename"
    
    # Composite agent_id: base_agent_id~prompt_id
    local agent_id="${base_agent_id}~${prompt_id}"
    
    echo "  Processing: $s3_key"
    
    # Download file
    if ! aws s3 cp "s3://$BUCKET/$s3_key" "$local_file" --profile "$PROFILE" --region "$REGION" --quiet 2>/dev/null; then
        echo "    [ERROR] Failed to download $s3_key"
        return 1
    fi
    
    # Get last modified date
    local last_mod_date=$(get_s3_last_modified "$s3_key")
    if [ -z "$last_mod_date" ]; then
        last_mod_date=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    fi
    
    # Read and validate JSON
    if ! jq -e . "$local_file" > /dev/null 2>&1; then
        echo "    [ERROR] Invalid JSON in $s3_key"
        return 1
    fi
    
    # Extract prompt_id from JSON "id" field (should be "pr-*" format)
    local json_prompt_id=$(jq -r '.id // empty' "$local_file" 2>/dev/null)
    if [ -n "$json_prompt_id" ] && [ "$json_prompt_id" != "null" ]; then
        prompt_id="$json_prompt_id"
    fi
    
    # Composite agent_id: base_agent_id~prompt_id
    local agent_id="${base_agent_id}~${prompt_id}"
    
    # Extract prompt_name from JSON (try "name" or "title" field, fallback to filename)
    local prompt_name=$(jq -r '.name // .title // empty' "$local_file" 2>/dev/null)
    if [ -z "$prompt_name" ] || [ "$prompt_name" = "null" ]; then
        prompt_name="$prompt_id"
    fi
    
    # Extract suitable_modes from JSON (default to "any")
    local suitable_modes=$(jq -r '.suitable_modes // .modes // "any"' "$local_file" 2>/dev/null)
    if [ -z "$suitable_modes" ] || [ "$suitable_modes" = "null" ]; then
        suitable_modes="any"
    fi
    
    # Extract metadata from JSON (default to {})
    local metadata=$(jq -c '.metadata // {}' "$local_file" 2>/dev/null)
    if [ -z "$metadata" ] || [ "$metadata" = "null" ]; then
        metadata="{}"
    fi
    
    # Stringify the entire prompt content
    local prompt_content=$(jq -c '.' "$local_file")
    
    # Escape for DynamoDB JSON
    local prompt_escaped=$(echo "$prompt_content" | jq -Rs '.')
    local metadata_escaped=$(echo "$metadata" | jq -Rs '.')
    
    echo "    owner_id: $owner_id"
    echo "    agent_id: $agent_id"
    echo "    prompt_id: $prompt_id"
    echo "    prompt_name: $prompt_name"
    echo "    suitable_modes: $suitable_modes"
    echo "    last_mod_date: $last_mod_date"
    
    if [ "$DRY_RUN" = true ]; then
        echo "    [DRY-RUN] Would insert into $TABLE"
        return 0
    fi
    
    # Build DynamoDB item JSON
    local item=$(cat <<EOF
{
    "owner_id": {"S": "$owner_id"},
    "agent_id": {"S": "$agent_id"},
    "prompt_id": {"S": "$prompt_id"},
    "prompt_name": {"S": "$prompt_name"},
    "prompt": {"S": $prompt_escaped},
    "suitable_modes": {"S": "$suitable_modes"},
    "metadata": {"S": $metadata_escaped},
    "last_mod_date": {"S": "$last_mod_date"}
}
EOF
)
    
    # Insert into DynamoDB
    if aws dynamodb put-item \
        --table-name "$TABLE" \
        --item "$item" \
        --profile "$PROFILE" \
        --region "$REGION" 2>/dev/null; then
        echo "    [OK] Inserted into $TABLE"
    else
        echo "    [ERROR] Failed to insert into $TABLE"
        return 1
    fi
    
    # Cleanup temp file
    rm -f "$local_file"
}

# ==========================================
# Process PUBLIC prompts
# ==========================================
echo ""
echo "[1/2] Processing PUBLIC prompts from public/prompts/sample_prompts/"
echo "----------------------------------------------"

public_files=$(aws s3 ls "s3://$BUCKET/public/prompts/sample_prompts/" --profile "$PROFILE" --region "$REGION" 2>/dev/null | grep '\.json$' | awk '{print $4}' || true)

if [ -z "$public_files" ]; then
    echo "  No public prompt files found"
else
    public_count=0
    while IFS= read -r file; do
        if [ -n "$file" ]; then
            process_prompt_file "public/prompts/sample_prompts/$file" "public" "any"
            ((public_count++)) || true
        fi
    done <<< "$public_files"
    echo ""
    echo "  Processed $public_count public prompt(s)"
fi

# ==========================================
# Process USER prompts
# ==========================================
echo ""
echo "[2/2] Processing USER prompts from <user>/prompts/"
echo "----------------------------------------------"

# List all top-level "directories" (user folders)
user_dirs=$(aws s3 ls "s3://$BUCKET/" --profile "$PROFILE" --region "$REGION" 2>/dev/null | grep 'PRE' | awk '{print $2}' | tr -d '/' || true)

user_total=0
if [ -z "$user_dirs" ]; then
    echo "  No user directories found"
else
    while IFS= read -r user_dir; do
        # Skip special directories
        if [ "$user_dir" = "public" ] || [ "$user_dir" = "tmp" ] || [ -z "$user_dir" ]; then
            continue
        fi
        
        # Check if user has prompts folder
        user_prompts=$(aws s3 ls "s3://$BUCKET/$user_dir/prompts/" --profile "$PROFILE" --region "$REGION" 2>/dev/null | grep '\.json$' | awk '{print $4}' || true)
        
        if [ -n "$user_prompts" ]; then
            echo ""
            echo "  User: $user_dir"
            while IFS= read -r file; do
                if [ -n "$file" ]; then
                    process_prompt_file "$user_dir/prompts/$file" "$user_dir" "any"
                    ((user_total++)) || true
                fi
            done <<< "$user_prompts"
        fi
    done <<< "$user_dirs"
fi

echo ""
echo "=========================================="
echo "Import Complete!"
echo "=========================================="
echo "Total user prompts processed: $user_total"
echo ""
