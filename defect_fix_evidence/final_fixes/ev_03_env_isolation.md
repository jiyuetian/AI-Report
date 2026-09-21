# 0.3 环境隔离 — 证据

## 改动
1. `backend/run_backend.py` `main()` 开头新增启动横幅：明确打印后端绑定的
   `DuckDB(业务数据)` 与 `MetaDB(元数据)`，并在 `DUCKDB_PATH` 未显式设置时打印
   `[0.3-WARN]` 告警（回退到元数据库 `aibi.db` 而非业务数据）。
2. `backend/.env.example` 补全 `DUCKDB_PATH`（此前缺失，是隔离缺口），并加注释：
   一个后端只对一个库，业务库与元数据必须分开、不指向同一文件。

## 实测（boot 日志 `ev_03_boot.log`）
```
[0.3-WARN] DUCKDB_PATH 未显式设置！将回退到默认 ./data/duckdb/aibi.db（元数据库，非业务数据）。
[0.3] 后端绑定 -> DuckDB(业务数据)=None(将用配置默认 ./data/duckdb/aibi.db)  MetaDB(元数据)=None(将用配置默认 sqlite+aiosqlite:///./data/aibi.db)
[B5] 端口 8000 已被占用（可能存在未记录的后端进程）。拒绝启动以免双进程。
[B5] 请先确认并结束占用 8000 的进程，再重试。
```
- 0.3：横幅 + 告警生效（静默错库类 bug 现被显式暴露）。
- 0.2（B5 单实例）：端口占用即拒绝，验证通过。

## 完成标准核对
- 后端改动：diff + 实测 API/启动响应 ✅（启动横幅即响应证据）
- 未引新依赖、未改业务代码 ✅
