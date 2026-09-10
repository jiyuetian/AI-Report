# ============================================================
# AI-Report 一键启动开发环境（Windows）
# 用法：在项目管理器右键「用 PowerShell 运行」，或终端执行 .\start_dev.ps1
# 说明：分别在 backend / frontend 后台启动 Uvicorn 与 Vite
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Start-Backend {
    Write-Host ">>> 启动后端 Uvicorn (port 8000) ..." -ForegroundColor Cyan
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "python"
    $psi.Arguments = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
    $psi.WorkingDirectory = Join-Path $root "backend"
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    [System.Diagnostics.Process]::Start($psi) | Out-Null
}

function Start-Frontend {
    Write-Host ">>> 启动前端 Vite (port 5173) ..." -ForegroundColor Cyan
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "npm"
    $psi.Arguments = "run dev"
    $psi.WorkingDirectory = Join-Path $root "frontend"
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    [System.Diagnostics.Process]::Start($psi) | Out-Null
}

Start-Backend
Start-Sleep -Seconds 2
Start-Frontend

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " 后端:  http://127.0.0.1:8000   (文档 /docs)" -ForegroundColor Green
Write-Host " 前端:  http://localhost:5173" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "关闭请直接关掉对应的命令行窗口。" -ForegroundColor Yellow
