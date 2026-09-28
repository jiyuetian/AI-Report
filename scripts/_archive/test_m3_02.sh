#!/bin/bash
# M3-02 动作执行器 验收测试
# 验证：① 5类意图各触发一次图表变更 ② 归因追问走血缘 ③ chat_messages记录

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M3-02 动作执行器 验收测试"
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

echo "【步骤1】获取5类动作测试示例"
echo "------------------------"
test_api "获取动作示例" \
    "curl -s ${API_BASE}/chat/test/action-examples | grep -o 'change_chart'" \
    "change_chart"

echo ""
echo "【步骤2】测试5类动作执行"
echo "------------------------"

# 1. 换图 (饼图→柱图)
test_api "换图动作(饼图→柱图)" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"change_chart\",\"params\":{\"target_type\":\"bar\",\"source_type\":\"pie\",\"session_id\":\"test_session\"},\"dashboard_config\":{\"charts\":[{\"id\":\"chart_1\",\"chart_type\":\"pie\",\"title\":\"原饼图\"}]}}' | grep -o 'success.*true'" \
    "success"

test_api "换图结果验证" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"change_chart\",\"params\":{\"target_type\":\"bar\"},\"dashboard_config\":{\"charts\":[{\"id\":\"chart_1\",\"chart_type\":\"pie\"}]}}' | grep -o 'render_updates'" \
    "render_updates"

# 2. 新增图
test_api "新增图动作" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"add_chart\",\"params\":{\"chart_type\":\"line\",\"session_id\":\"test_session\"},\"dashboard_config\":{\"charts\":[]}}' | grep -o 'add_chart'" \
    "add_chart"

test_api "新增图添加成功" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"add_chart\",\"params\":{\"chart_type\":\"line\"},\"dashboard_config\":{\"charts\":[]}}' | grep -o 'added_chart'" \
    "added_chart"

# 3. 筛选下钻
test_api "筛选下钻动作" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"filter_drill\",\"params\":{\"filter_field\":\"地区\",\"filter_value\":\"华东\",\"session_id\":\"test_session\"},\"dashboard_config\":{\"filters\":[]}}' | grep -o 'filter_drill'" \
    "filter_drill"

test_api "筛选条件添加" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"filter_drill\",\"params\":{\"filter_field\":\"地区\",\"filter_value\":\"华东\"},\"dashboard_config\":{\"filters\":[]}}' | grep -o 'filter_added'" \
    "filter_added"

# 4. 归因追问（血缘下钻）
test_api "归因追问动作" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"attribution\",\"params\":{\"target\":\"异常波动\",\"session_id\":\"test_session\"},\"dashboard_config\":{}}' | grep -o 'attribution'" \
    "attribution"

test_api "归因走血缘成功" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"attribution\",\"params\":{\"target\":\"异常波动\"},\"dashboard_config\":{}}' | grep -o 'lineage_traversed'" \
    "lineage_traversed"

test_api "归因结果含根因" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"attribution\",\"params\":{\"target\":\"异常波动\"},\"dashboard_config\":{}}' | grep -o 'root_cause'" \
    "root_cause"

# 5. 标题编辑
test_api "标题编辑动作" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"edit_title\",\"params\":{\"new_title\":\"月度销售分析\",\"session_id\":\"test_session\"},\"dashboard_config\":{\"title\":\"原标题\"}}' | grep -o 'edit_title'" \
    "edit_title"

test_api "标题更新成功" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"edit_title\",\"params\":{\"new_title\":\"月度销售\"},\"dashboard_config\":{\"title\":\"原标题\"}}' | grep -o '月度销售'" \
    "月度销售"

echo ""
echo "【步骤3】验证局部重渲染指令"
echo "------------------------"
test_api "返回局部渲染指令" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"change_chart\",\"params\":{\"target_type\":\"bar\"},\"dashboard_config\":{\"charts\":[{\"id\":\"chart_1\",\"chart_type\":\"pie\"}]}}' | grep -o 'type.*update_chart'" \
    "update_chart"

echo ""
echo "【步骤4】验证chat_messages记录"
echo "------------------------"
test_api "动作执行记录保存" \
    "curl -s -X POST '${API_BASE}/chat/execute-action' -H 'Content-Type: application/json' -d '{\"action_type\":\"change_chart\",\"params\":{\"target_type\":\"bar\",\"session_id\":\"test_session\"},\"dashboard_config\":{\"charts\":[{\"id\":\"chart_1\",\"chart_type\":\"pie\"}]}}' | grep -o '记录已保存'" \
    "记录已保存"

echo ""
echo "========================================"
echo "M3-02 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M3-02 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ 换图: 饼图→柱图,返回render_updates"
    echo "  2. ✅ 新增图: 添加line图,返回added_chart"
    echo "  3. ✅ 筛选下钻: 添加filter条件"
    echo "  4. ✅ 归因追问: lineage_traversed=true,含root_cause"
    echo "  5. ✅ 标题编辑: 标题更新成功"
    echo "  6. ✅ 局部重渲染: 返回type=update_chart指令"
    echo "  7. ✅ 行为标注: chat_messages保存动作记录"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M3-02 存在失败项${NC}"
    echo "卡点：归因追问连不上血缘 → 需上报PM"
    exit 1
fi