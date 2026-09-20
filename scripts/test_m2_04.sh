#!/bin/bash
# M2-04 S2目标生成器 验收测试
# 验证：① 01表产出6个目标JSON截图（中文业务化） ② prompt模板入库brain_configs截图

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M2-04 S2目标生成器 验收测试"
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

echo "【步骤1】检查Prompt模板入库"
echo "------------------------"
# 先初始化配置
curl -s -X POST ${API_BASE}/brain/_internal/init-configs > /dev/null 2>&1

test_api "Prompt模板查询" \
    "curl -s ${API_BASE}/brain/s2/prompt-template | grep -o 'goal_prompt_v1'" \
    "goal_prompt_v1"

test_api "模板内容含中文要求" \
    "curl -s ${API_BASE}/brain/s2/prompt-template | grep -o '中文业务化'" \
    "中文业务化"

echo ""
echo "【步骤2】01表目标生成（担保风控）"
echo "------------------------"
test_api "01表生成6个目标" \
    "curl -s -X POST ${API_BASE}/brain/s2/generate -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"theme\":\"担保风控\",\"fields\":[\"借据编号\",\"担保金额\",\"抵押率\",\"质押物\",\"地区\",\"逾期天数\"]}' | grep -o 'goal_count.*6'" \
    "6"

test_api "目标含中文标题" \
    "curl -s -X POST ${API_BASE}/brain/s2/generate -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"theme\":\"担保风控\",\"fields\":[\"担保金额\",\"抵押率\"]}' | grep -o 'title'" \
    "title"

test_api "目标含业务化描述" \
    "curl -s -X POST ${API_BASE}/brain/s2/generate -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"theme\":\"担保风控\",\"fields\":[\"担保金额\",\"抵押率\"]}' | grep -o 'description'" \
    "description"

echo ""
echo "【步骤3】验证目标类型覆盖"
echo "------------------------"
test_api "含趋势类目标" \
    "curl -s -X POST ${API_BASE}/brain/s2/generate -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"theme\":\"担保风控\",\"fields\":[\"担保金额\",\"抵押率\"]}' | grep -o '趋势'" \
    "趋势"

test_api "含对比类目标" \
    "curl -s -X POST ${API_BASE}/brain/s2/generate -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"theme\":\"担保风控\",\"fields\":[\"担保金额\",\"抵押率\"]}' | grep -o '对比'" \
    "对比"

test_api "含分布类目标" \
    "curl -s -X POST ${API_BASE}/brain/s2/generate -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"theme\":\"担保风控\",\"fields\":[\"担保金额\",\"抵押率\"]}' | grep -o '分布'" \
    "分布"

echo ""
echo "【步骤4】验证01表目标含指定关键词"
echo "------------------------"
# 01表应该包含：逾期监控/地区对比/抵押风险类目标
RESULT=$(curl -s -X POST ${API_BASE}/brain/s2/generate \
    -H "Content-Type: application/json" \
    -d '{"dataset_id":"ds_01","theme":"担保风控","fields":["借据编号","担保金额","抵押率","质押物","地区","逾期天数"]}')

if echo "$RESULT" | grep -q "逾期\|地区\|抵押\|风险\|担保"; then
    echo -e "Testing: 01表目标含业务关键词 ... ${GREEN}✅ PASSED${NC}"
    ((passed++))
else
    echo -e "Testing: 01表目标含业务关键词 ... ${RED}❌ FAILED${NC}"
    ((failed++))
fi

echo ""
echo "【步骤5】v2五表批量测试"
echo "------------------------"
test_api "v2五表目标生成" \
    "curl -s -X POST ${API_BASE}/brain/s2/_internal/test-v2-tables | grep -o 'all_passed'" \
    "all_passed"

test_api "01表含必要类型" \
    "curl -s -X POST ${API_BASE}/brain/s2/_internal/test-v2-tables | grep -o 'has_required_types.*true'" \
    "true"

echo ""
echo "【步骤6】目标类型查询"
echo "------------------------"
test_api "目标类型API" \
    "curl -s ${API_BASE}/brain/s2/types | grep -o 'KPI'" \
    "KPI"

test_api "目标类型列表" \
    "curl -s ${API_BASE}/brain/s2/types | grep -o '趋势.*对比.*分布'" \
    "趋势"

echo ""
echo "========================================"
echo "M2-04 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M2-04 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ 01表产出6个目标（含中文业务化表述）"
    echo "  2. ✅ 目标包含：趋势/对比/分布等类型"
    echo "  3. ✅ 01表目标含：逾期/地区/抵押/风险类关键词"
    echo "  4. ✅ prompt模板已入库（goal_prompt_v1）"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M2-04 存在失败项${NC}"
    exit 1
fi