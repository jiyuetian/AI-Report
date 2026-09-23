# 04 · 运行手册（RUNBOOK）

> 本机陷阱见 `05_KNOWN_TRAPS.md`。所有 Git 操作用 `git.exe -C "<绝对路径>"`（陷阱 1）。

## 1. 起后端

```bash
# run_backend.py 内部会 chdir 到 backend/，故直接绝对路径调用即可
C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe \
  "C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend/run_backend.py"
```

- 端口 8000；B5 单实例守卫（重复起会拒，先查 `backend/.backend.pid`）。
- 启动自检：DuckDB fail-fast——库缺失 → `[DUCKDB-FAIL]` 退出；表=0 → 告警；正常 → 打印 `ds_*` 表数。
- 若提示 DuckDB 缺失：**先确认 `backend/.env` 的 `DUCKDB_PATH` 指向 `./data/duckdb/aibi.db`**（绝对路径解析基于 backend 根）。
- LLM 网关需出口代理 7897；后端进程需能访问 `https://token.sensenova.cn/v1`。

## 2. 起前端

```bash
cd "C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/frontend"
C:/Users/Asus009/.workbuddy/binaries/node/versions/22.22.2-3/node.exe node_modules/.bin/vite
# 或 npm run dev（用 managed node）
```

- 端口 5173；`npm run build` 产出 `dist/`。

## 3. 测试

```bash
# 后端编译
C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe -m py_compile backend/app/**/*.py
# 后端单测（若 tests/ 有 pytest）
C:/Users/Asus009/.workbuddy/binaries/python/versions/3.13.12/python.exe -m pytest backend/tests -q
# 前端类型检查
cd frontend && npx tsc --noEmit
```

- 接口冒烟：`GET /health` 应 200；核心链路用 `backend/tests` 或 `ai-report-acceptance-report/` 的用例。
- AI 对话真跑：需后端起 + LLM 网关可达；绿标判定见 `LoadingPage.tsx` 读 `generation_mode`/`ai_participated`。

## 4. 备份（改数据模型前必做）

```bash
# 停后端（见陷阱：taskkill 强杀）
# 备份真相库 + wal
cp "backend/data/duckdb/aibi.db"      "backend/data/backups/aibi_$(date +%Y%m%d_%H%M%S).db"
cp "backend/data/duckdb/aibi.db.wal"  "backend/data/backups/aibi_$(date +%Y%m%d_%H%M%S).db.wal"
cp "backend/data/aibi.db"             "backend/data/backups/meta_$(date +%Y%m%d_%H%M%S).db"
# 校验大小（GBK 解码见陷阱；Python 直接 stat）
```

> 注：`date` 在损坏 shim 下可能缺失，用 Python `datetime` 生成时间戳，或手动命名。

## 5. 回滚（schema 改动必带）

- 任何 `alembic`/DDL 改动，先写回滚脚本（反向 DDL 或 `alembic downgrade`）。
- 若改坏：从 `backend/data/backups/` 还原 `.db`+`.wal`，重启后端。
- Git 层面：`git revert <commit>` 回退单类改动，不要 `git reset --hard` 共享分支。

## 6. 提交纪律（红线）

```bash
git.exe -C "<绝对路径>" add <具体文件>      # 禁 git add -A（会误带 gitignored 残留）
git.exe -C "<绝对路径>" commit -m "feat/fix/docs: 一类一说明"
git.exe -C "<绝对路径>" push origin p0-security-fixes
```
