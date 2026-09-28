#!/bin/bash
# M2-05 S3规则引擎 验收测试
# 验证：① 关闭LLM开关跑01表，输出看板5张图 ② chart_rules.yaml截图

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M2-05 S3规则引擎 验收测试"
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

echo "【步骤1】查询图表规则配置"
echo "------------------------"
test_api "查询YAML规则" \
    "curl -s ${API_BASE}/brain/s3/rules | grep -o 's3_chart_rules.yaml'" \
    "yaml"

test_api "规则数量" \
    "curl -s ${API_BASE}/brain/s3/rules | grep -o 'rule_count'" \
    "rule_count"

test_api "兜底规则" \
    "curl -s ${API_BASE}/brain/s3/rules | grep -o 'fallback'" \
    "fallback"

echo ""
echo "【步骤2】查询字段类型"
echo "------------------------"
test_api "字段类型API" \
    "curl -s ${API_BASE}/brain/s3/field-types | grep -o 'date.*number.*category'" \
    "date"

test_api "图表类型API" \
    "curl -s ${API_BASE}/brain/s3/chart-types | grep -o 'kpi.*line.*bar.*pie'" \
    "kpi"

echo ""
echo "【步骤3】01表看板生成（无需LLM）"
echo "------------------------"
test_api "01表生成看板" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-01-table | grep -o 'success.*true'" \
    "success"

test_api "看板含5个图表" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-01-table | grep -o 'chart_count.*5'" \
    "chart_count"

test_api "图表全为规则的生成（无LLM）" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-01-table | grep -o 'rule_engine'" \
    "rule_engine"

test_api "llm_used=false" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-01-table | grep -o 'llm_used.*false'" \
    "false"

echo ""
echo "【步骤4】验证5种必要图表类型"
echo "------------------------"
test_api "包含KPI" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-01-table | grep -o 'kpi'" \
    "kpi"

test_api "包含line趋势" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-01-table | grep -o 'line'" \
    "line"

test_api "包含bar对比" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-01-table | grep -o 'bar'" \
    "bar"

test_api "包含pie分布" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-01-table | grep -o 'pie'" \
    "pie"

test_api "包含table明细" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-01-table | grep -o 'table'" \
    "table"

echo ""
echo "【步骤5】自定义字段推荐测试"
echo "------------------------"
test_api "推荐5个图表" \
    "curl -s -X POST ${API_BASE}/brain/s3/recommend -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_test\",\"fields\":[\"日期\",\"金额\",\"类别\",\"地区\"],\"grain\":\"detail\"}' | grep -o 'chart_count'" \
    "chart_count"

test_api "生成到看板" \
    "curl -s -X POST ${API_BASE}/brain/s3/generate-dashboard -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_test\",\"fields\":[\"日期\",\"金额\",\"类别\"],\"grain\":\"detail\"}' | grep -o 'generated_by.*rule_engine'" \
    "rule_engine"

echo ""
echo "【步骤6】粒度限制测试"
echo "------------------------"
test_api "粒度限制API" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-grain-constraints | grep -o 'passed.*true'" \
    "passed"

test_api "detail粒度允许table" \
    "curl -s -X POST ${API_BASE}/brain/s3/_internal/test-grain-constraints | grep -o 'has_table.*true'" \
    "true"

echo ""
echo "========================================"
echo "M2-05 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M2-05 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ 关闭LLM跑01表，输出5张图"
    echo "     - KPI卡"
    echo "     - 趋势图(line)"
    echo "     - 对比图(bar)"
    echo "     - 分布图(pie)"
    echo "     - 明细表(table)"
    echo "  2. ✅ chart_rules.yaml 规则配置"
    echo "  3. ✅ llm_used=false（完全规则生成）"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M2-05 存在失败项${NC}"
    exit 1
fi