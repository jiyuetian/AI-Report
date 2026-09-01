#!/bin/bash
# AI快速BI报表工具 - 一键打包脚本
# 执行后生成 ai-bi-report-v2.0.01-M1.zip

echo "========================================"
echo "  AI快速BI报表工具 M1 打包工具"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE_NAME="ai-bi-report-v2.0.01-M1"
ZIP_FILE="${PROJECT_DIR}/${RELEASE_NAME}.zip"

echo -e "${YELLOW}正在打包...${NC}"
echo "项目目录: ${PROJECT_DIR}"
echo "输出文件: ${ZIP_FILE}"
echo ""

# 创建临时目录
TEMP_DIR=$(mktemp -d)
RELEASE_DIR="${TEMP_DIR}/${RELEASE_NAME}"
mkdir -p "${RELEASE_DIR}"

# 复制核心文件
echo "复制后端文件..."
mkdir -p "${RELEASE_DIR}/backend"
cp -r "${PROJECT_DIR}/backend/app" "${RELEASE_DIR}/backend/" 2>/dev/null || true
cp "${PROJECT_DIR}/backend/requirements.txt" "${RELEASE_DIR}/backend/" 2>/dev/null || true
cp "${PROJECT_DIR}/backend/Dockerfile" "${RELEASE_DIR}/backend/" 2>/dev/null || true
cp "${PROJECT_DIR}/backend/pyproject.toml" "${RELEASE_DIR}/backend/" 2>/dev/null || true

echo "复制前端文件..."
mkdir -p "${RELEASE_DIR}/frontend"
cp -r "${PROJECT_DIR}/frontend/src" "${RELEASE_DIR}/frontend/" 2>/dev/null || true
cp "${PROJECT_DIR}/frontend/package.json" "${RELEASE_DIR}/frontend/" 2>/dev/null || true
cp "${PROJECT_DIR}/frontend/Dockerfile" "${RELEASE_DIR}/frontend/" 2>/dev/null || true
cp "${PROJECT_DIR}/frontend/tsconfig.json" "${RELEASE_DIR}/frontend/" 2>/dev/null || true

echo "复制配置文件..."
cp "${PROJECT_DIR}/docker-compose.yml" "${RELEASE_DIR}/" 2>/dev/null || true
cp "${PROJECT_DIR}/README.md" "${RELEASE_DIR}/" 2>/dev/null || true

echo "复制文档..."
mkdir -p "${RELEASE_DIR}/docs"
cp "${PROJECT_DIR}"/*.md "${RELEASE_DIR}/docs/" 2>/dev/null || true

echo "复制脚本..."
mkdir -p "${RELEASE_DIR}/scripts"
cp "${PROJECT_DIR}/scripts"/*.sh "${RELEASE_DIR}/scripts/" 2>/dev/null || true

echo "复制测试数据..."
mkdir -p "${RELEASE_DIR}/test_data"
cp "${PROJECT_DIR}/test_data"/* "${RELEASE_DIR}/test_data/" 2>/dev/null || true

# 生成启动脚本
cat > "${RELEASE_DIR}/启动服务.sh" << 'EOFSCRIPT'
#!/bin/bash
echo "========================================"
echo "  AI快速BI报表工具 v2.0.01 M1"
echo "========================================"
echo ""

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "错误: Docker Compose未安装"
    exit 1
fi

echo "正在启动服务..."
docker-compose up -d --build

echo ""
echo "等待服务启动..."
sleep 30

echo ""
echo -e "\033[0;32m✅ 服务已启动\033[0m"
echo ""
echo "访问地址:"
echo "  前端界面: http://localhost:3000"
echo "  后端API:  http://localhost:8000"
echo "  API文档:  http://localhost:8000/docs"
echo ""
echo "测试命令:"
echo "  curl http://localhost:8000/api/v1/health"
echo ""
EOFSCRIPT
chmod +x "${RELEASE_DIR}/启动服务.sh"

# 打包
echo ""
echo "正在压缩..."
cd "${TEMP_DIR}"
zip -r "${ZIP_FILE}" "${RELEASE_NAME}" \
    -x "*.pyc" \
    -x "*/__pycache__/*" \
    -x "*/node_modules/*" \
    -x "*/.git/*" \
    -x "*/dist/*" \
    -x "*/build/*"

# 清理临时目录
rm -rf "${TEMP_DIR}"

# 显示结果
echo ""
echo "========================================"
echo -e "${GREEN}✅ 打包完成!${NC}"
echo "========================================"
echo ""
ls -lh "${ZIP_FILE}"
echo ""
echo "包名: ${RELEASE_NAME}.zip"
echo "位置: ${ZIP_FILE}"
echo ""
echo "您可以通过以下方式下载:"
echo "1. SFTP/SCP: scp user@server:'${ZIP_FILE}' ./"
echo "2. FileBrowser: http://your-server:8080"
echo "3. 直接复制到HTTP目录: cp '${ZIP_FILE}' /var/www/html/"
echo ""
