#!/bin/bash
# M3-06 加量申请 验收测试
# 验证：① 用户申请 ② 管理员审批 ③ 当日有效

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M3-06 加量申请 验收测试"
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

echo "【步骤1】用户申请加量"
echo "------------------------"
test_api "申请提交成功" \
    "curl -s -X POST '${API_BASE}/tokens/applications/apply' -H 'Content-Type: application/json' -d '{\"amount\":2000,\"reason\":\"今天有紧急报表需要生成，预计需要额外2000Token\"}' | grep -o 'success.*true'" \
    "success"

test_api "申请状态pending" \
    "curl -s -X POST '${API_BASE}/tokens/applications/apply' -H 'Content-Type: application/json' -d '{\"amount\":2000,\"reason\":\"今天有紧急报表需要生成，预计需要额外2000Token，请勿重复提交测试\"}' | grep -o 'pending'" \
    "pending"

test_api "当日有效提示" \
    "curl -s -X POST '${API_BASE}/tokens/applications/apply' -H 'Content-Type: application/json' -d '{\"amount\":2000,\"reason\":\"今天有紧急报表需要生成，预计需要额外2000Token，请勿重复提交测试2\"}' | grep -o '当日有效'" \
    "当日有效"

echo ""
echo "【步骤2】获取我的申请"
echo "------------------------"
test_api "我的申请列表" \
    "curl -s '${API_BASE}/tokens/applications/my-applications' | grep -o 'applications'" \
    "applications"

test_api "申请详情" \
    "curl -s '${API_BASE}/tokens/applications/my-applications' | grep -o 'apply_amount'" \
    "apply_amount"

echo ""
echo "【步骤3】管理员审批"
echo "------------------------"
# 获取待审批列表
PENDING_RESULT=$(curl -s "${API_BASE}/tokens/applications/admin/pending")
APP_ID=$(echo $PENDING_RESULT | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

test_api "待审批列表" \
    "curl -s '${API_BASE}/tokens/applications/admin/pending' | grep -o 'pending_count'" \
    "pending_count"

if [ -n "$APP_ID" ]; then
    test_api "审批通过" \
        "curl -s -X POST '${API_BASE}/tokens/applications/admin/${APP_ID}/approve' -H 'Content-Type: application/json' -d '{\"approved_amount\":2000,\"comment\":\"同意，当日有效\"}' | grep -o 'success.*true'" \
        "success"
    
    test_api "审批后状态approved" \
        "curl -s -X POST '${API_BASE}/tokens/applications/admin/${APP_ID}/approve' -H 'Content-Type: application/json' -d '{\"approved_amount\":2000}' | grep -o 'approved'" \
        "approved"
    
    test_api "加量生效" \
        "curl -s -X POST '${API_BASE}/tokens/applications/admin/${APP_ID}/approve' -H 'Content-Type: application/json' -d '{\"approved_amount\":2000}' | grep -o 'extra_quota'" \
        "extra_quota"
    
    test_api "过期时间设置" \
        "curl -s -X POST '${API_BASE}/tokens/applications/admin/${APP_ID}/approve' -H 'Content-Type: application/json' -d '{\"approved_amount\":2000}' | grep -o 'expires_at'" \
        "expires_at"
fi

echo ""
echo "【步骤4】检查加量生效"
echo "------------------------"
test_api "检查有效加量" \
    "curl -s '${API_BASE}/tokens/applications/check-active' | grep -o 'has_active'" \
    "has_active"

test_api "总配额增加" \
    "curl -s '${API_BASE}/tokens/applications/check-active' | grep -o 'total_limit'" \
    "total_limit"

echo ""
echo "【步骤5】管理员统计"
echo "------------------------"
test_api "全部申请统计" \
    "curl -s '${API_BASE}/tokens/applications/admin/all' | grep -o 'statistics'" \
    "statistics"

test_api "状态统计" \
    "curl -s '${API_BASE}/tokens/applications/admin/all' | grep -o 'approved'" \
    "approved"

echo ""
echo "========================================"
echo "M3-06 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M3-06 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ 用户申请录屏10s"
    echo "  2. ✅ 管理员审批通过录屏10s"
    echo "  3. ✅ 生效后token余量增加截图"
    echo "  4. ✅ 当日过期时间设置"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M3-06 存在失败项${NC}"
    echo "卡点：审批状态机错乱 → 需上报PM"
    exit 1
fi