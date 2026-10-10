#!/usr/bin/env bash
# Deploy the Knowledge Service as a CloudBase HTTP cloud function. Runs ON THE
# CVM (where tcb is logged in), in a folder holding this script, scf_bootstrap,
# requirements-scf.txt and dist/knowledge (from ../tcb/make_context.py).
#
#   bash deploy.sh ecan-knowledge-test     # schema knowledge_test, path /api/knowledge-test
#   bash deploy.sh ecan-knowledge          # schema knowledge,      path /api/knowledge
#
# Why a function and not 云托管: 云托管 containers cannot reach the CloudBase
# PostgreSQL (connect timeout, same VPC/subnet), while functions can.
#
# Same rules as eCan_lambda's skill_agent publish.sh / set-env.sh:
# `fn deploy --force` resets the function's environment AND VpcConfig, so both
# are restored right after every deploy, copied function-to-function from
# llm_proxy inside the cloud (no secret is typed, printed or stored), and the
# result is verified rather than trusted.
set -Eeuo pipefail
export PATH=$HOME/.local/bin:$PATH

FN="${1:-}"
case "$FN" in
  ecan-knowledge-test) SCHEMA=knowledge_test; ROUTE=/api/knowledge-test ;;
  ecan-knowledge)      SCHEMA=knowledge;      ROUTE=/api/knowledge ;;
  *) echo "usage: bash deploy.sh ecan-knowledge-test|ecan-knowledge"; exit 2 ;;
esac
NS=sccb0-d0gc5398xf028be6a
SRC_FN=llm_proxy
HERE="$(cd "$(dirname "$0")" && pwd)"
STAGE="$HERE/stage-$FN"
BUILD_VERSION="ks-$(date -u +%Y%m%d%H%M%S)"

[ -d "$HERE/dist/knowledge/ks" ] || { echo "missing dist/knowledge/ks"; exit 1; }

# ---- 1. stage code + vendored dependencies (Linux wheels for Python 3.10) ------------
rm -rf "$STAGE"; mkdir -p "$STAGE/vendor"
cp -r "$HERE/dist/knowledge" "$STAGE/knowledge"
install -m 0755 "$HERE/scf_bootstrap" "$STAGE/scf_bootstrap"
python3 -m pip install -q --target "$STAGE/vendor" --python-version 3.10 --platform manylinux2014_x86_64 \
  --only-binary=:all: --implementation cp -i https://mirrors.cloud.tencent.com/pypi/simple \
  -r "$HERE/requirements-scf.txt" 2>&1 | grep -v '^WARNING' || true
find "$STAGE" -name '__pycache__' -prune -exec rm -rf {} + ; find "$STAGE/vendor" -path '*/tests/*' -delete 2>/dev/null || true
echo "staged: $(du -sh "$STAGE" | cut -f1)"

cat > "$STAGE/cloudbaserc.json" <<JSON
{
  "version": "2.0",
  "envId": "$NS",
  "functionRoot": ".",
  "functions": [{
    "name": "$FN",
    "runtime": "Python3.10",
    "timeout": 300,
    "memorySize": 1024,
    "installDependency": false
  }]
}
JSON

# ---- 2. deploy (HTTP function, uploaded through COS: the package is large) ----------
cd "$STAGE"
tcb fn deploy "$FN" --httpFn --dir "$STAGE" --force --deployMode cos --path "$ROUTE" --install-dependency false 2>&1 \
  | grep -vE 'Loading|Try the tcb ai' | tail -8
cd "$HERE"

# ---- 3. restore env + VpcConfig (copied from llm_proxy, verified) ----------------------
FN="$FN" NS="$NS" SRC="$SRC_FN" SCHEMA="$SCHEMA" ROUTE="$ROUTE" BUILD_VERSION="$BUILD_VERSION" python3 - <<'PY'
import json, os, subprocess, sys
fn, ns, src = os.environ["FN"], os.environ["NS"], os.environ["SRC"]
COPY = ["DATABASE_URL", "PGSSL", "LLM_PROXY_INTERNAL_TOKEN", "ECAN_JWT_SECRET"]

def tcb(action, body):
    r = subprocess.run(["tcb", "api", "scf", action, "--json", "--body", json.dumps(body)], capture_output=True, text=True)
    out = r.stdout + r.stderr
    i = out.find("{")
    if r.returncode != 0 or i < 0:
        sys.exit(f"{action} failed: {out[-300:]}")
    return json.loads(out[i:])

def config_of(name):
    d = tcb("GetFunction", {"FunctionName": name, "Namespace": ns})["data"]
    return {v["Key"]: v["Value"] for v in (d.get("Environment") or {}).get("Variables", [])}, d.get("VpcConfig") or {}

source, vpc = config_of(src)
missing = [k for k in COPY if not source.get(k) and k != "PGSSL"]
if missing:
    sys.exit(f"{src} has no value for {missing}")
if not vpc.get("VpcId") or not vpc.get("SubnetId"):
    sys.exit(f"{src} has no VpcConfig; the database would be unreachable")
target, _ = config_of(fn)
target.update({k: source[k] for k in COPY if source.get(k) is not None})
target.update({
    "KS_PLANE": "public", "KS_DB_SCHEMA": os.environ["SCHEMA"], "KS_PATH_PREFIX": os.environ["ROUTE"],
    "KS_CLOUDBASE_ENV_ID": ns, "KS_ALLOW_TENANT_CREATE": "1", "KS_INLINE_JOBS": "1",
    "LLM_PROXY_URL": f"https://{ns}.service.tcloudbase.com/api/llm-proxy",
    "RAG_EMBEDDING_MODEL": "text-embedding-v3", "RAG_EMBEDDING_DIM": "1024", "RAG_EMBEDDING_BATCH_SIZE": "10",
    "BUILD_VERSION": os.environ["BUILD_VERSION"],
})
tcb("UpdateFunctionConfiguration", {"FunctionName": fn, "Namespace": ns, "VpcConfig": vpc,
                                     "Environment": {"Variables": [{"Key": k, "Value": v} for k, v in target.items()]}})
after, after_vpc = config_of(fn)
bad = [k for k in COPY if source.get(k) is not None and after.get(k) != source[k]]
if after_vpc.get("SubnetId") != vpc["SubnetId"]:
    bad.append("VpcConfig")
if bad:
    sys.exit(f"NOT APPLIED: {bad}")
print(f"env: {len(after)} vars set by name {sorted(after)}; VpcConfig {vpc['VpcId']}/{vpc['SubnetId']} (verified)")
PY

# ---- 4. health ---------------------------------------------------------------------------
URL="https://${NS}.service.tcloudbase.com${ROUTE}"
echo "url: $URL"
for i in 1 2 3 4 5 6 7 8; do
  out="$(curl -sS -m 40 "$URL/v1/health" 2>&1)" || true
  case "$out" in *'"status":"ok"'*) echo "health: $out"; exit 0 ;; esac
  echo "health (try $i): ${out:0:300}"; sleep 15
done
exit 1
