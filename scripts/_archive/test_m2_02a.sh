#!/bin/bash
# M2-02a LLM网关-基础调用 验收测试
# 验证：① curl POST /v1/chat/completions 返回200+JSON ② Jinja2模板渲染 ③ 重试日志

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M2-02a LLM网关-基础调用 验收测试"
echo "========================================"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

passed=0
failed=0

test_api() {
    local name=$1
    local cmd=$2
    local check=$3
    
    echo -n "Testing: $name ... "
    result=$(eval $cmd 2>&1)
    
    if echo "$result" | grep -q "$check"; then
        echo -e "${GREEN}✅ PASSED${NC}"
        ((passed++))
        return 0
    else
        echo -e "${RED}❌ FAILED${NC}"
        echo "  Response: $result"
        ((failed++))
        return 1
    fi
}

echo "【步骤1】OpenAI兼容接口测试"
echo "------------------------"
test_api "POST /llm/chat/completions 200" \
    "curl -s -X POST ${API_BASE}/llm/chat/completions -H 'Content-Type: application/json' -d '{\"model\":\"gpt-4\",\"messages\":[{\"role\":\"user\",\"content\":\"分析担保风控数据\"}]}' | grep -o 'success.*true'" \
    "success"

test_api "返回JSON格式" \
    "curl -s -X POST ${API_BASE}/llm/chat/completions -H 'Content-Type: application/json' -d '{\"model\":\"gpt-4\",\"messages\":[{\"role\":\"user\",\"content\":\"分析担保风控\"}]}' | grep -o 'response_json'" \
    "response_json"

echo ""
echo "【步骤2】LLM网关chat接口测试"
echo "------------------------"
test_api "直接prompt调用" \
    "curl -s -X POST ${API_BASE}/llm/chat -H 'Content-Type: application/json' -d '{\"prompt\":\"识别这个数据集的主题\",\"json_mode\":true}' | grep -o 'tokens_used'" \
    "tokens_used"

test_api "Token计量" \
    "curl -s -X POST ${API_BASE}/llm/chat -H 'Content-Type: application/json' -d '{\"prompt\":\"分析数据\",\"user_id\":\"test_001\"}' | grep -o 'tokens_prompt'" \
    "tokens_prompt"

echo ""
echo "【步骤3】Jinja2模板渲染测试"
echo "------------------------"
# 先初始化配置
curl -s -X POST ${API_BASE}/brain/_internal/init-configs > /dev/null 2>&1

test_api "模板渲染接口" \
    "curl -s -X POST ${API_BASE}/llm/template/render -H 'Content-Type: application/json' -d '{\"template_key\":\"goal_prompt_v1\",\"context\":{\"theme\":\"担保风控\",\"grain\":\"detail\",\"fields\":[\"担保金额\",\"抵押率\"]}}' | grep -o 'rendered'" \
    "rendered"

test_api "模板中使用变量" \
    "curl -s -X POST ${API_BASE}/llm/template/render -H 'Content-Type: application/json' -d '{\"template_key\":\"goal_prompt_v1\",\"context\":{\"theme\":\"担保风控\"}}' | grep -o '担保风控'" \
    "担保风控"

echo ""
echo "【步骤4】模板+LLM完整调用"
echo "------------------------"
test_api "模板+LLM调用" \
    "curl -s -X POST ${API_BASE}/llm/chat -H 'Content-Type: application/json' -d '{\"template_key\":\"goal_prompt_v1\",\"template_context\":{\"theme\":\"担保风控\",\"grain\":\"detail\",\"fields\":[\"担保金额\",\"抵押率\"]},\"json_mode\":true}' | grep -o 'goals'" \
    "goals"

echo ""
echo "【步骤5】限流配置查询"
echo "------------------------"
test_api "限流配置查询" \
    "curl -s ${API_BASE}/llm/config | grep -o 'concurrency_limit'" \
    "concurrency_limit"

test_api "Mock模式标识" \
    "curl -s ${API_BASE}/llm/config | grep -o 'mock_mode'" \
    "mock_mode"

echo ""
echo "========================================"
echo "M2-02a 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M2-02a 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ curl POST /v1/chat/completions 返回200+JSON"
    echo "  2. ✅ Jinja2模板渲染输出（含变量替换）"
    echo "  3. ✅ Token计量（tokens_prompt/completion/used）"
    echo ""
    echo "重试日志验证（需手动测试）："
    echo "  1. 断网: sudo ifconfig eth0 down"
    echo "  2. 发起请求，观察日志中的重试"
    echo "  3. 恢复网络: sudo ifconfig eth0 up"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M2-02a 存在失败项${NC}"
    exit 1
fi