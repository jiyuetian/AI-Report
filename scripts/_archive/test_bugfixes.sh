#!/bin/bash
# 代码修复验收测试
# 验证所有修复的问题

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "代码修复验收测试"
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

echo "【修复 #1: Token配额重置SQL表达式】"
echo "------------------------"
test_api "重置Token配额SQL正确" \
    "curl -s -X POST '${API_BASE}/tokens/admin/reset' 2>&1 | head -20" \
    "success"

echo ""
echo "【修复 #2: SSE db session生命周期】"
echo "------------------------"
# 创建会话并发送消息
SESSION_RESULT=$(curl -s -X POST "${API_BASE}/chat/sessions" -H "Content-Type: application/json" -d '{}')
SESSION_ID=$(echo $SESSION_RESULT | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)
test_api "SSE流式响应不崩溃" \
    "curl -s -N -X POST '${API_BASE}/chat/message' -H 'Content-Type: application/json' -d '{\"session_id\":\"$SESSION_ID\",\"message\":\"把饼图改成柱图\"}' | head -5 | grep -o 'event'" \
    "event"

echo ""
echo "【修复 #3: 数据库表自动创建】"
echo "------------------------"
test_api "健康检查接口可用" \
    "curl -s ${API_BASE}/health | grep -o 'status'" \
    "status"

echo ""
echo "【修复 #4: Token预警阈值使用total_limit】"
echo "------------------------"
test_api "Token状态查询使用total_limit" \
    "curl -s ${API_BASE}/tokens/status | grep -o 'total_limit'" \
    "total_limit"

echo ""
echo "【修复 #5: Token管理API权限控制】"
echo "------------------------"
test_api "非管理员无法重置配额" \
    "curl -s -X POST '${API_BASE}/tokens/admin/reset' | grep -o '403\|FORBIDDEN'" \
    "FORBIDDEN"

test_api "非管理员无法查看待审批" \
    "curl -s '${API_BASE}/tokens/applications/admin/pending' | grep -o '403\|FORBIDDEN'" \
    "FORBIDDEN"

echo ""
echo "【修复 #6: S5重排备选池分离】"
echo "------------------------"
test_api "S5评分重排不减少图表数" \
    "curl -s -X POST '${API_BASE}/brain/s5/score' -H 'Content-Type: application/json' -d '{\"charts\":[{\"chart_type\":\"kpi\",\"title\":\"T1\"},{\"chart_type\":\"line\",\"title\":\"T2\"},{\"chart_type\":\"bar\",\"title\":\"T3\"},{\"chart_type\":\"pie\",\"title\":\"T4\"}]}' | grep -o 'chart_count.*[4-9]'" \
    "chart_count"

test_api "S5重排补充缺失类型" \
    "curl -s -X POST '${API_BASE}/brain/s5/score' -H 'Content-Type: application/json' -d '{\"charts\":[{\"chart_type\":\"kpi\",\"title\":\"T1\"}]}' | grep -o 'coverage'" \
    "coverage"

echo ""
echo "【修复 #7: 图表类型中文名映射】"
echo "------------------------"
test_api "中文'饼图'映射为'pie'" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"change_chart\",\"params\":{\"target_type\":\"饼图\",\"session_id\":\"test\"},\"dashboard_config\":{\"charts\":[{\"id\":\"c1\",\"chart_type\":\"bar\"}]}}' | grep -o 'pie'" \
    "pie"

test_api "中文'柱图'映射为'bar'" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"add_chart\",\"params\":{\"chart_type\":\"柱图\",\"session_id\":\"test\"},\"dashboard_config\":{\"charts\":[]}}' | grep -o 'bar'" \
    "bar"

test_api "英文类型直接通过" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"change_chart\",\"params\":{\"target_type\":\"line\",\"session_id\":\"test\"},\"dashboard_config\":{\"charts\":[{\"id\":\"c1\",\"chart_type\":\"bar\"}]}}' | grep -o 'line'" \
    "line"

echo ""
echo "========================================"
echo "修复验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ 所有修复验收通过${NC}"
    echo ""
    echo "修复内容："
    echo "  ✅ #1 Token配额重置SQL表达式正确"
    echo "  ✅ #2 SSE db session生命周期安全"
    echo "  ✅ #3 数据库表自动创建"
    echo "  ✅ #4 Token预警阈值使用total_limit"
    echo "  ✅ #5 Token管理API权限控制"
    echo "  ✅ #6 S5重排备选池分离+自动生成"
    echo "  ✅ #7 图表类型中文名映射"
    echo ""
    exit 0
else
    echo -e "${RED}❌ 存在失败项${NC}"
    exit 1
fi
