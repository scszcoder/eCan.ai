#!/usr/bin/env bash
#
# Upload settings JSON files to DynamoDB ECAN_Settings table.
#
# Usage:
#   ./upload-settings-to-dynamodb.sh [owner_id]
#
# Default owner_id: songc_yahoo_com
#
# DynamoDB Table: ECAN_Settings
#   PK: owner_id  (String)  – normalized email, e.g. "songc_yahoo_com"
#   SK: sid        (String)  – random settings-id, e.g. "set-a1b2c3d4"
#   general_settings      (S) – JSON string of general settings defaults
#   llm_providers         (S) – JSON string from gui/config/llm_providers.json
#   embedding_providers   (S) – JSON string from gui/config/embedding_providers.json
#   rerank_providers      (S) – JSON string from gui/config/rerank_providers.json
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

OWNER_ID="${1:-songc_yahoo_com}"
TABLE_NAME="ECAN_Settings"
REGION="us-east-1"
PROFILE="maipps8"

# Generate a random settings ID
SID="set-$(openssl rand -hex 4)"

echo "=== Upload Settings to DynamoDB ==="
echo "  Table:    $TABLE_NAME"
echo "  Owner:    $OWNER_ID"
echo "  SID:      $SID"
echo "  Region:   $REGION"
echo ""

# Paths to provider config files
LLM_FILE="$REPO_ROOT/gui/config/llm_providers.json"
EMBEDDING_FILE="$REPO_ROOT/gui/config/embedding_providers.json"
RERANK_FILE="$REPO_ROOT/gui/config/rerank_providers.json"

# Verify files exist
for f in "$LLM_FILE" "$EMBEDDING_FILE" "$RERANK_FILE"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: File not found: $f"
    exit 1
  fi
done

# Build general_settings JSON (mirrors initialSettings in Settings.tsx)
GENERAL_SETTINGS=$(cat <<'EOJSON'
{
  "schedule_mode": "auto",
  "debug_mode": false,
  "default_wifi": "",
  "default_printer": "",
  "display_resolution": "D1920X1080",
  "default_webdriver_path": "",
  "build_dom_tree_script_path": "agent/ec_skills/dom/buildDomTree.js",
  "new_orders_dir": "",
  "new_bots_file_path": "",
  "new_orders_path": "",
  "browser_use_file_system_path": "",
  "browser_use_download_dir": "",
  "browser_use_user_data_dir": "",
  "gui_flowgram_schema": "myskills/node_schemas.json",
  "local_user_db_host": "127.0.0.1",
  "local_user_db_port": "5080",
  "local_agent_db_host": "",
  "local_agent_db_port": "6668",
  "local_agent_ports": [3600, 3800],
  "local_server_port": "4668",
  "lan_api_endpoint": "",
  "wan_api_endpoint": "https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql",
  "ws_api_endpoint": "wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql",
  "ws_api_host": "3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com",
  "ecan_cloud_searcher_url": "http://52.204.81.197:5808/search_components",
  "wan_api_key": "",
  "ocr_api_key": "",
  "network_api_engine": "lan",
  "schedule_engine": "wan",
  "ocr_api_endpoint": "http://52.204.81.197:8848/graphql/reqScreenTxtRead",
  "default_llm": "ChatOpenAI",
  "default_llm_model": "",
  "default_embedding": "OpenAI",
  "default_embedding_model": "text-embedding-3-small",
  "default_rerank": "",
  "default_rerank_model": "",
  "skill_use_git": false,
  "last_bots_file": "",
  "last_bots_file_time": 0,
  "last_order_file": "",
  "last_order_file_time": 0,
  "mids_forced_to_run": []
}
EOJSON
)

# Read provider files as compact JSON strings
LLM_JSON=$(python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1])),separators=(',',':')))" "$LLM_FILE")
EMBEDDING_JSON=$(python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1])),separators=(',',':')))" "$EMBEDDING_FILE")
RERANK_JSON=$(python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1])),separators=(',',':')))" "$RERANK_FILE")
GENERAL_JSON=$(echo "$GENERAL_SETTINGS" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin),separators=(',',':')))")

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Uploading to DynamoDB..."

# Use a Python script for the actual put-item because the JSON payloads are large
python3 - "$OWNER_ID" "$SID" "$GENERAL_JSON" "$LLM_JSON" "$EMBEDDING_JSON" "$RERANK_JSON" "$TIMESTAMP" "$TABLE_NAME" "$REGION" "$PROFILE" <<'PYEOF'
import sys
import json
import subprocess

owner_id = sys.argv[1]
sid = sys.argv[2]
general = sys.argv[3]
llm = sys.argv[4]
embedding = sys.argv[5]
rerank = sys.argv[6]
timestamp = sys.argv[7]
table = sys.argv[8]
region = sys.argv[9]
profile = sys.argv[10]

item = {
    "owner_id":           {"S": owner_id},
    "sid":                {"S": sid},
    "general_settings":   {"S": general},
    "llm_providers":      {"S": llm},
    "embedding_providers":{"S": embedding},
    "rerank_providers":   {"S": rerank},
    "created_at":         {"S": timestamp},
    "updated_at":         {"S": timestamp}
}

item_json = json.dumps(item)

cmd = [
    "aws", "dynamodb", "put-item",
    "--table-name", table,
    "--item", item_json,
    "--region", region,
    "--profile", profile
]

print(f"  PutItem: owner_id={owner_id}, sid={sid}")
result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode != 0:
    print(f"ERROR: {result.stderr}")
    sys.exit(1)
else:
    print("✅ Successfully uploaded settings to DynamoDB!")
    print(f"   owner_id: {owner_id}")
    print(f"   sid:      {sid}")
    if result.stdout.strip():
        print(result.stdout)
PYEOF

echo ""
echo "Done. You can verify with:"
echo "  aws dynamodb get-item --table-name $TABLE_NAME --key '{\"owner_id\":{\"S\":\"$OWNER_ID\"},\"sid\":{\"S\":\"$SID\"}}' --region $REGION --profile $PROFILE"
