# 04 · 运行手册（RUNBOOK）· v2

> 本机陷阱见 `05_KNOWN_TRAPS.md`。所有 Git 操作用 `git.exe -C "<绝对路径>"`（陷阱 1）。
> **代理 7897 已永久配置**（`netsh winhttp` + `HKLM\...\4073` 双写），不再需要每次 `set https_proxy`。

## 1. 起后端

```powershell
# 绝对路径，PowerShell 用 & 前缀调可执行
& 'C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe' `
  'C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend/run_backend.py'
```

- 端口 8000；B5 单实例守卫（重复起会拒，先查 `backend/.backend.pid`）。
- 启动自检：DuckDB fail-fast——库缺失 → `[DUCKDB-FAIL]` 退出；表=0 → 告警；正常 → 打印 `ds_*` 表数。
- LLM 网关：6 层 provider 已配好；网关要求 `business_type=chat`、kimi 系列 `temperature=1`。

## 2. 起前端

```powershell
cd 'C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/frontend'
& 'C:/Users/Asus009/.workbuddy/binaries/node/versions/22.22.2-3/node.exe' node_modules/.bin/vite
# 或 npm run dev
```

- 端口 5173；`npm run build` 产出 `dist/`。

## 3. 阶段 5 测试（push 前必过）

### 3.1 编译

```powershell
# 后端
& 'C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe' -m py_compile 'backend/app/**/*.py'
# 前端类型
cd frontend ; npx tsc --noEmit
```

### 3.2 基线回归（`_verify_*.py` 系列，零 DB，秒级）

```powershell
$PY = 'C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe'
& $PY 'backend/_verify_taskg.py'   # Task G CRUD  14/14
& $PY 'backend/_verify_taski.py'   # Task H/I 派生+重算  32/32
& $PY 'backend/_verify_taskjk.py'  # Task J/K 使用统计+联调  17/17
& $PY 'backend/_verify_iss058.py'  # ISS-058 阈值调整  35/35
```

### 3.3 接口冒烟

- `GET /health` → 200
- 前端 `GET http://localhost:5173` → 200
- AI 对话真跑：发一条「把阈值调 80%」，确认绿标 + 看板变化 + 撤销闭环

## 4. 备份（改数据模型前必做）

```powershell
# 1) 停后端（taskkill 强杀）
taskkill /F /IM python.exe   # 或按 PID
# 2) 备份真相库 + wal（date 用 Python 生成时间戳，避免 date shim 缺失）
& $PY -c "import datetime,shutil; ts=datetime.datetime.now().strftime('%Y%m%d_%H%M%S'); shutil.copy('backend/data/duckdb/aibi.db', f'backend/data/backups/aibi_{ts}.db'); shutil.copy('backend/data/duckdb/aibi.db.wal', f'backend/data/backups/aibi_{ts}.db.wal'); shutil.copy('backend/data/aibi.db', f'backend/data/backups/meta_{ts}.db'); print(ts)"
# 3) 校验大小
```

## 5. 回滚

- 任何 DDL/迁移改动，先写回滚脚本（反向 DDL）。
- 若改坏：从 `backend/data/backups/` 还原 `.db`+`.wal`，重启后端。
- Git 层面：`git.exe -C "<绝对路径>" revert <commit>`；不要 `reset --hard` 共享分支。

## 6. 提交纪律（红线）

```powershell
git.exe -C 'C:\Users\Asus009\Desktop\临时\ai大赛\AI-Report' status -sb
git.exe -C 'C:\Users\Asus009\Desktop\临时\ai大赛\AI-Report' add <具体文件>   # 禁 git add -A
git.exe -C 'C:\Users\Asus009\Desktop\临时\ai大赛\AI-Report' commit -m "feat/fix/docs: 一类一说明"
git.exe -C 'C:\Users\Asus009\Desktop\临时\ai大赛\AI-Report' push origin p0-security-fixes
git.exe -C 'C:\Users\Asus009\Desktop\临时\ai大赛\AI-Report' rev-list --count origin/p0-security-fixes..HEAD   # 应为 0
```

## 7. 代理配置（已永久化，仅需知悉）

```powershell
# 已执行，无需每次调用：
# netsh winhttp set proxy 127.0.0.1:7897
# reg add HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings\4073 /v ProxyServer /t REG_SZ /d "127.0.0.1:7897" /f
# 验证：
# netsh winhttp show proxy
```

若日后需要改回直连：
```powershell
netsh winhttp reset proxy
reg delete HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings\4073 /v ProxyServer /f
```

## 8. 常用 git 命令（Git-Bash shim 陷阱规避）

| 需求 | 命令 |
|------|------|
| 状态 | `git.exe -C '<路径>' status -sb` |
| 差异 | `git.exe -C '<路径>' diff --stat` |
| 日志 | `git.exe -C '<路径>' log --oneline -20` |
| 拉取 | `git.exe -C '<路径>' pull --ff-only` |
| 强制同步（慎用）| `git.exe -C '<路径>' reset --hard origin/p0-security-fixes` |
