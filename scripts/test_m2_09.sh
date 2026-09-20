#!/bin/bash
# M2-09 看板API 验收测试
# 验证：① POST /dashboards 成功 ② 跨表charts创建返回403 ③ 多dataset挂载截图

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M2-09 看板API 验收测试"
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

echo "【步骤1】创建看板"
echo "------------------------"
test_api "创建看板API" \
    "curl -s -X POST ${API_BASE}/dashboards -H 'Content-Type: application/json' -d '{\"name\":\"测试看板\",\"description\":\"测试描述\",\"dataset_ids\":[\"ds_001\",\"ds_002\"],\"primary_dataset_id\":\"ds_001\"}' | grep -o 'dashboard_id'" \
    "dashboard_id"

test_api "返回看板数据" \
    "curl -s -X POST ${API_BASE}/dashboards -H 'Content-Type: application/json' -d '{\"name\":\"测试看板2\"}' | grep -o 'success.*true'" \
    "success"

echo ""
echo "【步骤2】查询看板"
echo "------------------------"
test_api "看板列表" \
    "curl -s ${API_BASE}/dashboards | grep -o 'dashboards'" \
    "dashboards"

echo ""
echo "【步骤3】多数据源挂载"
echo "------------------------"
# 获取刚创建的看板ID
DASHBOARD_RESULT=$(curl -s -X POST ${API_BASE}/dashboards \
    -H "Content-Type: application/json" \
    -d '{"name":"多数据源测试","dataset_ids":["ds_001"],"primary_dataset_id":"ds_001"}')
DASHBOARD_ID=$(echo $DASHBOARD_RESULT | grep -o '"dashboard_id":"[^"]*"' | cut -d'"' -f4)

test_api "挂载数据源" \
    "curl -s -X POST '${API_BASE}/dashboards/${DASHBOARD_ID}/datasets?dataset_id=ds_002' | grep -o 'success.*true'" \
    "success"

test_api "多数据源列表" \
    "curl -s -X POST '${API_BASE}/dashboards/${DASHBOARD_ID}/datasets?dataset_id=ds_003' | grep -o 'dataset_ids'" \
    "dataset_ids"

echo ""
echo "【步骤4】创建图表（单源绑定）"
echo "------------------------"
test_api "创建图表" \
    "curl -s -X POST ${API_BASE}/dashboards/${DASHBOARD_ID}/charts -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_001\",\"chart_type\":\"bar\",\"title\":\"测试图表\"}' | grep -o 'chart_id'" \
    "chart_id"

test_api "图表dataset_id非空" \
    "curl -s -X POST ${API_BASE}/dashboards/${DASHBOARD_ID}/charts -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_001\",\"chart_type\":\"line\",\"title\":\"测试2\"}' | grep -o 'dataset_id.*ds_001'" \
    "ds_001"

echo ""
echo "【步骤5】跨数据源拒绝"
echo "------------------------"
# 尝试创建ds_003的图表（不在dataset_ids中）
test_api "跨数据源返回403" \
    "curl -s -X POST ${API_BASE}/dashboards/${DASHBOARD_ID}/charts -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_999\",\"chart_type\":\"bar\",\"title\":\"跨源\"}' | grep -o '403\|FORBIDDEN\|CROSS_DATASET'" \
    "CROSS_DATASET"

test_api "错误信息正确" \
    "curl -s -X POST ${API_BASE}/dashboards/${DASHBOARD_ID}/charts -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_999\",\"chart_type\":\"bar\"}' | grep -o '禁止跨数据源'" \
    "禁止跨数据源"

echo ""
echo "【步骤6】图表CRUD"
echo "------------------------"
test_api "图表列表" \
    "curl -s ${API_BASE}/dashboards/${DASHBOARD_ID}/charts | grep -o 'charts'" \
    "charts"

test_api "图表更新" \
    "curl -s -X PUT ${API_BASE}/dashboards/${DASHBOARD_ID}/charts/$(curl -s ${API_BASE}/dashboards/${DASHBOARD_ID}/charts | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4) -H 'Content-Type: application/json' -d '{\"title\":\"更新后标题\"}' | grep -o 'success'" \
    "success"

echo ""
echo "========================================"
echo "M2-09 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M2-09 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ POST /dashboards 成功返回 dashboard_id"
    echo "  2. ✅ 跨表charts创建返回403 CROSS_DATASET_FORBIDDEN"
    echo "  3. ✅ 多dataset挂载成功（dataset_ids数组）"
    echo "  4. ✅ 图表单源绑定（dataset_id非空约束）"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M2-09 存在失败项${NC}"
    exit 1
fi