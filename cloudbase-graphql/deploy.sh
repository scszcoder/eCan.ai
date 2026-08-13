#!/bin/bash
# ============================================================
# eCan.ai TCB 云函数部署 — 兼容入口
# ============================================================
#
# ⚠️  旧版 deploy.sh 已废弃
#
# 老脚本会把源码拷贝到 cloudbase-graphql/functions/ecan-graphql-api/
# 再 `cloudbase fn deploy --dir functions/ecan-graphql-api`，导致：
#   1. 源代码被复制为 staging dir, 任何 bug fix 要改两份
#   2. .gitignore 必须排除整个函数目录, 容易踩坑
#   3. 上传包含 node_modules, 经常踩 TCB COS 60s 上传超时
#
# 新脚本 scripts/deploy-api.sh 用 .deploy_tmp/ 临时目录,
# 在上传前自动剥掉 darwin/arm64 prisma engine、自动 prisma generate、
# 自动 db push additive-only schema, 并提供回滚快照。
#
# 此入口只做兼容转发，所有参数透传给 deploy-api.sh：
#
#   ./deploy.sh                → 完整 10 步部署
#   ./deploy.sh --dry-run      → preflight + tests + stage, 不上传
#   ./deploy.sh --skip-tests   → 跳过 precheck
#   ./deploy.sh --no-migrate   → 跳过 db push
#   ./deploy.sh --list-versions
#   ./deploy.sh --rollback
#
# 新代码部署请走：npm run deploy:safe 或 ./scripts/deploy-api.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/scripts/deploy-api.sh"

if [[ ! -x "$TARGET" ]]; then
  echo "❌ 找不到 $TARGET" >&2
  echo "   提示: chmod +x scripts/deploy-api.sh" >&2
  exit 1
fi

echo "ℹ️  deploy.sh 是兼容入口; 转发到 scripts/deploy-api.sh (参数透传)" >&2
exec "$TARGET" "$@"