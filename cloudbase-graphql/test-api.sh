#!/bin/bash
# ============================================================
# eCan.ai API 测试脚本
# ============================================================
# 使用方式：
#   ./test-api.sh                    # 测试本地
#   ./test-api.sh <api-url>          # 测试指定 API

# API 地址（默认本地）
API_URL="${1:-http://localhost:3000/api/graphql}"

echo "========================================"
echo "  eCan.ai API 测试"
echo "========================================"
echo "API: $API_URL"
echo ""

# ============ 1. 健康检查 ============
echo "1️⃣  健康检查..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL")
if [ "$RESPONSE" = "200" ]; then
    echo "   ✅ API 可用 (HTTP $RESPONSE)"
else
    echo "   ❌ API 不可用 (HTTP $RESPONSE)"
    echo "   提示：确保云函数已部署并配置了 HTTP 触发器"
fi
echo ""

# ============ 2. 测试查询 ============
echo "2️⃣  测试 GraphQL 查询..."

QUERY='{"query":"query { getOrgs { id name } }"}'
RESPONSE=$(curl -s -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "$QUERY")

echo "   请求: query { getOrgs { id name } }"
echo "   响应: $(echo $RESPONSE | head -c 200)..."
echo ""

# ============ 3. 测试添加数据 ============
echo "3️⃣  测试添加 Agent..."

MUTATION='{"query":"mutation { addAgents(input: [{ name: \"Test Agent\", description: \"API 测试\", status: \"active\" }]) { id success } }"}'
RESPONSE=$(curl -s -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "$MUTATION")

echo "   请求: mutation { addAgents(...) }"
echo "   响应: $RESPONSE"
echo ""

# ============ 4. 测试查询 Agents ============
echo "4️⃣  测试查询 Agents..."

QUERY='{"query":"query { getAgents { id name status } }"}'
RESPONSE=$(curl -s -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "$QUERY")

echo "   请求: query { getAgents { id name status } }"
echo "   响应: $(echo $RESPONSE | head -c 300)..."
echo ""

# ============ 5. 测试 Skills ============
echo "5️⃣  测试查询 Skills..."

QUERY='{"query":"query { getAgentSkills { id name category } }"}'
RESPONSE=$(curl -s -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "$QUERY")

echo "   请求: query { getAgentSkills { id name category } }"
echo "   响应: $(echo $RESPONSE | head -c 300)..."
echo ""

# ============ 6. 测试 getAllMine ============
echo "6️⃣  测试批量查询 getAllMine..."

QUERY='{"query":"query { getAllMine { agents { id name } skills { id name } } }"}'
RESPONSE=$(curl -s -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "$QUERY")

echo "   请求: query { getAllMine { agents { id name } } }"
echo "   响应: $(echo $RESPONSE | head -c 300)..."
echo ""

echo "========================================"
echo "  ✅ 测试完成"
echo "========================================"
echo ""
echo "📖 打开 Playground: $API_URL"
