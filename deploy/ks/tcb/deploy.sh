#!/usr/bin/env bash
# Deploy the Knowledge Service to CloudBase 云托管. Runs ON THE CVM, in a
# folder that holds this script and dist/ (from make_context.py).
#
#   bash deploy.sh ecan-knowledge-test     # isolated twin, schema knowledge_test
#   bash deploy.sh ecan-knowledge          # production, schema knowledge
#
# Modelled on eCan_lambda/cn/tencent/cloudbase-graphql/ws/scripts/deploy.sh:
# secrets are never baked into the image; they go into the service's EnvParams
# (merged with what is already there), the VPC is bound with --vpc-config at
# deploy time, the CLI runs under expect with its real exit status, and the
# deploy only counts if the serving version actually changed.
#
# Secrets are read from the llm_proxy function's configuration (the owner of
# DATABASE_URL, PGSSL, LLM_PROXY_INTERNAL_TOKEN and ECAN_JWT_SECRET) and are
# kept in memory only; nothing prints them.
set -uo pipefail
export PATH=$HOME/.local/bin:$PATH

SERVICE="${1:-}"
case "$SERVICE" in
  ecan-knowledge-test) SCHEMA=knowledge_test; MIN_NUM=0 ;;
  ecan-knowledge)      SCHEMA=knowledge;      MIN_NUM=1 ;;
  *) echo "usage: bash deploy.sh ecan-knowledge-test|ecan-knowledge"; exit 2 ;;
esac
ENV_ID=sccb0-d0gc5398xf028be6a
PORT=8080
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/dist"
BUILD_VERSION="ks-$(date -u +%Y%m%d%H%M%S)"
LLM_PROXY_URL="https://${ENV_ID}.service.tcloudbase.com/api/llm-proxy"
VPC_JSON='{"vpcId":"vpc-2pt6t7qg","vpcCIDR":"10.0.0.0/16","subnetId":"subnet-h3cs01ip","subnetCIDR":"10.0.1.0/24"}'

[ -f "$SRC/Dockerfile" ] || { echo "missing $SRC/Dockerfile (run make_context.py and upload dist/)"; exit 1; }

detail_json() { tcb cloudrun detail --env-id "$ENV_ID" --service-name "$SERVICE" --json 2>/dev/null; }

online_versions() {
  detail_json | python3 -c '
import json,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw[raw.index("{"):]); d=d.get("data",d)
    print(",".join(sorted(v["VersionName"] for v in (d.get("OnlineVersionInfos") or []))))
except Exception:
    print("")'
}

run_deploy() {
  local vpc_file exp_file rc
  vpc_file="$(mktemp)"; exp_file="$(mktemp)"
  printf '%s' "$VPC_JSON" > "$vpc_file"
  cat > "$exp_file" <<EXP
#!/usr/bin/expect -f
set timeout 1800
log_user 1
log_file -a /tmp/ks_deploy_console.log
set vpc_json [exec cat "$vpc_file"]
cd "$HERE"
spawn tcb cloudrun deploy --env-id $ENV_ID --service-name $SERVICE --port $PORT --source ./dist --vpc-config \$vpc_json --force --wait
expect {
  -re "Enable gray deployment.*"      { send "\r"; exp_continue }
  -re "tasks? running.*\\\\?"         { send "Y\r"; exp_continue }
  -re "Overwrite.*\\\\?"              { send "Y\r"; exp_continue }
  -re "Confirm.*\\\\?"                { send "Y\r"; exp_continue }
  -re "Y/n|y/N"                       { send "Y\r"; exp_continue }
  -re "DEPLOY.*FAILED|ERROR.*deploy"  { puts "\nDEPLOY FAILED MARKER\n"; exit 1 }
  eof                                 { }
  timeout                             { puts "\nTIMEOUT\n"; exit 2 }
}
catch wait result
exit [lindex \$result 3]
EXP
  chmod +x "$exp_file"
  "$exp_file"; rc=$?
  rm -f "$exp_file" "$vpc_file"
  return $rc
}

# ---- 1. secrets from llm_proxy (memory only) -------------------------------------------
eval "$(python3 "$HERE/ks_secrets.py")" || { echo "cannot read llm_proxy configuration"; exit 1; }
missing=()
for k in DATABASE_URL LLM_PROXY_INTERNAL_TOKEN ECAN_JWT_SECRET; do
  v="KSV_$k"; [ -n "${!v:-}" ] || missing+=("$k")
done
[ ${#missing[@]} -eq 0 ] || { echo "llm_proxy is missing: ${missing[*]}"; exit 1; }
echo "secrets: loaded from llm_proxy (not shown)"

# ---- 2. first deploy creates the service --------------------------------------------------
PRE="$(online_versions)"
if [ -z "$(detail_json | grep -o '"ServerName"' | head -1)" ]; then
  echo "service $SERVICE does not exist: first deploy creates it (no secrets, every request but /healthz is 401)"
  run_deploy || { echo "first deploy failed; see /tmp/ks_deploy_console.log"; exit 1; }
  PRE="$(online_versions)"
fi

# ---- 3. merge EnvParams + sizing into the service config -----------------------------------
BODY="$(detail_json | SCHEMA="$SCHEMA" MIN_NUM="$MIN_NUM" PORT="$PORT" BUILD_VERSION="$BUILD_VERSION" \
  ENV_ID="$ENV_ID" LLM_PROXY_URL="$LLM_PROXY_URL" python3 -c '
import json,os,sys
raw=sys.stdin.read(); d=json.loads(raw[raw.index("{"):]); d=d.get("data",d)
cfg=d["ServerConfig"]
keep=("EnvId","ServerName","OpenAccessTypes","Cpu","Mem","MinNum","MaxNum","PolicyDetails","CustomLogs",
      "InitialDelaySeconds","CreateTime","Port","HasDockerfile","Dockerfile","BuildDir","InternalAccess","VpcConf",
      "EnvParams")
base={k:cfg.get(k) for k in keep}
try: env=json.loads(base.get("EnvParams") or "{}")
except Exception: env={}
env.update({
  "KS_PLANE": "public", "KS_DB_SCHEMA": os.environ["SCHEMA"], "KS_DATA_DIR": "/data",
  "KS_CLOUDBASE_ENV_ID": os.environ["ENV_ID"], "KS_ALLOW_TENANT_CREATE": "1",
  "LLM_PROXY_URL": os.environ["LLM_PROXY_URL"], "RAG_EMBEDDING_MODEL": "text-embedding-v3",
  "RAG_EMBEDDING_DIM": "1024", "RAG_EMBEDDING_BATCH_SIZE": "10", "BUILD_VERSION": os.environ["BUILD_VERSION"],
  "DATABASE_URL": os.environ["KSV_DATABASE_URL"], "PGSSL": os.environ.get("KSV_PGSSL",""),
  "LLM_PROXY_INTERNAL_TOKEN": os.environ["KSV_LLM_PROXY_INTERNAL_TOKEN"],
  "ECAN_JWT_SECRET": os.environ["KSV_ECAN_JWT_SECRET"],
})
base.update({"EnvParams": json.dumps(env), "Cpu": 0.5, "Mem": 1, "MinNum": int(os.environ["MIN_NUM"]),
             "MaxNum": 1, "Port": int(os.environ["PORT"]), "InitialDelaySeconds": 30})
print(json.dumps({"EnvId": os.environ["ENV_ID"], "ServerBaseConfig": base}))')" || { echo "cannot build service config"; exit 1; }
if tcb api tcbr UpdateCloudRunServerConfig --api-version 2022-02-17 --body "$BODY" >/tmp/ks_update_config.log 2>&1 \
   && ! grep -qi '"error"' /tmp/ks_update_config.log; then
  echo "config: EnvParams merged, 0.5 CPU / 1 GB, min $MIN_NUM max 1"
else
  echo "config update failed:"; grep -io '"message":"[^"]*"' /tmp/ks_update_config.log | head -3; exit 1
fi
unset BODY KSV_DATABASE_URL KSV_LLM_PROXY_INTERNAL_TOKEN KSV_ECAN_JWT_SECRET KSV_PGSSL

# ---- 4. deploy the build that picks up the config -----------------------------------------
run_deploy || { echo "deploy failed; see /tmp/ks_deploy_console.log"; exit 1; }
POST="$(online_versions)"
if [ -n "$PRE" ] && [ "$POST" = "$PRE" ]; then
  echo "deploy did not take effect: online version still $POST"; exit 1
fi
echo "online version: ${PRE:-none} -> $POST"

# ---- 5. stop versions that no longer serve (images kept for rollback) ----------------------
NEW="$(echo "$POST" | tr ',' '\n' | tail -1)"
OLD="$(echo "$PRE" | tr ',' '\n' | grep -v "^$NEW$" | grep -v '^$' | paste -sd, -)"
if [ -n "$OLD" ]; then
  tcb cloudrun version delete --service-name "$SERVICE" --version-names "$OLD" --is-delete-image false --force \
    >/dev/null 2>&1 && echo "stopped old versions: $OLD (images kept)"
fi

# ---- 6. health ------------------------------------------------------------------------------
URL="$(detail_json | python3 -c '
import json,re,sys
raw=sys.stdin.read()
m=re.findall(r"https://[a-z0-9.-]+\.run\.tcloudbase\.com", raw)
print(m[0] if m else "")')"
echo "url: ${URL:-(see console)}"
if [ -n "$URL" ]; then
  for i in 1 2 3 4 5 6; do
    out="$(curl -sS -m 10 "$URL/v1/health" 2>&1)" && echo "health: $out" && exit 0
    sleep 10
  done
  echo "health check failed: $out"; exit 1
fi
