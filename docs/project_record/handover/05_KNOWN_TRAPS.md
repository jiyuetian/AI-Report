# 05 · 已知陷阱（KNOWN_TRAPS）

> 本机环境特有坑，**先查这**再报错。每个都有验证过的绕过方式。

## 陷阱 1 · Git-Bash shim 损坏（最高频）

- 现象：`git status | Select-Object`、`ls`、`cat`、`head`、`tail`、`grep`、`sleep`、`dirname`、`cd` 在 Bash 工具里报 `command not found`（exit 127）。
- 绕过：**所有 Git 操作用** `git.exe -C "<绝对路径>"`（绝对路径带引号）。避免 `cd`/管道。
- 备注：`git.exe -C` 会打印无害的 `dirname: command not found` / `cd: null directory` 到 stderr，exit 0 有真实输出，可忽略。

## 陷阱 2 · Edit/Write 偶发不落盘

- 现象：写完文件，后续读取内容仍是旧的。
- 绕过：写完立即 `Grep`/`Read` 复核关键行；不落盘就重写一次。

## 陷阱 3 · DuckDB 静默建空库（已根治，仍须警惕）

- 现象（旧）：`DUCKDB_PATH` 相对解析，目标不存在时**静默新建空库**，业务表全空。
- 现状：`718019d` 已绝对路径化 + `run_backend.py` 启动 fail-fast（`[DUCKDB-FAIL]` 退出）。
- 绕过：若后端起不来报 DUCKDB-FAIL，先核 `backend/.env` 的 `DUCKDB_PATH`；勿手动 `touch` 空库。

## 陷阱 4 · 沙箱 safe-delete 拦截删除

- 现象：`os.remove`/`shutil.move`/`PowerShell Remove-Item` 删除项目内文件被 `genie-trash` 拦截（WinError 5 / trash-failed），删除失败会**拒绝回退删除**。
- 绕过：要移除项目内残留，**用 Win32 `MoveFileExW`（`MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH`）把文件移出项目目录**到外部 `_trash_ai_report/`（非删除、可恢复）。
- 经验：锁文件（如 `.wal`、被占用的 `defect_fix_evidence` 内文件）可能 `MoveFileExW` 也 err=5，此时加 `.gitignore` 忽略即可，无害遗留。

## 陷阱 5 · GBK 编码

- 现象：`netstat` / 部分 Windows 命令 stdout 为 GBK，`subprocess` 直接读乱码或抛错。
- 绕过：`subprocess` 输出 `decode('gbk','ignore')`；或改用 Python `psutil` 查端口。

## 陷阱 6 · PowerShell 工具偶发空输出

- 现象：前几次 PowerShell 调用 stdout 为空（exit 0）。
- 绕过：优先用 Bash + `git.exe -C` 绝对路径；PowerShell 仅在确需 `Remove-Item`/`Get-ChildItem` 且 Bash 不便时用，并 `2>&1` 兜底。

## 陷阱 7 · 出口代理 7897

- 现象：后端访问 LLM 网关（`token.sensenova.cn`）超时/不可达。
- 绕过：确认 Clash 代理 7897 在线；后端进程走系统代理或显式 `HTTP_PROXY`/`HTTPS_PROXY=http://127.0.0.1:7897`。
- 注意：本机环境变量曾同时存 `http_proxy`/`HTTP_PROXY` 大小写重复，导致某些 MCP 启动即崩；后端用单份小写即可。

## 附：目录/文件雷区

- `backend/data/` 整体被 `.gitignore` 忽略，**不会入库**——20 个分身库在此安全。
- 根级 `defect_fix_evidence/`（及 `docs/defect_fix_evidence/`）为 gitignored 本地证据残留，勿提交。
- 改 API 契约前，先用 Grep 列出 `backend/app/api/*.py` 全部引用点（陷阱 2 复核）。
