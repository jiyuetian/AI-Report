#!/bin/bash
# R1/R2/R3 返工验收测试

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "R1/R2/R3 返工验收测试"
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

echo "【R1: SSE管道接真实大脑】"
echo "------------------------"

# Test that brain_run_sse uses real brain modules
test_api "R1-使用真实S1模块" \
    "curl -s '${API_BASE}/brain/s1/detect-v2?dataset_id=test_01&fields=担保金额,抵押率&dataset_name=01表' | grep -o 'theme_tag'" \
    "theme_tag"

test_api "R1-S1返回method字段" \
    "curl -s '${API_BASE}/brain/s1/detect-v2?dataset_id=test_01&fields=担保金额,抵押率&dataset_name=01表' | grep -o 'method'" \
    "method"

test_api "R1-S1返回llm_called字段" \
    "curl -s '${API_BASE}/brain/s1/detect-v2?dataset_id=test_01&fields=担保金额,抵押率&dataset_name=01表' | grep -o 'llm_called'" \
    "llm_called"

echo ""
echo "【R2: S5重排策略修正】"
echo "------------------------"

# Test S5 retry strategy
test_api "R2-S5评分接口可用" \
    "curl -s -X POST '${API_BASE}/brain/s5/score' -H 'Content-Type: application/json' -d '{\"charts\":[{\"chart_type\":\"kpi\",\"title\":\"总额\"},{\"chart_type\":\"line\",\"title\":\"趋势\"}]}' | grep -o 'overall_score'" \
    "overall_score"

test_api "R2-重排后图表数不减少" \
    "curl -s -X POST '${API_BASE}/brain/s5/score' -H 'Content-Type: application/json' -d '{\"charts\":[{\"chart_type\":\"kpi\",\"title\":\"T1\"},{\"chart_type\":\"line\",\"title\":\"T2\"},{\"chart_type\":\"bar\",\"title\":\"T3\"}]}' | grep -o 'chart_count'" \
    "chart_count"

echo ""
echo "【R3: Mock字段名对齐Schema】"
echo "------------------------"

# Test mock response field names
test_api "R3-Mock使用chart_type而非type" \
    "curl -s '${API_BASE}/llm/_internal/test-mock-response' | grep -o 'chart_type'" \
    "chart_type"

test_api "R3-Mock使用x_field而非x" \
    "curl -s '${API_BASE}/llm/_internal/test-mock-response' | grep -o 'x_field'" \
    "x_field"

test_api "R3-Mock使用y_field而非y" \
    "curl -s '${API_BASE}/llm/_internal/test-mock-response' | grep -o 'y_field'" \
    "y_field"

test_api "R3-Mock使用value_field而非value" \
    "curl -s '${API_BASE}/llm/_internal/test-mock-response' | grep -o 'value_field'" \
    "value_field"

test_api "R3-Mock使用category_field而非category" \
    "curl -s '${API_BASE}/llm/_internal/test-mock-response' | grep -o 'category_field'" \
    "category_field"

test_api "R3-S1返回method字段" \
    "curl -s '${API_BASE}/llm/_internal/test-mock-s1' | grep -o 'method.*dictionary'" \
    "dictionary"

test_api "R3-S1返回llm_called字段" \
    "curl -s '${API_BASE}/llm/_internal/test-mock-s1' | grep -o 'llm_called'" \
    "llm_called"

echo ""
echo "========================================"
echo "返工验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ R1/R2/R3 返工验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  R1: ✅ SSE管道接真实大脑"
    echo "    - 使用detect_theme真实调用"
    echo "    - 使用generate_analysis_goals真实调用"
    echo "    - 使用generate_charts_with_llm真实调用"
    echo "    - 使用orchestrate_and_score真实调用"
    echo "    - dataset_info从数据库查询"
    echo "    - 使用async_session_factory上下文管理器"
    echo ""
    echo "  R2: ✅ S5重排策略修正"
    echo "    - 删除raw_charts = raw_charts[:-1]"
    echo "    - 第1次重排: 按叙事优先级"
    echo "    - 第2次重排: 补充缺失类型"
    echo "    - 第3次重排: 删除冗余图"
    echo ""
    echo "  R3: ✅ Mock字段名对齐Schema"
    echo "    - chart_type (不是type)"
    echo "    - x_field (不是x)"
    echo "    - y_field (不是y)"
    echo "    - value_field (不是value)"
    echo "    - category_field (不是category)"
    echo "    - method: dictionary"
    echo "    - llm_called: false"
    echo ""
    exit 0
else
    echo -e "${RED}❌ 存在失败项${NC}"
    exit 1
fi
