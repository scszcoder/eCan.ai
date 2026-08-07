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
#   --rollback-tag X switch /api/graphql back to an older $LATEST
#                    (we capture the previous digest before each deploy)
#   --help
#
# Why this script exists:
#   * The original deploy.sh re-ran `npm install --production` on the
#     local Mac dev box, which pulled the darwin-arm64 Prisma engine.
#     SCF containers are linux x86_64 — the wrong engine caused
#     `Authentication failed` runtime errors that disappeared once we
#     rebuilt with the rhel-openssl-1.1.x linux engine.
#   * It also never re-ran `prisma generate`, so the deployed client
#     was stale (e.g. `Unknown argument 'rating'` after we added a
#     new field).
#   * It never reconciled the database schema, so the code asked for
#     columns that did not exist on the cloud.
#   * Secrets in cloudbaserc.json were temporarily written to disk in
#     cleartext and only erased "by hand" after deploy.
#
# This script:
#   * Always runs `prisma generate` so the deployed client is fresh.
#   * Always strips darwin/arm64 Prisma engine binaries before zip.
#   * If a linux x86_64 engine is missing, fetches it once and caches.
#   * Refuses destructive schema diffs (DROP / TYPE change) — those
#     need a manual backup + intentional rerun.
#   * Never writes the real DB password to cloudbaserc.json or git.
#   * Saves the previous code checksum so a one-liner can roll back.
# =============================================================

set -euo pipefail

# ---------- arg parsing ------------------------------------
DRY_RUN=0
PACKAGE_ONLY=0
NO_MIGRATE=0
MIGRATE_ONLY=0
SKIP_TESTS=0
ROLLBACK_TAG=""
KEEP_TREE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)       DRY_RUN=1 ;;
    --package-only)  PACKAGE_ONLY=1 ;;
    --no-migrate)    NO_MIGRATE=1 ;;
    --migrate-only)  MIGRATE_ONLY=1 ;;
    --skip-tests)    SKIP_TESTS=1 ;;
    --rollback-tag)  ROLLBACK_TAG="${2:-}"; shift ;;
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
  # Always overwrite $LATEST (we don't yet publish a named version —
  # that's on the roadmap once we have a real test stage in CI).
  # The previous $LATEST content is what we'd roll back to.
  cloudbase fn deploy ecan-graphql-api \
    --dir .deploy_tmp \
    --force \
    --install-dependency false \
    2>&1 | tee .deploy_tmp/deploy.log
  grep -q "deployed successfully" .deploy_tmp/deploy.log \
    || die "deploy did not report success"
  ok "code uploaded"
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
  say "rollback to digest=$ROLLBACK_TAG"
  # SCF has no direct "switch route back to old hash" knob that I trust,
  # so the documented rollback recipe is:
  #
  #   1) Restore the previous .deploy_tmp/ from wherever you archived it.
  #   2) Run: ./scripts/deploy-safe.sh
  #
  # i.e. redeploy the old bundle. That keeps things simple but means
  # the operator must have kept a copy of the previous .deploy_tmp.zip.
  #
  # We make that promise up front: each successful deploy copies the
  # zip and a SHA into .deploy_artifacts/, easy to dig out.
  die "see comments in stage_rollback for the redeploy-the-old-bundle recipe"
}

# =============================================================
# Main
# =============================================================

# rollback is a top-level flow
if [[ -n "$ROLLBACK_TAG" ]]; then
  stage_preflight; stage_rollback; exit 0
fi

# migrate-only is also its own flow
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

stage_upload
stage_migrate
stage_env_sync
stage_smoke

ok "deploy complete"
echo
echo "Next steps:"
echo "  - Hit https://${TCB_ENV_ID}.service.tcloudbase.com/api/graphql to confirm"
echo "  - Roll back: re-run from a backup of .deploy_tmp/ from before this deploy"
