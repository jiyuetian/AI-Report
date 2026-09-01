#!/bin/bash
# M2-01 验收测试脚本
# 验证：① 改配置不重启生效 ② brain_traces 5阶段落库

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M2-01 大脑配置中心 验收测试"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

passed=0
failed=0

# 测试函数
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

echo "【步骤1】初始化默认配置"
echo "------------------------"
test_api "初始化配置" \
    "curl -s -X POST ${API_BASE}/brain/_internal/init-configs | grep -o 'success'" \
    "success"

echo ""
echo "【步骤2】查询配置（热更新缓存测试）"
echo "------------------------"
test_api "查询主题词典" \
    "curl -s ${API_BASE}/brain/configs/theme_dict | grep -o 'config'" \
    "config"

test_api "查询评分权重" \
    "curl -s ${API_BASE}/brain/configs/score_weights | grep -o 'weights'" \
    "weights"

echo ""
echo "【步骤3】更新配置（热更新）"
echo "------------------------"
test_api "更新配置（不重启）" \
    "curl -s -X POST ${API_BASE}/brain/configs -H 'Content-Type: application/json' -d '{\"config_key\":\"score_weights\",\"category\":\"score\",\"content\":{\"weights\":{\"redundancy\":0.4,\"coverage\":0.3,\"narrative\":0.3},\"pass_threshold\":75,\"max_retries\":3},\"description\":\"更新后的评分权重\"}' | grep -o '热更新生效'" \
    "热更新生效"

echo ""
echo "【步骤4】验证更新后立即生效"
echo "------------------------"
test_api "验证新配置生效" \
    "curl -s ${API_BASE}/brain/configs/score_weights | grep -o '75'" \
    "75"

echo ""
echo "【步骤5】配置版本历史"
echo "------------------------"
test_api "查询版本历史" \
    "curl -s ${API_BASE}/brain/configs/score_weights/history | grep -o 'version_count'" \
    "version_count"

echo ""
echo "【步骤6】Trace 5阶段落库测试"
echo "------------------------"

# 开始一次运行
RUN_RESULT=$(curl -s -X POST ${API_BASE}/brain/trace/run/start \
    -H "Content-Type: application/json" \
    -d '{"dataset_id":"ds_test_001","user_id":"test_user"}')
RUN_ID=$(echo $RUN_RESULT | grep -o '"run_id":"[^"]*"' | cut -d'"' -f4)
echo "创建运行: run_id=$RUN_ID"

# S1 - 主题识别
test_api "S1 主题识别开始" \
    "curl -s -X POST ${API_BASE}/brain/trace/stage/start -H 'Content-Type: application/json' -d '{\"run_id\":\"$RUN_ID\",\"dataset_id\":\"ds_test_001\",\"stage\":\"S1\",\"stage_input\":{\"fields\":[\"担保金额\",\"抵押率\"]}}' | grep -o 'S1'" \
    "S1"

test_api "S1 主题识别完成" \
    "curl -s -X POST ${API_BASE}/brain/trace/stage/complete -H 'Content-Type: application/json' -d '{\"trace_id\":\"$(curl -s -X POST ${API_BASE}/brain/trace/stage/start -H '"'"'Content-Type: application/json'"'"' -d '"'"'{"run_id":"'$RUN_ID'","dataset_id":"ds_test_001","stage":"S1","stage_input":{"fields":["担保金额","抵押率"]}}'"'"' | grep -o '"'"'trace_id":"[^"]*"'"'"' | head -1 | cut -d'"'"'"'"' -f4)\",\"stage_output\":{\"theme_tag\":\"担保风控\",\"confidence\":0.95}}' | grep -o 'completed'" \
    "completed"

# S2 - 目标生成
test_api "S2 目标生成" \
    "curl -s -X POST ${API_BASE}/brain/trace/stage/start -H 'Content-Type: application/json' -d '{\"run_id\":\"$RUN_ID\",\"dataset_id\":\"ds_test_001\",\"stage\":\"S2\",\"stage_input\":{\"theme\":\"担保风控\"}}' | grep -o 'S2'" \
    "S2"

# S3 - 图表推荐
test_api "S3 图表推荐" \
    "curl -s -X POST ${API_BASE}/brain/trace/stage/start -H 'Content-Type: application/json' -d '{\"run_id\":\"$RUN_ID\",\"dataset_id\":\"ds_test_001\",\"stage\":\"S3\",\"stage_input\":{\"goals\":6}}' | grep -o 'S3'" \
    "S3"

# S4 - 编排
test_api "S4 编排" \
    "curl -s -X POST ${API_BASE}/brain/trace/stage/start -H 'Content-Type: application/json' -d '{\"run_id\":\"$RUN_ID\",\"dataset_id\":\"ds_test_001\",\"stage\":\"S4\",\"stage_input\":{\"charts\":5}}' | grep -o 'S4'" \
    "S4"

# S5 - 评分
test_api "S5 评分" \
    "curl -s -X POST ${API_BASE}/brain/trace/stage/start -H 'Content-Type: application/json' -d '{\"run_id\":\"$RUN_ID\",\"dataset_id\":\"ds_test_001\",\"stage\":\"S5\",\"stage_input\":{\"dashboard_id\":\"dash_001\"}}' | grep -o 'S5'" \
    "S5"

# 完成运行
test_api "完成运行" \
    "curl -s -X POST ${API_BASE}/brain/trace/run/complete -H 'Content-Type: application/json' -d '{\"run_id\":\"$RUN_ID\",\"dashboard_id\":\"dash_001\",\"final_score\":85,\"passed\":true}' | grep -o 'completed'" \
    "completed"

echo ""
echo "【步骤7】验证Trace落库"
echo "------------------------"
test_api "查询运行Trace" \
    "curl -s ${API_BASE}/brain/trace/$RUN_ID | grep -o 'stage_count'" \
    "stage_count"

test_api "验证5阶段都有记录" \
    "curl -s ${API_BASE}/brain/trace/$RUN_ID | grep -o 'S1.*S2.*S3.*S4.*S5'" \
    "S1"

echo ""
echo "========================================"
echo "M2-01 验收测试汇总"
echo "========================================"
echo -e "通过: ${GREEN}${passed}${NC}"
echo -e "失败: ${RED}${failed}${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ M2-01 验收通过${NC}"
    echo ""
    echo "验收证据："
    echo "  1. 改配置不重启生效 ✅"
    echo "  2. brain_traces 5阶段落库 ✅"
    echo ""
    exit 0
else
    echo -e "${RED}❌ M2-01 存在失败项${NC}"
    exit 1
fi