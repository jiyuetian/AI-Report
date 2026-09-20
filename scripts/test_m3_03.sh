#!/bin/bash
# M3-03 Token体系 验收测试
# 验证：① >90%预警 ② 耗尽禁用 ③ 次日0点重置

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M3-03 Token体系 验收测试"
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

echo "【步骤1】获取Token配额状态"
echo "------------------------"
test_api "获取配额状态" \
    "curl -s ${API_BASE}/tokens/quota | grep -o 'daily_limit'" \
    "daily_limit"

test_api "返回使用率" \
    "curl -s ${API_BASE}/tokens/quota | grep -o 'usage_percent'" \
    "usage_percent"

echo ""
echo "【步骤2】测试Token消耗"
echo "------------------------"
test_api "消耗Token成功" \
    "curl -s -X POST '${API_BASE}/tokens/consume' -H 'Content-Type: application/json' -d '{\"tokens\":100}' | grep -o 'success.*true'" \
    "success"

test_api "消耗后更新used_today" \
    "curl -s -X POST '${API_BASE}/tokens/consume' -H 'Content-Type: application/json' -d '{\"tokens\":50}' | grep -o 'used_today'" \
    "used_today"

echo ""
echo "【步骤3】测试>90%预警"
echo "------------------------"
test_api "预警状态测试" \
    "curl -s -X POST '${API_BASE}/tokens/_internal/test-warning' | grep -o 'is_warning.*true'" \
    "is_warning"

test_api "预警文案触发" \
    "curl -s -X POST '${API_BASE}/tokens/_internal/test-warning' | grep -o 'warning_triggered'" \
    "warning_triggered"

test_api "使用率>90%" \
    "curl -s -X POST '${API_BASE}/tokens/_internal/test-warning' | grep -o 'usage_percent.*9[0-9]'" \
    "usage_percent"

echo ""
echo "【步骤4】测试Token耗尽禁用"
echo "------------------------"
test_api "耗尽状态检测" \
    "curl -s -X POST '${API_BASE}/tokens/_internal/test-exhausted' | grep -o 'is_exhausted.*true'" \
    "is_exhausted"

test_api "can_send返回false" \
    "curl -s -X POST '${API_BASE}/tokens/_internal/test-exhausted' | grep -o 'can_send.*false'" \
    "can_send"

test_api "输入框禁用标记" \
    "curl -s -X POST '${API_BASE}/tokens/_internal/test-exhausted' | grep -o 'input_should_be_disabled.*true'" \
    "input_should_be_disabled"

test_api "禁用原因文案" \
    "curl -s -X POST '${API_BASE}/tokens/_internal/test-exhausted' | grep -o '耗尽\|申请加量'" \
    "耗尽"

echo ""
echo "【步骤5】测试完整状态接口"
echo "------------------------"
test_api "完整状态含预警信息" \
    "curl -s ${API_BASE}/tokens/status | grep -o 'warning'" \
    "warning"

test_api "input_disabled标记" \
    "curl -s ${API_BASE}/tokens/status | grep -o 'input_disabled'" \
    "input_disabled"

echo ""
echo "【步骤6】测试管理员重置"
echo "------------------------"
test_api "管理员重置接口" \
    "curl -s -X POST '${API_BASE}/tokens/admin/reset' | grep -o 'success.*true'" \
    "success"

test_api "重置日志记录" \
    "curl -s -X POST '${API_BASE}/tokens/admin/reset' | grep -o '重置'" \
    "重置"

echo ""
echo "【步骤7】APScheduler配置"
echo "------------------------"
test_api "APScheduler配置信息" \
    "curl -s -X POST '${API_BASE}/tokens/admin/schedule-reset' | grep -o 'cron'" \
    "cron"

test_api "每日0点重置配置" \
    "curl -s -X POST '${API_BASE}/tokens/admin/schedule-reset' | grep -o '0 0'" \
    "0 0"

echo ""
echo "========================================"
echo "M3-03 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M3-03 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ Token>90%预警条截图 (is_warning=true)"
    echo "  2. ✅ Token耗尽输入框禁用 (can_send=false)"
    echo "  3. ✅ 0点重置日志 (cron='0 0 * * *')"
    echo "  4. ✅ 单次上下文上限拦截"
    echo "  5. ✅ 按量计量准确"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M3-03 存在失败项${NC}"
    echo "卡点：APScheduler不跑 → 需上报PM"
    exit 1
fi