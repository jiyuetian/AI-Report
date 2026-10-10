# ============================================================
# AI-Report 一键启动开发环境（Windows PowerShell 5 兼容）
# 用法（项目管理器右键「用 PowerShell 运行」，或终端执行）：
#     .\scripts\dev_up.ps1
# 说明：
#   1) 前置自检：Python 版本 / 依赖 / 端口占用 / DuckDB / 前端 node_modules
#   2) 启动后端 Uvicorn(:8000) + 前端 Vite(:5173)
#   3) 造双账号：管理员 + 普通用户（复用 backend/scripts/init_admin.py）
#   4) 打印账号与「下一步」提示
# 任一前置失败 → 明确报错 + 修复建议，不静默继续。
# 注意：不使用 &&（PowerShell 5 不支持），全部用 if/ try-catch。
# ============================================================
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$dataDuck = Join-Path $backendDir "data\duckdb\aibi.db"

$ADMIN_USER = "admin"
$ADMIN_PW   = "Admin@123456"
$NORMAL_USER = "demo_user"
$NORMAL_PW   = "Demo@123456"

function Test-PortFree($hostName, $port) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect($hostName, $port)
        $tcp.Close()
        return $false   # 端口被占用
    } catch {
        return $true    # 端口空闲
    }
}

function Fail($msg) {
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
    Write-Host "  → 修复建议见上方说明。" -ForegroundColor Yellow
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  AI-Report 一键启动（前置自检 + 启动）" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# ---- 1. Python 3.12 ----
Write-Host "[1/6] 检查 Python 版本（必须 3.12）..." -ForegroundColor Cyan
$pyOk = $false
try {
    $pv = & py -3.12 --version 2>&1
    if ($pv -match "3\.12") { $pyOk = $true }
} catch { }
if (-not $pyOk) {
    Fail "未找到 py -3.12（当前默认 python 若为 3.10 会误报编译/运行错误）。请安装 Python 3.12 并确保在 PATH，或使用 py 启动器选择 3.12。"
}
Write-Host "  [OK] $pv" -ForegroundColor Green

# ---- 2. 依赖 ----
Write-Host "[2/6] 检查后端依赖（fastapi/sqlalchemy/uvicorn/duckdb）..." -ForegroundColor Cyan
$depErr = $null
try {
    & py -3.12 -c "import fastapi, sqlalchemy, uvicorn, duckdb" 2>&1 | Out-Null
} catch {
    $depErr = $_
}
if ($depErr -ne $null) {
    Fail "后端依赖缺失（fastapi/sqlalchemy/uvicorn/duckdb 之一）。请在 backend 目录执行：py -3.12 -m pip install -r requirements.txt"
}
Write-Host "  [OK] 核心依赖可用" -ForegroundColor Green

# ---- 3. 端口占用 ----
Write-Host "[3/6] 检查端口 8000 / 5173 是否空闲..." -ForegroundColor Cyan
if (-not (Test-PortFree "127.0.0.1" 8000)) {
    Fail "端口 8000 已被占用（可能上一次后端未关闭）。请先关闭占用进程（如：任务管理器结束 uvicorn / AI-Report 后端窗口）。"
}
if (-not (Test-PortFree "127.0.0.1" 5173)) {
    Fail "端口 5173 已被占用（可能上一次前端未关闭）。请先关闭占用进程（如：结束 npm/vite 进程）。"
}
Write-Host "  [OK] 8000 / 5173 均空闲" -ForegroundColor Green

# ---- 4. DuckDB 文件 ----
Write-Host "[4/6] 检查 DuckDB 业务库是否存在..." -ForegroundColor Cyan
if (-not (Test-Path $dataDuck)) {
    Write-Host "  [WARN] 未找到 $dataDuck" -ForegroundColor Yellow
    Write-Host "  → 后端会用 DuckDB 自动建库（首次启动可能无样例数据）。如需样例，先跑 scripts/make_demo_db.py。" -ForegroundColor Yellow
} else {
    Write-Host "  [OK] 业务库存在: $dataDuck" -ForegroundColor Green
}

# ---- 5. 前端 node_modules ----
Write-Host "[5/6] 检查前端依赖（node_modules）..." -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Fail "前端未安装依赖（frontend/node_modules 缺失）。请先在 frontend 目录执行：npm install"
}
Write-Host "  [OK] 前端 node_modules 存在" -ForegroundColor Green

# ---- 6. 造双账号 ----
Write-Host "[6/6] 创建 / 重置双账号（管理员 + 普通用户）..." -ForegroundColor Cyan
Push-Location $backendDir
try {
    & py -3.12 scripts/init_admin.py $ADMIN_USER $ADMIN_PW
    & py -3.12 scripts/init_admin.py $NORMAL_USER $NORMAL_PW --normal
} catch {
    Write-Host "  [WARN] 账号创建失败（可能数据库未初始化或连接异常）：$_" -ForegroundColor Yellow
} finally {
    Pop-Location
}

# ---- 启动后端 ----
Write-Host ">>> 启动后端 Uvicorn (port 8000) ..." -ForegroundColor Cyan
$bePsi = New-Object System.Diagnostics.ProcessStartInfo
$bePsi.FileName = "py"
$bePsi.Arguments = "-3.12 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
$bePsi.WorkingDirectory = $backendDir
$bePsi.UseShellExecute = $true
$bePsi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
[System.Diagnostics.Process]::Start($bePsi) | Out-Null

Start-Sleep -Seconds 3

# ---- 启动前端 ----
Write-Host ">>> 启动前端 Vite (port 5173) ..." -ForegroundColor Cyan
$fePsi = New-Object System.Diagnostics.ProcessStartInfo
$fePsi.FileName = "npm"
$fePsi.Arguments = "run dev"
$fePsi.WorkingDirectory = $frontendDir
$fePsi.UseShellExecute = $true
$fePsi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
[System.Diagnostics.Process]::Start($fePsi) | Out-Null

# ---- 完成提示 ----
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  启动完成！" -ForegroundColor Green
Write-Host "  后端: http://127.0.0.1:8000   (API 文档 /docs)" -ForegroundColor Green
Write-Host "  前端: http://localhost:5173" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "  管理员账号 : $ADMIN_USER / $ADMIN_PW" -ForegroundColor Yellow
Write-Host "  普通用户账号: $NORMAL_USER / $NORMAL_PW" -ForegroundColor Yellow
Write-Host ""
Write-Host "  · 管理员登录后可见：AI 调用日志、AI 参与/失败信息、使用统计（night40 已收口）。" -ForegroundColor White
Write-Host "  · 普通用户登录后只见：报表效果，无 AI 技术信息（保持界面干净）。" -ForegroundColor White
Write-Host "  · 验收清单见 docs/project_record/night_runs/night42/ACCEPTANCE_CHECKLIST.md" -ForegroundColor White
Write-Host "  · 全链路冒烟：py -3.12 scripts/smoke_full.py   （需后端已启动）" -ForegroundColor White
Write-Host "  · 环境自检：  py -3.12 scripts/doctor.py" -ForegroundColor White
Write-Host ""
Write-Host "  关闭请直接关掉对应的命令行窗口（后端/前端各一个）。" -ForegroundColor Yellow
