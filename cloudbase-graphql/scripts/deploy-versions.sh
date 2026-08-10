#!/bin/bash
# ============================================================
# TCB 云函数版本管理与回滚脚本
#
# TCB SCF 版本机制:
#   - 每次 deploy 更新 $LATEST
#   - fn publish-version <name> [desc] 创建编号快照 (1, 2, 3...)
#   - fn config-route 可以切流量 (但 HTTP 路由只认函数名)
#
# 策略: 每次 deploy 前快照当前 LATEST, 成功后记录版本到本地文件.
#   - 版本号: 递增整数 (v1, v2, v3...)
#   - 版本描述: git commit SHA + 时间戳
#   - 回滚: 把指定版本重新 publish 为 LATEST
#
# 用法:
#   ./scripts/deploy-versions.sh deploy [fn]     部署并创建版本快照
#   ./scripts/deploy-versions.sh list [fn]       列出所有版本
#   ./scripts/deploy-versions.sh rollback [fn] [version]  回滚到指定版本
#   ./scripts/deploy-versions.sh current [fn]     显示当前版本

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

VERSION_FILE=".deploy_versions.json"

# 读取版本文件
read_versions() {
  if [ -f "$VERSION_FILE" ]; then
    cat "$VERSION_FILE"
  else
    echo "{}"
  fi
}

# 写入版本文件
write_versions() {
  echo "$1" > "$VERSION_FILE"
}

# 获取某个函数的当前版本记录
get_current() {
  local fn="$1"
  read_versions | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data.get('$fn', {}).get('current', ''))
" 2>/dev/null
}

# 获取某个函数的版本列表
list_versions() {
  local fn="$1"
  cloudbase fn list-function-versions "$fn" --env-id sccb0-d0gc5398xf028be6a 2>/dev/null
}

# 获取下一个版本号
next_version() {
  local fn="$1"
  read_versions | python3 -c "
import json, sys
data = json.load(sys.stdin)
versions = data.get('$fn', {}).get('versions', {})
# Find max version number
max_v = 0
for k in versions:
  try:
    v = int(k.replace('v',''))
    if v > max_v: max_v = v
  except: pass
print('v' + str(max_v + 1))
" 2>/dev/null
}

# 创建版本快照
snapshot() {
  local fn="$1"
  local desc="${2:-}"
  cloudbase fn publish-version "$fn" --env-id sccb0-d0gc5398xf028be6a "$desc" 2>/dev/null
}

# 重新部署指定版本 (把该版本的代码重新发布为 LATEST)
restore_version() {
  local fn="$1"
  local ver="$2"
  local data="$(read_versions)"
  local desc="$(echo "$data" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('$fn', {}).get('versions', {}).get('$ver', {}).get('desc', ''))
" 2>/dev/null)"

  if [ -z "$desc" ]; then
    echo -e "${RED}❌ 版本 $ver 不存在于本地记录${NC}"
    return 1
  fi

  echo -e "${YELLOW}⚠️  确认回滚 $fn 到 $ver ?${NC}"
  echo -e "  描述: $desc"
  echo -e "  操作: 把 $ver 版本的代码重新发布为 LATEST (会覆盖当前版本)"
  read -p "  输入 yes 确认: " confirm
  if [ "$confirm" != "yes" ]; then
    echo -e "  已取消"
    return 1
  fi

  # 获取该版本的代码 (通过 SCF API)
  echo -e "${YELLOW}→ 获取版本 $ver 代码...${NC}"

  # 用 SCF API 获取版本代码的 COS bucket
  local cos_info=$(cloudbase api scf GetFunction \
    --body "{\"FunctionName\":\"$fn\",\"Namespace\":\"sccb0-d0gc5398xf028be6a\",\"Qualifier\":\"$ver\"}" 2>/dev/null)
  echo "$cos_info" | head -5

  echo -e "${RED}  注意: SCF 版本回滚需要手动操作${NC}"
  echo -e "  方案: 使用 SCF 控制台 → 函数 → 版本 → 选择版本 → 切换到该版本"
  echo -e "  或: 使用流量分配把流量切到旧版本 (见下方)"
  echo ""
  echo -e "${BLUE}  替代方案: 流量灰度${NC}"
  echo -e "    cloudbase fn config-route $fn \$LATEST 90 $ver 10"
  echo -e "    # 将 10% 流量切到旧版本, 确认正常后再切 100%"

  return 1
}

# 部署主命令
cmd_deploy() {
  local fn="${1:-ecan-graphql-api}"
  echo -e "${BLUE}=== 部署 $fn ===${NC}"

  # 1. 记录当前版本
  local current=$(get_current "$fn")
  if [ -n "$current" ]; then
    echo -e "  当前版本: ${GREEN}$current${NC}"
  else
    echo -e "  当前版本: ${YELLOW}(首次部署)${NC}"
  fi

  # 2. 快照当前 LATEST (仅当有版本记录时)
  if [ -n "$current" ]; then
    echo -e "  → 快照当前版本..."
    snapshot "$fn" "snapshot-before-$current" 2>/dev/null || true
    echo -e "  ✓ 已快照"
  fi

  # 3. 执行部署 (调用 deploy.sh)
  echo -e "  → 执行部署 (./deploy.sh)..."
  if ./deploy.sh 2>&1 | tail -5; then
    echo -e "  ✓ 部署完成"
  else
    echo -e "${RED}❌ 部署失败${NC}"
    return 1
  fi

  # 4. 创建版本快照
  local ver=$(next_version "$fn")
  local sha=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  local ts=$(date '+%Y-%m-%d %H:%M')
  local desc="${sha} $ts"
  echo -e "  → 发布版本 $ver..."
  snapshot "$fn" "$desc" 2>/dev/null || echo -e "  ⚠️  版本发布失败 (可手动 publish)"

  # 5. 更新版本记录
  local data="$(read_versions)"
  echo "$data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
fn = '$fn'
ver = '$ver'
desc = '$desc'
ts = '$ts'
if fn not in data: data[fn] = {'versions': {}, 'current': ''}
data[fn]['versions'][ver] = {'desc': desc, 'ts': ts}
data[fn]['current'] = ver
print(json.dumps(data, indent=2))
" > "$VERSION_FILE"

  echo -e "  ✓ 版本 $ver 已记录"
  echo -e "  描述: $desc"
  echo ""
  echo -e "${GREEN}✅ $fn 部署完成, 版本: $ver${NC}"
}

# 列出版本
cmd_list() {
  local fn="${1:-ecan-graphql-api}"
  echo -e "${BLUE}=== $fn 版本列表 ===${NC}"
  echo ""

  # 列出 TCB 版本
  echo -e "${YELLOW}TCB SCF 版本:${NC}"
  list_versions "$fn" | tail -n +5 | head -20

  echo ""
  echo -e "${YELLOW}本地版本记录:${NC}"
  local data="$(read_versions)"
  echo "$data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
fn = '$fn'
info = data.get(fn, {})
cur = info.get('current', '')
for ver, meta in sorted(info.get('versions', {}).items(), key=lambda x: x[0]):
    marker = ' ← CURRENT' if ver == cur else ''
    print(f'  {ver}: {meta.get(\"desc\",\"\")} ({meta.get(\"ts\",\"\")}){marker}')
if not info.get('versions'):
    print('  (无记录)')
" 2>/dev/null
}

# 回滚
cmd_rollback() {
  local fn="${1:-ecan-graphql-api}"
  local target="${2:-}"

  if [ -z "$target" ]; then
    echo -e "${RED}❌ 需要指定目标版本${NC}"
    echo "  用法: $0 rollback <fn> <version>"
    echo "  例如: $0 rollback ecan-graphql-api v1"
    cmd_list "$fn"
    return 1
  fi

  restore_version "$fn" "$target"
}

# 当前版本
cmd_current() {
  local fn="${1:-ecan-graphql-api}"
  local cur=$(get_current "$fn")
  if [ -n "$cur" ]; then
    echo -e "${GREEN}$cur${NC}"
  else
    echo -e "${YELLOW}(未记录)${NC}"
  fi
}

# 主入口
CMD="${1:-}"
FUNC="${2:-}"

case "$CMD" in
  deploy)
    cmd_deploy "$FUNC"
    ;;
  list)
    cmd_list "$FUNC"
    ;;
  rollback)
    cmd_rollback "$FUNC" "${3:-}"
    ;;
  current)
    cmd_current "$FUNC"
    ;;
  *)
    echo "用法: $0 <command> [function] [args]"
    echo ""
    echo "命令:"
    echo "  deploy [fn]      部署并创建版本快照"
    echo "  list [fn]        列出所有版本"
    echo "  rollback fn vN  回滚到指定版本"
    echo "  current [fn]     显示当前版本"
    echo ""
    echo "示例:"
    echo "  $0 deploy ecan-graphql-api"
    echo "  $0 list ecan-graphql-api"
    echo "  $0 rollback ecan-graphql-api v1"
    echo "  $0 current ecan-graphql-api"
    ;;
esac
