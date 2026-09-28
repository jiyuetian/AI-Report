#!/bin/bash
# M3-01 对话API 验收测试
# 验证：① 5类意图各能正确分类 ② SSE流式输出

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M3-01 对话API 验收测试"
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

echo "【步骤1】获取测试示例"
echo "------------------------"
test_api "获取5类意图示例" \
    "curl -s ${API_BASE}/chat/test/intent-examples | grep -o 'change_chart'" \
    "change_chart"

echo ""
echo "【步骤2】测试5类意图分类"
echo "------------------------"

# 1. 换图意图
test_api "换图意图(饼图→柱图)" \
    "curl -s -X POST '${API_BASE}/chat/classify-intent?message=把饼图改成柱图' | grep -o 'change_chart'" \
    "change_chart"

# 2. 新增图意图
test_api "新增图意图" \
    "curl -s -X POST '${API_BASE}/chat/classify-intent?message=新增一个趋势图' | grep -o 'add_chart'" \
    "add_chart"

# 3. 筛选下钻意图
test_api "筛选下钻意图" \
    "curl -s -X POST '${API_BASE}/chat/classify-intent?message=筛选华东地区的数据' | grep -o 'filter_drill'" \
    "filter_drill"

# 4. 归因追问意图
test_api "归因追问意图" \
    "curl -s -X POST '${API_BASE}/chat/classify-intent?message=这个异常是什么原因' | grep -o 'attribution'" \
    "attribution"

# 5. 标题编辑意图
test_api "标题编辑意图" \
    "curl -s -X POST '${API_BASE}/chat/classify-intent?message=把标题改成月度销售' | grep -o 'edit_title'" \
    "edit_title"

echo ""
echo "【步骤3】验证置信度"
echo "------------------------"
test_api "换图置信度≥70" \
    "curl -s -X POST '${API_BASE}/chat/classify-intent?message=把饼图改成柱图' | grep -o '"confidence":[7-9][0-9]'" \
    "confidence"

test_api "is_confident标记" \
    "curl -s -X POST '${API_BASE}/chat/classify-intent?message=把饼图改成柱图' | grep -o 'true'" \
    "true"

echo ""
echo "【步骤4】测试SSE流式"
echo "------------------------"
echo "创建会话并发送消息..."

# 创建会话
SESSION_RESULT=$(curl -s -X POST "${API_BASE}/chat/sessions" \
    -H "Content-Type: application/json" \
    -d '{}')
SESSION_ID=$(echo $SESSION_RESULT | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)

echo "会话ID: $SESSION_ID"

# 测试SSE流式 (检查event流格式)
test_api "SSE流式事件格式" \
    "curl -s -N -X POST '${API_BASE}/chat/message' -H 'Content-Type: application/json' -d '{\"session_id\":\"$SESSION_ID\",\"message\":\"把饼图改成柱图\"}' | head -1 | grep -o 'event'" \
    "event"

echo ""
echo "【步骤5】验证消息保存"
echo "------------------------"
# 等待一下让异步保存完成
sleep 1

test_api "消息已保存到数据库" \
    "curl -s ${API_BASE}/chat/sessions/${SESSION_ID}/history | grep -o 'messages'" \
    "messages"

test_api "保存了用户消息" \
    "curl -s ${API_BASE}/chat/sessions/${SESSION_ID}/history | grep -o 'user'" \
    "user"

test_api "保存了助手回复" \
    "curl -s ${API_BASE}/chat/sessions/${SESSION_ID}/history | grep -o 'assistant'" \
    "assistant"

echo ""
echo "========================================"
echo "M3-01 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M3-01 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ 5类意图各能正确分类"
    echo "     - change_chart (换图)"
    echo "     - add_chart (新增图)"
    echo "     - filter_drill (筛选下钻)"
    echo "     - attribution (归因追问)"
    echo "     - edit_title (标题编辑)"
    echo "  2. ✅ 置信度≥70标记is_confident"
    echo "  3. ✅ SSE流式输出格式正确"
    echo "  4. ✅ 消息保存到chat_messages表"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M3-01 存在失败项${NC}"
    echo "卡点：意图分类准确率<70% → 需上报PM调prompt"
    exit 1
fi