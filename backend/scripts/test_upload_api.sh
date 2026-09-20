#!/bin/bash
# M1-05a 文件上传接口测试脚本

API_BASE="http://localhost:8000/api/v1"

echo "========================================"
echo "M1-05a 文件上传接口测试"
echo "========================================"

# 测试1: 正常文件上传
echo ""
echo "[TEST 1] 正常文件上传"
echo "curl -X POST -F \"file=@test.xlsx\" ${API_BASE}/files"
curl -X POST -F "file=@test.xlsx" ${API_BASE}/files 2>/dev/null | jq .

# 测试2: 文件过大 (413)
echo ""
echo "[TEST 2] 文件过大 (139MB应返回413)"
echo "curl -X POST -F \"file=@large_file.xlsx\" ${API_BASE}/files"

# 测试3: 不支持的文件类型 (415)
echo ""
echo "[TEST 3] 不支持的文件类型 (应返回415)"
echo "curl -X POST -F \"file=@test.pdf\" ${API_BASE}/files"
curl -X POST -F "file=@test.pdf" ${API_BASE}/files 2>/dev/null | jq .

# 测试4: 健康检查
echo ""
echo "[TEST 4] 健康检查"
curl ${API_BASE}/health 2>/dev/null | jq .

echo ""
echo "========================================"
echo "测试完成"
echo "========================================"