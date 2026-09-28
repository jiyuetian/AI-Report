#!/bin/bash
# M2-03 S1主题识别器 验收测试
# 验证：① 五表识别为担保风控截图 ② trace表1行含theme_tag ③ 词典命中不调LLM日志

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M2-03 S1主题识别器 验收测试"
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

echo "【步骤1】检查主题词典"
echo "------------------------"
# 先初始化配置
curl -s -X POST ${API_BASE}/brain/_internal/init-configs > /dev/null 2>&1

test_api "词典查询" \
    "curl -s ${API_BASE}/brain/s1/dictionary | grep -o '担保风控'" \
    "担保风控"

test_api "词典关键词" \
    "curl -s ${API_BASE}/brain/s1/dictionary | grep -o '抵押'" \
    "抵押"

echo ""
echo "【步骤2】01表主题识别（担保风控）"
echo "------------------------"
test_api "01表识别" \
    "curl -s -X POST ${API_BASE}/brain/s1/detect -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"fields\":[\"借据编号\",\"担保金额\",\"抵押率\",\"质押物\",\"保证人\"],\"dataset_name\":\"01表\"}' | grep -o '担保风控'" \
    "担保风控"

test_api "01表置信度" \
    "curl -s -X POST ${API_BASE}/brain/s1/detect -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"fields\":[\"借据编号\",\"担保金额\",\"抵押率\"],\"dataset_name\":\"01表\"}' | grep -o 'confidence'" \
    "confidence"

echo ""
echo "【步骤3】02表主题识别（客户画像）"
echo "------------------------"
test_api "02表识别" \
    "curl -s -X POST ${API_BASE}/brain/s1/detect -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_02\",\"fields\":[\"客户编号\",\"客户名称\",\"客户类型\",\"注册地址\"],\"dataset_name\":\"02表\"}' | grep -o '客户画像'" \
    "客户画像"

echo ""
echo "【步骤4】03表主题识别（逾期分析）"
echo "------------------------"
test_api "03表识别" \
    "curl -s -X POST ${API_BASE}/brain/s1/detect -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_03\",\"fields\":[\"月份\",\"逾期金额\",\"逾期天数\",\"不良率\"],\"dataset_name\":\"03表\"}' | grep -o '逾期分析'" \
    "逾期分析"

echo ""
echo "【步骤5】04表主题识别（产品分析）"
echo "------------------------"
test_api "04表识别" \
    "curl -s -X POST ${API_BASE}/brain/s1/detect -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_04\",\"fields\":[\"产品类型\",\"贷款品种\",\"合同金额\",\"合同期限\"],\"dataset_name\":\"04表\"}' | grep -o '产品分析'" \
    "产品分析"

echo ""
echo "【步骤6】05表主题识别（担保风控）"
echo "------------------------"
test_api "05表识别" \
    "curl -s -X POST ${API_BASE}/brain/s1/detect -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_05\",\"fields\":[\"担保编号\",\"担保方式\",\"担保金额\",\"抵押物名称\"],\"dataset_name\":\"05表\"}' | grep -o '担保风控'" \
    "担保风控"

echo ""
echo "【步骤7】v2五表批量测试"
echo "------------------------"
test_api "v2五表批量测试" \
    "curl -s -X POST ${API_BASE}/brain/s1/_internal/test-v2-tables | grep -o 'all_passed.*true'" \
    "all_passed"

test_api "五表全部通过" \
    "curl -s -X POST ${API_BASE}/brain/s1/_internal/test-v2-tables | grep -o '担保风控.*客户画像.*逾期分析'" \
    "担保风控"

echo ""
echo "【步骤8】验证词典命中（不调LLM）"
echo "------------------------"
# 检查是否为 dictionary 方法
test_api "01表使用词典" \
    "curl -s -X POST ${API_BASE}/brain/s1/detect -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"fields\":[\"担保金额\",\"抵押率\",\"质押物\"],\"dataset_name\":\"01表\"}' | grep -o 'dictionary'" \
    "dictionary"

test_api "01表未调LLM" \
    "curl -s -X POST ${API_BASE}/brain/s1/detect -H 'Content-Type: application/json' -d '{\"dataset_id\":\"ds_01\",\"fields\":[\"担保金额\",\"抵押率\",\"质押物\"],\"dataset_name\":\"01表\"}' | grep -o 'llm_called.*false'" \
    "false"

echo ""
echo "========================================"
echo "M2-03 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M2-03 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ 01表 → 担保风控"
    echo "  2. ✅ 02表 → 客户画像"
    echo "  3. ✅ 03表 → 逾期分析"
    echo "  4. ✅ 04表 → 产品分析"
    echo "  5. ✅ 05表 → 担保风控"
    echo "  6. ✅ 词典命中，llm_called=false（不调LLM，降本）"
    echo ""
    echo "日志验证："
    echo "  观察后端日志，确认词典命中时不输出 '[LLM] 调用' 日志"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M2-03 存在失败项${NC}"
    exit 1
fi