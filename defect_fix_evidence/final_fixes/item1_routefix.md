# Item 1 · 路由修复 + 真实看板出图（已实测通过）

**状态：✅ 已完成并实测**
**约束：** 仅按约定范围改动，未动路由逻辑本身（根因是 DuckDB 指向错误，非代码 bug）。

## 根因（结论 A）
- 真实业务表在 `qa_aibi.db`（`ds_3716856d_*` 系列），但 `backend/.env` 默认 `DUCKDB_PATH=./data/duckdb/aibi.db`。
- 启动后端时须显式指定：
  `DUCKDB_PATH=./data/duckdb/qa_aibi.db python run_backend.py`
- `config.py:_PROJECT_ROOT` 解析到 `backend/`，故 `.env` 正确位置是 `backend/.env`（已核实）。

## 实测证据（2026-09-10，后端进程占用 8000）
| 接口 | 方法 | 状态码 | 关键返回 |
|---|---|---|---|
| `/api/v1/health` | GET | 200 | healthy, version 2.0.0 |
| `/api/v1/dashboards/dash_3716856d_35d769` | GET | 200 | name=`risk_demo_v2_05_合规月度表看板`，charts=**5** |
| `/api/v1/datasets/3716856d-.../chart-data` | GET | 200 | columns=**6**，rows=**12**（真实月度合规率） |
| 附录 `/preview`、`/profile` | GET | 200 | 有数据（前期已验） |

**5 张真实图：** 业务流程合规率 / 合规指标月度趋势 / 登记与档案合规趋势 / 制度执行与整改对比 / 合规指标月度明细。

## 落盘产物
- `routefix_proof.html` — 真实数据契约可视化快照（沙箱无浏览器，无法对 React UI 截图；UI 以本机 `http://127.0.0.1:8000/dashboard/dash_3716856d_35d769` 实测为准）。
- `proof_data.json` — 原始返回 JSON。
- `verify_item145.py` — 可复跑的验证脚本（自签 admin JWT）。

## 说明
本项无代码改动（路由代码本身正确，问题在使用时未指向正确 DuckDB）。已通过运行时实测坐实结论 A。
