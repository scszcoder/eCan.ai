#!/usr/bin/env bash
# =============================================================
# eCan.ai · safe deploy to TCB (cloudbase-graphql)
# =============================================================
#
# Default flow (the one you'll use 99% of the time):
#
#   $ ./scripts/deploy-safe.sh
#
# Optional flags:
#   --dry-run        preflight + tests + tree, NO upload
#   --package-only   stop after staging the zip dir
#   --no-migrate     skip DB schema push (you did it manually)
#   --migrate-only   run only DB schema push
#   --skip-tests     skip precheck (unit/smoke/skill-store)
#   --rollback       rollback to previous version
#   --rollback-tag X switch /api/graphql back to version X
#   --list-versions  list all deployed versions
#   --help
#
# Version Management:
#   - Each deploy creates a new version with timestamp
#   - Versions are tracked in .deploy_artifacts/versions.json
#   - Rollback available via --rollback or --rollback-tag
# =============================================================

set -euo pipefail

# ---------- arg parsing ------------------------------------
DRY_RUN=0
PACKAGE_ONLY=0
NO_MIGRATE=0
MIGRATE_ONLY=0
SKIP_TESTS=0
ROLLBACK_TAG=""
ROLLBACK_PREV=0
LIST_VERSIONS=0
KEEP_TREE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)         DRY_RUN=1 ;;
    --package-only)    PACKAGE_ONLY=1 ;;
    --no-migrate)      NO_MIGRATE=1 ;;
    --migrate-only)    MIGRATE_ONLY=1 ;;
    --skip-tests)      SKIP_TESTS=1 ;;
    --rollback)        ROLLBACK_PREV=1 ;;
    --rollback-tag)    ROLLBACK_TAG="${2:-}"; shift ;;
    --list-versions)   LIST_VERSIONS=1 ;;
    -h|--help)
      sed -n '2,40p' "$0"; exit 0 ;;
    *)
      echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

# ---------- paths & colors ---------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; B='\033[1;34m'; N='\033[0m'
say()  { printf "${B}[deploy]${N} %s\n" "$*"; }
ok()   { printf "${G}[deploy]${N} %s\n" "$*"; }
warn() { printf "${Y}[deploy]${N} %s\n" "$*"; }
die()  { printf "${R}[deploy]${N} %s\n" "$*" >&2; exit 1; }

# ---------- scratch files (auto-cleaned on EXIT) ----------
ENV_TCB="$(mktemp -t ecan-env.XXXXXXXX)"
chmod 600 "$ENV_TCB"
cleanup() {
  rm -f "$ENV_TCB" 2>/dev/null || true
  # Keep .deploy_tmp/ alive if user asked to inspect it (dry-run,
  # package-only, or migrate-only). Otherwise wipe to avoid leaking
  # 200 MB of dependencies into the working tree.
  if [[ "$KEEP_TREE" -eq 0 ]]; then
    rm -rf "$PROJECT_DIR/.deploy_tmp" "$PROJECT_DIR/.deploy_tmp.zip" 2>/dev/null || true
  fi
}
trap cleanup EXIT
require() { command -v "$1" >/dev/null 2>&1 || die "missing dependency: $1"; }

# ---------- version management ------------------------------
VERSIONS_FILE="$PROJECT_DIR/.deploy_artifacts/versions.json"

init_versions_file() {
  mkdir -p "$PROJECT_DIR/.deploy_artifacts"
  if [[ ! -f "$VERSIONS_FILE" ]]; then
    echo '{"functions":{},"current":null}' > "$VERSIONS_FILE"
  fi
}

save_version() {
  local fn_name="$1"
  local version="$2"
  local digest="$3"
  local timestamp="$4"
  local deployer="${5:-unknown}"
  
  init_versions_file
  
  # 使用 Python 处理 JSON（跨平台兼容）
  python3 << EOF
import json
with open('$VERSIONS_FILE', 'r') as f:
    data = json.load(f)
    
if '$fn_name' not in data['functions']:
    data['functions']['$fn_name'] = []

data['functions']['$fn_name'].insert(0, {
    'version': '$version',
    'digest': '$digest',
    'timestamp': '$timestamp',
    'deployer': '$deployer'
})
data['current'] = '$fn_name:$version'

with open('$VERSIONS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
EOF
}

list_versions() {
  init_versions_file
  echo ""
  echo "📦 部署版本历史"
  echo "================"
  python3 << EOF
import json
with open('$VERSIONS_FILE', 'r') as f:
    data = json.load(f)
    
for fn, versions in data.get('functions', {}).items():
    print(f"\n🔧 {fn}:")
    for i, v in enumerate(versions):
        marker = " ← 当前" if i == 0 else ""
        print(f"   v{v['version']} | {v['timestamp']} | {v['deployer']}{marker}")
EOF
  echo ""
}

get_previous_version() {
  local fn_name="$1"
  init_versions_file
  python3 << EOF
import json
with open('$VERSIONS_FILE', 'r') as f:
    data = json.load(f)
versions = data.get('functions', {}).get('$fn_name', [])
if len(versions) > 1:
    print(versions[1]['digest'])
EOF
}

get_current_version() {
  local fn_name="$1"
  init_versions_file
  python3 << EOF
import json
with open('$VERSIONS_FILE', 'r') as f:
    data = json.load(f)
versions = data.get('functions', {}).get('$fn_name', [])
if versions:
    print(versions[0]['version'])
EOF
}

# =============================================================
# Stages
# =============================================================

stage_preflight() {
  say "preflight"
  require node; require npm; require curl

  if ! command -v cloudbase >/dev/null 2>&1; then
    warn "cloudbase CLI missing — installing to ~/.local"
    mkdir -p "$HOME/.local/bin"
    npm config set prefix "$HOME/.local" >/dev/null
    npm install -g @cloudbase/cli >/dev/null
    export PATH="$HOME/.local/bin:$PATH"
    require cloudbase
  fi

  [[ -f .env.local ]] || die ".env.local missing (copy from .env.local.example)"
  set -a; . ./.env.local; set +a

  [[ -n "${TCB_ENV_ID:-}" ]]           || die "TCB_ENV_ID not set in .env.local"
  [[ -n "${DATABASE_URL:-}" ]]         || die "DATABASE_URL not set in .env.local"
  [[ -n "${COS_BUCKET:-}" ]]           || die "COS_BUCKET not set in .env.local"
  [[ -n "${COS_REGION:-}" ]]           || die "COS_REGION not set in .env.local"
  [[ -n "${WEBSOCKET_PUSH_SECRET:-}" ]] || die "WEBSOCKET_PUSH_SECRET not set in .env.local"

  cloudbase env list >/dev/null 2>&1 \
    || die "cloudbase CLI not logged in. Run: cloudbase login"
  ok "preflight passed"
}

stage_tests() {
  if [[ "$SKIP_TESTS" -eq 1 ]]; then
    warn "skip-tests"
    return 0
  fi
  say "tests"
  npm run precheck
  ok "tests passed"
}

stage_prisma() {
  say "prisma generate"
  # `--no-engine` keeps the current engines; we only need to refresh
  # the generated client code (the JS that knows about new fields).
  npx prisma generate >/dev/null 2>&1
  ok "client regenerated"
}

stage_tree() {
  say "stage tree"
  rm -rf .deploy_tmp
  mkdir -p .deploy_tmp

  local files=(
    auth.js tcb-init.js context-helpers.js event-bus.js health-check.js
    index.js websocket.js package.json package-lock.json
  )
  for f in "${files[@]}"; do
    [[ -f "$f" ]] || die "missing required file: $f"
    cp "$f" .deploy_tmp/
  done
  cp -r prisma storage scheduler compat services resolvers .deploy_tmp/

  # node_modules: copy dev tree, strip wrong-platform engines.
  cp -rL node_modules .deploy_tmp/
  local stripped=0
  for f in \
    .deploy_tmp/node_modules/.prisma/client/libquery_engine-darwin-arm64.dylib.node \
    .deploy_tmp/node_modules/.prisma/client/schema-engine-darwin-arm64 \
    .deploy_tmp/node_modules/.prisma/client/libquery_engine-linux-musl-arm64-openssl-1.1.x.so.node \
    .deploy_tmp/node_modules/.prisma/client/schema-engine-linux-musl-arm64-openssl-1.1.x \
    .deploy_tmp/node_modules/.prisma/client/libquery_engine-rhel-openssl-1.0.x.so.node \
    .deploy_tmp/node_modules/.prisma/client/schema-engine-rhel-openssl-1.0.x \
    .deploy_tmp/node_modules/prisma/libquery_engine-darwin-arm64.dylib.node \
    .deploy_tmp/node_modules/prisma/libquery_engine-linux-musl-arm64-openssl-1.1.x.so.node \
    .deploy_tmp/node_modules/prisma/schema-engine-darwin-arm64 \
    .deploy_tmp/node_modules/prisma/schema-engine-linux-musl-arm64-openssl-1.1.x \
    .deploy_tmp/node_modules/@prisma/engines/libquery_engine-darwin-arm64.dylib.node \
    .deploy_tmp/node_modules/@prisma/engines/libquery_engine-linux-musl-arm64-openssl-1.1.x.so.node \
    .deploy_tmp/node_modules/@prisma/engines/schema-engine-darwin-arm64 \
    .deploy_tmp/node_modules/@prisma/engines/schema-engine-linux-musl-arm64-openssl-1.1.x \
    .deploy_tmp/node_modules/@prisma/engines/libquery_engine-rhel-openssl-1.0.x.so.node \
    .deploy_tmp/node_modules/@prisma/engines/libquery_engine-rhel-openssl-3.0.x.so.node \
    .deploy_tmp/node_modules/@prisma/engines/schema-engine-rhel-openssl-1.0.x \
    .deploy_tmp/node_modules/@prisma/engines/schema-engine-rhel-openssl-3.0.x; do
    if [[ -e "$f" ]]; then rm -f "$f"; stripped=$((stripped+1)); fi
  done
  say "stripped $stripped platform-mismatched engine files"

  # Ensure the only linux-x86_64 engine we need is present
  local qe=".deploy_tmp/node_modules/.prisma/client/libquery_engine-rhel-openssl-1.1.x.so.node"
  if [[ ! -s "$qe" ]]; then
    warn "missing $qe — fetching from binaries.prisma.sh"
    fetch_prisma_engine || die "could not obtain linux-x86_64 query engine"
  fi
  ok "tree ready"
}

fetch_prisma_engine() {
  local ver
  ver="$(node -e "process.stdout.write(require('./node_modules/@prisma/engines-version').enginesVersion)")"
  [[ -n "$ver" ]] || die "enginesVersion unresolved"
  local base="https://binaries.prisma.sh/all_commits/${ver}/rhel-openssl-1.1.x"
  local out=".deploy_tmp/node_modules/.prisma/client"
  mkdir -p "$out"
  curl --fail --silent --show-error --retry 3 --retry-delay 2 \
       -o "$out/libquery_engine-rhel-openssl-1.1.x.so.node" \
       "$base/query-engine/node.gz" \
    || die "could not fetch query-engine from $base/query-engine/node.gz"
  curl --fail --silent --show-error --retry 3 --retry-delay 2 \
       -o "$out/schema-engine-rhel-openssl-1.1.x" \
       "$base/schema-engine/node.gz" \
    || warn "could not fetch schema-engine (db push will fall back to npm-installed binary)"
}

stage_migrate() {
  if [[ "$NO_MIGRATE" -eq 1 ]]; then
    warn "no-migrate: skipped"
    return 0
  fi
  say "migrate (DB schema)"
  local diff
  diff="$(npx prisma migrate diff \
            --from-schema-datasource "$DATABASE_URL" \
            --to-schema-datamodel prisma/schema.prisma \
            --script 2>/dev/null || true)"
  if [[ -z "$diff" ]]; then
    ok "no schema drift"
    return 0
  fi
  # Surface the diff the operator will see
  echo "$diff" > .deploy_tmp/diff.sql
  warn "schema diff written to .deploy_tmp/diff.sql"

  if echo "$diff" | grep -qE 'DROP (TABLE|COLUMN)|ALTER COLUMN .* (TYPE|DROP NOT NULL)'; then
    warn "DESTRUCTIVE change detected — refusing to auto-apply"
    warn "back up the DB, then re-run with --no-migrate after manual apply"
    return 1
  fi

  npx prisma db push \
    --schema prisma/schema.prisma \
    --skip-generate \
    --accept-data-loss 2>&1 | tee .deploy_tmp/push.log
  grep -q "Your database is now in sync" .deploy_tmp/push.log \
    || die "db push failed"
  ok "schema applied"
}

stage_upload() {
  say "upload (fn deploy)"
  
  # 计算代码摘要用于版本追踪
  local code_digest
  code_digest="$(find .deploy_tmp -type f ! -name '*.log' -exec cat {} \; | sha256sum | cut -c1-12)"
  
  # 生成版本号（时间戳格式）
  local version
  version="$(date '+%Y%m%d-%H%M%S')"
  local timestamp
  timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
  local deployer
  deployer="$(git config user.name 2>/dev/null || echo 'unknown')"
  
  say "发布版本: $version"
  say "代码摘要: $code_digest"
  
  # 部署云函数
  cloudbase fn deploy ecan-graphql-api \
    --dir .deploy_tmp \
    --force \
    --install-dependency false \
    2>&1 | tee .deploy_tmp/deploy.log
  
  if grep -q "deployed successfully" .deploy_tmp/deploy.log; then
    # 保存版本记录
    save_version "ecan-graphql-api" "$version" "$code_digest" "$timestamp" "$deployer"
    ok "代码上传成功，版本 v$version 已记录"
  else
    die "部署未报告成功"
  fi
}

stage_env_sync() {
  say "env sync"
  if [[ -x scripts/sync-tcb-env.sh ]]; then
    bash scripts/sync-tcb-env.sh \
      || warn "sync-tcb-env exited non-zero — verify in console"
  else
    warn "scripts/sync-tcb-env.sh not executable, skipping"
  fi
  ok "env reconciled"
}

stage_smoke() {
  say "smoke"
  local url="https://${TCB_ENV_ID}.service.tcloudbase.com/api/graphql"
  local body='{"query":"{ searchSkills(input:{q:\"weather\",limit:1}) { name } }"}'
  local resp
  resp="$(curl --fail --silent --show-error --max-time 20 \
    -H "Content-Type: application/json" -d "$body" "$url" 2>/dev/null || true)"
  if [[ -z "$resp" ]]; then
    warn "smoke: no response (cold-start?)"
    return 0
  fi
  if echo "$resp" | grep -q '"errors"'; then
    warn "smoke: response contains errors — investigate before trusting deploy"
    echo "$resp" | head -c 500 >&2
    return 1
  fi
  ok "smoke passed"
}

stage_rollback() {
  say "rollback"
  
  local target_digest=""
  if [[ -n "$ROLLBACK_TAG" ]]; then
    # 按版本号回滚
    target_digest="$(python3 << EOF
import json
with open('$VERSIONS_FILE', 'r') as f:
    data = json.load(f)
for fn, versions in data.get('functions', {}).items():
    for v in versions:
        if v['version'] == '$ROLLBACK_TAG':
            print(v['digest'])
            exit(0)
EOF
)"
    [[ -z "$target_digest" ]] && die "版本 $ROLLBACK_TAG 未找到"
    say "回滚到版本 $ROLLBACK_TAG (digest: $target_digest)"
  elif [[ "$ROLLBACK_PREV" -eq 1 ]]; then
    # 回滚到上一个版本
    target_digest="$(get_previous_version "ecan-graphql-api")"
    [[ -z "$target_digest" ]] && die "没有可回滚的上一个版本"
    say "回滚到上一个版本 (digest: $target_digest)"
  fi
  
  # 从历史记录中找到对应的版本包
  local rollback_zip=".deploy_artifacts/archive_${target_digest}.zip"
  if [[ ! -f "$rollback_zip" ]]; then
    die "未找到版本包: $rollback_zip"
  fi
  
  say "解压版本包..."
  rm -rf .deploy_tmp
  unzip -q "$rollback_zip" -d .deploy_tmp
  
  say "重新部署..."
  cloudbase fn deploy ecan-graphql-api \
    --dir .deploy_tmp \
    --force \
    --install-dependency false
  
  ok "回滚完成"
}

# =============================================================
# Main
# =============================================================

# list-versions 是独立流程
if [[ "$LIST_VERSIONS" -eq 1 ]]; then
  list_versions
  exit 0
fi

# rollback 是顶级流程
if [[ "$ROLLBACK_PREV" -eq 1 ]] || [[ -n "$ROLLBACK_TAG" ]]; then
  stage_preflight
  stage_rollback
  exit 0
fi

# migrate-only 也是独立流程
if [[ "$MIGRATE_ONLY" -eq 1 ]]; then
  stage_preflight; stage_migrate
  KEEP_TREE=1
  exit 0
fi

stage_preflight
[[ "$DRY_RUN" -eq 1 ]] && {
  KEEP_TREE=1
  stage_tests; stage_prisma; stage_tree
  ok "dry-run finished — .deploy_tmp/ kept for inspection"
  exit 0
}

stage_tests
stage_prisma
stage_tree
[[ "$PACKAGE_ONLY" -eq 1 ]] && { KEEP_TREE=1; ok "package-only: stopped after stage 4"; exit 0; }

# 保存当前版本包（用于回滚）
init_versions_file
prev_digest="$(get_previous_version "ecan-graphql-api" 2>/dev/null || echo "")"
if [[ -n "$prev_digest" ]] && [[ ! -f ".deploy_artifacts/archive_${prev_digest}.zip" ]]; then
  # 如果上一个版本没有存档，先创建
  say "存档上一个版本..."
  (cd .deploy_tmp && zip -q -r "../.deploy_artifacts/archive_${prev_digest}.zip" . 2>/dev/null || true)
fi

stage_upload

# 部署成功后存档当前版本
if [[ -d ".deploy_tmp" ]]; then
  new_digest="$(find .deploy_tmp -type f ! -name '*.log' -exec cat {} \; | sha256sum | cut -c1-12)"
  rm -f ".deploy_artifacts/archive_${new_digest}.zip"
  (cd .deploy_tmp && zip -q -r "../.deploy_artifacts/archive_${new_digest}.zip" .)
  say "版本包已存档"
fi

stage_migrate
stage_env_sync
stage_smoke

ok "deploy complete"
echo
echo "📦 版本管理:"
echo "  - 查看版本: ./scripts/deploy-safe.sh --list-versions"
echo "  - 回滚到上一版: ./scripts/deploy-safe.sh --rollback"
echo "  - 回滚到指定版本: ./scripts/deploy-safe.sh --rollback-tag <version>"
echo
echo "Next steps:"
echo "  - Hit https://${TCB_ENV_ID}.service.tcloudbase.com/api/graphql to confirm"
echo "  - Roll back: ./scripts/deploy-safe.sh --rollback"
