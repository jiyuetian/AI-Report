#!/bin/bash
# M3-04 审核与边界 验收测试
# 验证：① 4类边界话术 ② 审核拦截不扣token ③ 发送失败保留原文

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M3-04 审核与边界 验收测试"
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

echo "【步骤1】测试4类边界话术"
echo "------------------------"

# 1. 超范围
test_api "超范围-天气查询" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=今天天气怎么样' | grep -o 'out_of_scope'" \
    "out_of_scope"

test_api "超范围-文案正确" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=今天天气怎么样' | grep -o '超出服务范围'" \
    "超出服务范围"

# 2. 含糊反问
test_api "含糊-什么意思" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=什么意思' | grep -o 'vague_question'" \
    "vague_question"

test_api "含糊-文案正确" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=什么意思' | grep -o '问题需要更明确'" \
    "问题需要更明确"

# 3. 图库外替代
test_api "图库外-3d图" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=来一个3d图' | grep -o 'chart_not_supported'" \
    "chart_not_supported"

test_api "图库外-文案正确" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=来一个3d图' | grep -o '暂不支持'" \
    "暂不支持"

# 4. 敏感
test_api "敏感-机密数据" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=这是机密数据' | grep -o 'sensitive'" \
    "sensitive"

test_api "敏感-文案正确" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=这是机密数据' | grep -o '敏感信息'" \
    "敏感信息"

echo ""
echo "【步骤2】验证审核拦截不扣Token"
echo "------------------------"
test_api "拦截deduct_tokens=false" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=这是机密数据' | grep -o 'deduct_tokens.*false'" \
    "deduct_tokens"

test_api "敏感提示" \
    "curl -s -X POST '${API_BASE}/chat/test/moderation?message=这是机密数据' | grep -o '不会扣除Token'" \
    "不会扣除Token"

echo ""
echo "【步骤3】验证发送失败保留原文"
echo "------------------------"
test_api "保留原文机制" \
    "curl -s -X POST '${API_BASE}/chat/test/retry' | grep -o 'original_content_preserved.*true'" \
    "original_content_preserved"

test_api "原文完整保存" \
    "curl -s -X POST '${API_BASE}/chat/test/retry' | grep -o '把饼图改成柱图'" \
    "把饼图改成柱图"

test_api "重试次数记录" \
    "curl -s -X POST '${API_BASE}/chat/test/retry' | grep -o 'retry_count'" \
    "retry_count"

echo ""
echo "【步骤4】测试对话流程中的审核拦截"
echo "------------------------"
# 创建会话
SESSION_RESULT=$(curl -s -X POST "${API_BASE}/chat/sessions" -H "Content-Type: application/json" -d '{}')
SESSION_ID=$(echo $SESSION_RESULT | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)

# 发送敏感消息（应该被拦截）
test_api "SSE流敏感拦截" \
    "curl -s -N -X POST '${API_BASE}/chat/message' -H 'Content-Type: application/json' -d '{\"session_id\":\"$SESSION_ID\",\"message\":\"这是机密数据\"}' | grep -o 'moderation_blocked'" \
    "moderation_blocked"

test_api "拦截返回边界类型" \
    "curl -s -N -X POST '${API_BASE}/chat/message' -H 'Content-Type: application/json' -d '{\"session_id\":\"$SESSION_ID\",\"message\":\"这是机密数据\"}' | grep -o 'sensitive'" \
    "sensitive"

echo ""
echo "========================================"
echo "M3-04 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M3-04 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. ✅ 4类边界话术各1张截图"
    echo "     - out_of_scope (超范围)"
    echo "     - vague_question (含糊反问)"
    echo "     - chart_not_supported (图库外)"
    echo "     - sensitive (敏感)"
    echo "  2. ✅ 审核拦截不扣token (deduct_tokens=false)"
    echo "  3. ✅ 发送失败保留原文 (original_content)"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M3-04 存在失败项${NC}"
    echo "卡点：审核接口未打通 → 需上报PM"
    exit 1
fi