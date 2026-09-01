#!/bin/bash
# M1全量验收测试脚本

API_BASE="http://localhost:8000/api/v1"
TEST_DATA_DIR="../test_data"

echo "========================================"
echo "M1全量验收测试"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

test_passed=0
test_failed=0

# 测试函数
run_test() {
    local name=$1
    local cmd=$2
    local expected=$3
    
    echo -n "Testing: $name ... "
    result=$(eval $cmd 2>&1)
    
    if echo "$result" | grep -q "$expected"; then
        echo -e "${GREEN}✅ PASSED${NC}"
        ((test_passed++))
    else
        echo -e "${RED}❌ FAILED${NC}"
        echo "  Expected: $expected"
        echo "  Got: $result"
        ((test_failed++))
    fi
}

echo "【M1-05a】文件上传测试"
echo "------------------------"

# 测试1: 正常上传
run_test "CSV上传" \
    "curl -s -X POST -F \"file=@${TEST_DATA_DIR}/sample.csv\" ${API_BASE}/files | grep -o 'file_id'" \
    "file_id"

# 测试2: 413错误
run_test "文件过大413" \
    "curl -s -X POST -F \"file=@${TEST_DATA_DIR}/large_file.bin\" ${API_BASE}/files | grep -o 'UPLOAD_413'" \
    "UPLOAD_413"

# 测试3: 415错误
run_test "格式不支持415" \
    "curl -s -X POST -F \"file=@${TEST_DATA_DIR}/test.pdf\" ${API_BASE}/files | grep -o 'UPLOAD_415'" \
    "UPLOAD_415"

echo ""
echo "【M1-06】多Sheet与编码测试"
echo "------------------------"

# 创建测试文件ID
FILE_ID="550e8400-e29b-41d4-a716-446655440000"

run_test "Sheet列表获取" \
    "curl -s ${API_BASE}/files/${FILE_ID}/sheets | grep -o 'sheets'" \
    "sheets"

run_test "编码检测" \
    "curl -s ${API_BASE}/files/${FILE_ID}/encoding | grep -o 'detected_encoding'" \
    "detected_encoding"

echo ""
echo "【M1-07】DuckDB入库测试"
echo "------------------------"

run_test "数据集创建" \
    "curl -s -X POST ${API_BASE}/datasets -H 'Content-Type: application/json' -d '{\"file_id\":\"${FILE_ID}\",\"name\":\"test\"}' | grep -o 'dataset_id'" \
    "dataset_id"

run_test "字段画像" \
    "curl -s ${API_BASE}/datasets/${FILE_ID}/profile | grep -o 'profiles'" \
    "profiles"

echo ""
echo "【M1-08】六类质检测试"
echo "------------------------"

run_test "质检执行" \
    "curl -s -X POST ${API_BASE}/quality/check -H 'Content-Type: application/json' -d '{\"dataset_id\":\"${FILE_ID}\"}' | grep -o 'issues'" \
    "issues"

run_test "六类质检" \
    "curl -s -X POST ${API_BASE}/quality/check -H 'Content-Type: application/json' -d '{\"dataset_id\":\"${FILE_ID}\"}' | grep -o 'null.*format.*unique.*range.*logic.*code'" \
    "null"

echo ""
echo "【M1-09】修复执行测试"
echo "------------------------"

run_test "修复规则创建" \
    "curl -s -X POST ${API_BASE}/quality/fix -H 'Content-Type: application/json' -d '{\"dataset_id\":\"${FILE_ID}\",\"issue_type\":\"null\",\"column\":\"test\",\"fix_strategy\":\"fill_median\"}' | grep -o 'rule_id'" \
    "rule_id"

echo ""
echo "【M1-10】二次质检门禁测试"
echo "------------------------"

run_test "门禁检查" \
    "curl -s -X POST ${API_BASE}/brain/run -H 'Content-Type: application/json' -d '{\"dataset_id\":\"${FILE_ID}\"}' | grep -o 'QUALITY_NOT_PASSED\|SUCCESS'" \
    "QUALITY_NOT_PASSED\|SUCCESS"

echo ""
echo "【M1-15】规则配置测试"
echo "------------------------"

run_test "配置查询" \
    "curl -s ${API_BASE}/brain/configs | grep -o 'configs'" \
    "configs"

run_test "阈值更新" \
    "curl -s -X POST ${API_BASE}/brain/configs/update -H 'Content-Type: application/json' -d '{\"category\":\"quality\",\"key\":\"null_threshold\",\"value\":0.01}' | grep -o 'success'" \
    "success"

echo ""
echo "========================================"
echo "测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${test_passed}${NC}"
echo -e "失败: ${RED}${test_failed}${NC}"
echo ""

if [ $test_failed -eq 0 ]; then
    echo -e "${GREEN}✅ M1全量验收通过${NC}"
    exit 0
else
    echo -e "${RED}❌ 存在失败的测试${NC}"
    exit 1
fi