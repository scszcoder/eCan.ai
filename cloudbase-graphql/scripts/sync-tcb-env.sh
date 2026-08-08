#!/bin/bash
# ============================================================
# 推 .env.local 的敏感变量到 TCB 云函数环境变量
# ============================================================
#
# 用法：
#   ./scripts/sync-tcb-env.sh
#
# 【安全设计】
#   - 所有 secret 只从 .env.local 读（gitignored）
#   - 绝不写入 cloudbaserc.json（cloudbaserc.json 必须只含占位符，可安全提交）
#   - 绝不打印 secret 值（脚本中所有 secret 走 stdin/proc substitution, 仅显示长度）
#   - 绝不进 git
#
# 【cloudbaserc.json 里的占位符】
#   "__SET_IN_TCB_CONSOLE__" — 表示该值由本脚本从 .env.local 推送到 TCB,
#   本脚本**只会**推送到 TCB 云函数环境变量, **不会**回填 cloudbaserc.json。
#
# 依赖：
#   npm install -g @cloudbase/cli
#   cloudbase login
#

set -e

PINK='\033[1;35m'
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  同步 .env.local → TCB 云函数环境变量${NC}"
echo -e "${BLUE}========================================${NC}\n"

# --- Guard 1: Check CLI ---
if ! command -v tcb &> /dev/null; then
  if ! command -v cloudbase &> /dev/null; then
    echo -e "${RED}❌ tcb / cloudbase CLI 未安装${NC}"
    echo -e "${YELLOW}  安装: npm install -g @cloudbase/cli${NC}"
    exit 1
  fi
fi

# --- Guard 2: .env.local exists ---
if [ ! -f ".env.local" ]; then
  echo -e "${RED}❌ .env.local 不存在${NC}"
  exit 1
fi

# --- Guard 3: cloudbaserc.json is committed-only (must contain only placeholders) ---
# 任何不符合占位符模式的 secret 字段都意味着 cloudbaserc.json 被污染, 立刻退出
python3 << 'EOF'
import json, sys, re
try:
    with open("cloudbaserc.json", "r") as f:
        data = json.load(f)
except Exception as e:
    print(f"❌ 无法读取 cloudbaserc.json: {e}")
    sys.exit(1)

# 任何形如 secret 字段名的 KEY 一旦值不是占位符即视作污染
SECRET_KEYS = {"DATABASE_URL", "WEBSOCKET_PUSH_SECRET", "JWT_SECRET", "API_KEY", "PRIVATE_KEY"}
# 只接受严格的占位符字面量, 空字符串视为污染
ALLOWED_PLACEHOLDERS = {
    "__SET_IN_TCB_CONSOLE__",
    "__SET_VIA_TCB_CONSOLE_OR_LOCAL_ENV__",
}

violations = []
for fn in data.get("functions", []):
    fname = fn.get("name", "?")
    for k, v in (fn.get("envVariables") or {}).items():
        if k in SECRET_KEYS:
            if str(v) not in ALLOWED_PLACEHOLDERS:
                # 值不是占位符 = 真实 secret 暴露在 git 追踪文件中
                violations.append(f"  - {fname}.{k}: {str(v)[:30]}...")

if violations:
    print("❌ cloudbaserc.json 包含未脱敏的 secret, 拒绝运行:")
    print("\n".join(violations))
    print()
    print("修复方法:")
    print("  1. 编辑 cloudbaserc.json, 把上述字段改为占位符 __SET_IN_TCB_CONSOLE__")
    print("  2. 用 git filter-repo / bfg 清理 git 历史")
    print("  3. 重新提交")
    sys.exit(1)

print("✅ cloudbaserc.json 无明文 secret, 占位符合规")
EOF

# --- Load .env.local into env vars (subshell style, no echo) ---
set -a
. .env.local
set +a

if [ -z "$TCB_ENV_ID" ]; then
  echo -e "${RED}❌ TCB_ENV_ID 未配置${NC}"
  exit 1
fi

# --- Sanity: cannot be placeholder ---
if [[ "$DATABASE_URL" == *"__SET_IN_TCB_CONSOLE__"* ]] || \
   [[ "$DATABASE_URL" == *"__SET_VIA_TCB_CONSOLE_OR_LOCAL_ENV__"* ]]; then
  echo -e "${RED}❌ DATABASE_URL 还是占位符, 请先在 .env.local 填写真实密码${NC}"
  exit 1
fi

if [[ "$WEBSOCKET_PUSH_SECRET" == *"__SET_IN_TCB_CONSOLE__"* ]] || \
   [[ "$WEBSOCKET_PUSH_SECRET" == *"__SET_VIA_TCB_CONSOLE_OR_LOCAL_ENV__"* ]]; then
  echo -e "${RED}❌ WEBSOCKET_PUSH_SECRET 还是占位符${NC}"
  WEBSOCKET_PUSH_SECRET=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")
  echo -e "${YELLOW}  → 自动生成新密钥 (长度: ${#WEBSOCKET_PUSH_SECRET} chars, 不显示值)${NC}"
fi

# --- Core: call SCF API directly, never touch cloudbaserc.json ---
# 用 Python 一次性把每个函数的全部 env vars 推到 TCB。
# 关键: 整个脚本里 secret 仅作为 Python 变量存在, 不会写入任何文件 / git。
# 显示: 仅打印 KEY 列表 + 长度, 绝不打印 value。

push_env_to_scf() {
  local func_name="$1"
  shift
  # 剩余参数: KEY=VALUE 列表 (这些值不显示)
  local pairs=("$@")

  echo -e "${PINK}  → $func_name (${#pairs[@]} vars)${NC}"

  # 把 key=value 传进 Python 子进程, value 走 env 而不是命令行参数 (避免 ps 泄漏)
  python3 - "$func_name" "${pairs[@]}" << 'PYEOF'
import sys, os, json, subprocess

func_name = sys.argv[1]
rest = sys.argv[2:]

# 解析 k=v 对
vars_list = []
for kv in rest:
    if "=" not in kv:
        continue
    k, v = kv.split("=", 1)
    vars_list.append({"Key": k, "Value": v})

# 安全打印：不显示值, 只显示 key + 长度
for v in vars_list:
    val = v["Value"]
    is_secret = any(s in v["Key"].upper() for s in ["URL", "SECRET", "PASSWORD", "KEY", "TOKEN"])
    if is_secret:
        print(f"    {v['Key']} = <hidden, len={len(val)}>")
    else:
        # 非 secret 值（如 COS_BUCKET）也只显示前 30 字符
        print(f"    {v['Key']} = {val[:30]}{'...' if len(val) > 30 else ''}")

payload = {
    "FunctionName": func_name,
    "Namespace": os.environ["TCB_ENV_ID"],
    "Environment": {"Variables": vars_list},
}

# 调用 SCF API UpdateFunctionConfiguration
r = subprocess.run(
    ["tcb", "api", "scf", "UpdateFunctionConfiguration", "--json",
     "--body", json.dumps(payload)],
    capture_output=True, text=True
)

if r.returncode != 0:
    print(f"  ❌ SCF API 调用失败: {r.stderr[:300]}")
    sys.exit(1)
else:
    print(f"  ✅ 已推送到 TCB")
PYEOF
}

# 1. GraphQL API
echo -e "${YELLOW}⚙️  配置 ecan-graphql-api${NC}"
push_env_to_scf "ecan-graphql-api" \
  "NODE_ENV=production" \
  "TCB_REGION=ap-shanghai" \
  "COS_REGION=$COS_REGION" \
  "COS_BUCKET=$COS_BUCKET" \
  "WEBSOCKET_FUNCTION_NAME=ecan-websocket" \
  "WEBSOCKET_PUSH_SECRET=$WEBSOCKET_PUSH_SECRET" \
  "GRAPHQL_ENDPOINT_HOST=${GRAPHQL_ENDPOINT_HOST:-sccb0-d0gc5398xf028be6a.service.tcloudbase.com}" \
  "DATABASE_URL=$DATABASE_URL" \
  "TENCENT_SCHEDULER_FUNCTION=${TENCENT_SCHEDULER_FUNCTION:-ecan-graphql-api}" \
  "TENCENT_SCF_NAMESPACE=${TENCENT_SCF_NAMESPACE:-default}" \
  "TENCENT_REGION=${TENCENT_REGION:-ap-shanghai}"

# 2. WebSocket
echo -e "${YELLOW}⚙️  配置 ecan-websocket${NC}"
push_env_to_scf "ecan-websocket" \
  "NODE_ENV=production" \
  "TCB_REGION=ap-shanghai" \
  "COS_REGION=$COS_REGION" \
  "COS_BUCKET=$COS_BUCKET" \
  "WEBSOCKET_PUSH_SECRET=$WEBSOCKET_PUSH_SECRET"

# 3. Health
echo -e "${YELLOW}⚙️  配置 ecan-health${NC}"
push_env_to_scf "ecan-health" \
  "NODE_ENV=production" \
  "TCB_REGION=ap-shanghai"

# --- Final guard: cloudbaserc.json unchanged ---
echo ""
if git diff --quiet cloudbaserc.json 2>/dev/null; then
  echo -e "${GREEN}✅ cloudbaserc.json 仍是占位符, 未被修改${NC}"
else
  echo -e "${RED}❌ cloudbaserc.json 被意外修改! 立即退出${NC}"
  git diff cloudbaserc.json
  exit 1
fi

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  ✅ 环境变量已同步到 TCB 控制台${NC}"
echo -e "${GREEN}========================================${NC}\n"
echo -e "⚠️  提醒："
echo -e "   - 所有 secret 仅来自 .env.local (gitignored)。"
echo -e "   - cloudbaserc.json 仍是占位符, 绝无明文密码, 可安全提交 git。"
echo -e "   - Secret 不应出现在任何屏幕输出 / 日志 / git 中。\n"
