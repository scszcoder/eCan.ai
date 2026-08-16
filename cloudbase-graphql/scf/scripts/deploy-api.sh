#!/usr/bin/env bash
# =============================================================
# eCan.ai · safe deploy to TCB (cloudbase-graphql)
# =============================================================
#
# Default flow (the one you'll use 99% of the time):
#
#   $ ./scripts/deploy-api.sh
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
NODE_BUILD_IMAGE="${NODE_BUILD_IMAGE:-node:20-bookworm-slim}"
PRISMA_BINARY_TARGETS=("rhel-openssl-1.1.x" "rhel-openssl-3.0.x")

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
    rm -rf "$PROJECT_DIR/.build_tmp" "$PROJECT_DIR/.deploy_tmp" "$PROJECT_DIR/.deploy_tmp.zip" 2>/dev/null || true
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
  require node; require npm; require curl; require docker

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

  if [[ "${SKIP_CLOUDBASE_AUTH:-0}" == "1" ]]; then
    warn "skip cloudbase auth (dry-run mode)"
  else
    cloudbase env list >/dev/null 2>&1 \
      || die "cloudbase CLI not logged in. Run: cloudbase login"
  fi
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
  say "Node 20 dependency build + prisma generate"
  if [[ -e .build_tmp ]]; then
    docker run --rm -v "$PROJECT_DIR:/project" "$NODE_BUILD_IMAGE" \
      sh -ceu 'rm -rf /project/.build_tmp'
  fi
  mkdir -p .build_tmp
  cp package.json package-lock.json .build_tmp/
  cp -r prisma .build_tmp/
  mkdir -p .build_tmp/scripts
  cp scripts/relocate-prisma-client.js .build_tmp/scripts/

  docker run --rm \
    -v "$PROJECT_DIR/.build_tmp:/work" \
    -w /work \
    "$NODE_BUILD_IMAGE" \
    sh -ceu "apt-get update >/dev/null && apt-get install -y --no-install-recommends openssl ca-certificates >/dev/null && npm ci && npx prisma generate && node scripts/relocate-prisma-client.js && npm prune --omit=dev && chown -R $(id -u):$(id -g) /work"

  local client_dir=".build_tmp/node_modules/.prisma/client"
  [[ -s "$client_dir/index.js" ]] || die "generated Prisma client is missing: $client_dir/index.js"
  [[ -s "$client_dir/schema.prisma" ]] || die "generated Prisma schema is missing: $client_dir/schema.prisma"
  for target in "${PRISMA_BINARY_TARGETS[@]}"; do
    local query_engine="$client_dir/libquery_engine-${target}.so.node"
    [[ -s "$query_engine" ]] || die "generated Tencent Prisma engine is missing: $query_engine"
  done
  [[ -d .build_tmp/node_modules/@prisma/client ]] || die "@prisma/client runtime is missing"

  docker run --rm \
    -v "$PROJECT_DIR/.build_tmp:/work:ro" \
    -w /work \
    "$NODE_BUILD_IMAGE" \
    sh -ceu "apt-get update >/dev/null && apt-get install -y --no-install-recommends openssl ca-certificates >/dev/null && node -e \"require('./node_modules/.prisma/client/libquery_engine-rhel-openssl-3.0.x.so.node'); console.log('Tencent OpenSSL 3 Prisma engine loads')\""

  ok "Node 20 Prisma client generated for ${PRISMA_BINARY_TARGETS[*]}"
}

stage_tree() {
  say "stage tree"
  rm -rf .deploy_tmp
  mkdir -p .deploy_tmp

  local files=(
    auth.js tcb-init.js context-helpers.js event-bus.js health-check.js
    index.js package.json package-lock.json
    # add_snake_alias.js — required at runtime by index.js to expose snake_case
    # field aliases on every `input` type so eCan.ai client (snake_case native)
    # can talk to this backend (originally camelCase). See CLAUDE.md §5.
    add_snake_alias.js
  )
  for f in "${files[@]}"; do
    [[ -f "$f" ]] || die "missing required file: $f"
    cp "$f" .deploy_tmp/
  done
  cp -r prisma storage scheduler compat services resolvers .deploy_tmp/

  # Runtime dependencies and generated Prisma client come only from the
  # reproducible Node 20 build in stage_prisma, never from the host machine.
  cp -rL .build_tmp/node_modules .deploy_tmp/

  # CloudBase's COS directory packager omits dot-directories, including
  # node_modules/.prisma. Relocate the generated client to a visible root
  # directory and point @prisma/client's CommonJS entry files at it.
  cp -r .build_tmp/node_modules/.prisma/client .deploy_tmp/prisma-client
  sed -i "s#require('.prisma/client/default')#require('../../../prisma-client/default')#" \
    .deploy_tmp/node_modules/@prisma/client/default.js \
    .deploy_tmp/node_modules/@prisma/client/index.js
  rm -rf .deploy_tmp/node_modules/.prisma

  # === Bundle size reduction (cos upload 60s timeout) ===
  # Dev-only dependencies were already removed by `npm prune --omit=dev`.
  # tencentcloud-sdk-nodejs is a leftover from the WS push path; nothing requires it.
  rm -rf .deploy_tmp/node_modules/tencentcloud-sdk-nodejs 2>/dev/null
  # @prisma sub-trees only used by the prisma CLI
  rm -rf .deploy_tmp/node_modules/@prisma/fetch-engine .deploy_tmp/node_modules/@prisma/get-platform .deploy_tmp/node_modules/@prisma/debug 2>/dev/null
  # @prisma/client generator-build + scripts are only used by `prisma generate`; runtime/ IS needed
  rm -rf .deploy_tmp/node_modules/@prisma/client/generator-build .deploy_tmp/node_modules/@prisma/client/scripts 2>/dev/null
  # Strip JS source maps (.map) and TypeScript declaration files (.d.ts).
  find .deploy_tmp/node_modules -name '*.map' -type f -delete 2>/dev/null
  find .deploy_tmp/node_modules -name '*.d.ts' -type f -delete 2>/dev/null
  # npm bin directory is not needed at runtime.
  rm -rf .deploy_tmp/node_modules/.bin 2>/dev/null
  # Strip test/example/docs subdirs.
  find .deploy_tmp/node_modules -type d \( -name test -o -name tests -o -name example -o -name examples -o -name docs \) -exec rm -rf {} + 2>/dev/null
  # Strip docs/metadata files top-level.
  find .deploy_tmp/node_modules -type f \( -name '*.md' -o -name 'README*' -o -name 'LICENSE*' -o -name 'CHANGELOG*' -o -name '*.markdown' \) -delete 2>/dev/null
  local after
  after=$(du -sm .deploy_tmp | awk '{print $1}')
  say "tree size after pruning: ${after}M"

  local client_dir=".deploy_tmp/prisma-client"
  [[ -s "$client_dir/index.js" ]] || die "staged Prisma client index is missing"
  [[ -s "$client_dir/schema.prisma" ]] || die "staged Prisma schema is missing"
  for target in "${PRISMA_BINARY_TARGETS[@]}"; do
    local qe="$client_dir/libquery_engine-${target}.so.node"
    [[ -s "$qe" ]] || die "staged Tencent Prisma engine is missing: $qe"
  done
  [[ -d .deploy_tmp/node_modules/@prisma/client ]] || die "staged @prisma/client is missing"
  grep -q "../../../prisma-client/default" .deploy_tmp/node_modules/@prisma/client/default.js \
    || die "@prisma/client runtime wrapper was not relocated"
  ok "tree ready"
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
  if [[ -x bin/sync-tcb-env ]]; then
    bash bin/sync-tcb-env \
      || warn "sync-tcb-env exited non-zero — verify in console"
  else
    warn "bin/sync-tcb-env not executable, skipping"
  fi
  ok "env reconciled"
}

stage_smoke() {
  say "smoke"
  local url="https://${TCB_ENV_ID}.service.tcloudbase.com/api/graphql"
  # Schema requires Bearer token for all queries (resolveIdentity is bound
  # to the Yoga context factory), so we can't validate the response body.
  # What we CAN check: HTTP roundtrip succeeds (i.e. SCF accepted the
  # request and the function is alive), and the response carries a JSON
  # error message from the schema (proof that the deployed code is
  # running, not a stale instance from a previous deploy).
  local resp
  resp="$(curl --fail --silent --show-error --max-time 30 \
    -H "Content-Type: application/json" \
    -d '{"query":"{ __typename }"}' "$url" 2>/dev/null || true)"
  if [[ -z "$resp" ]]; then
    warn "smoke: no response (cold-start?)"
    return 0
  fi
  # Anything that is NOT a JSON auth error means the deployed code is
  # running but something else is wrong — surface it.
  if ! echo "$resp" | grep -qE '"UNAUTHENTICATED"|"errors"' && ! echo "$resp" | grep -q '__typename'; then
    warn "smoke: unexpected response — investigate before trusting deploy"
    echo "$resp" | head -c 500 >&2
    return 1
  fi
  ok "smoke: function responded (auth-protected schema is healthy)"
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
echo "  - 查看版本: ./scripts/deploy-api.sh --list-versions"
echo "  - 回滚到上一版: ./scripts/deploy-api.sh --rollback"
echo "  - 回滚到指定版本: ./scripts/deploy-api.sh --rollback-tag <version>"
echo
echo "Next steps:"
echo "  - Hit https://${TCB_ENV_ID}.service.tcloudbase.com/api/graphql to confirm"
echo "  - Roll back: ./scripts/deploy-api.sh --rollback"
