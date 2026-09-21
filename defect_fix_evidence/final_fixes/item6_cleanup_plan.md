# Item 6 · 清理测试残留数据 —— 方案（仅方案，未执行任何删除）

> ⚠️ **本文件只给方案与清单，按你的纪律"清数据先给方案等我拍板，不许先删"。下列删除均未执行。**
> 所有判断基于 `backend/data/aibi.db`（元数据 SQLite）只读 `SELECT` 枚举，未改动任何数据。

## 0. 范围与原则
- 当前环境是**大赛/开发联调库**，充斥 QA、E2E、安全注入、路演/绿标验证等测试痕迹。
- 删除**不可逆**，须先备份、再按 FK 顺序删、并同步清理 DuckDB 物理表。
- `risk_demo_v2_05_合规月度表` 看板（Item 1 已验的真实看板）**明确保留**。

## 1. 备份（删除前必做）
```bash
# 停后端（释放文件锁）
# 复制元数据库
cp backend/data/aibi.db backend/data/aibi.db.bak_20260910
# 复制全部 DuckDB 物理文件
cp -r backend/data/duckdb backend/data/duckdb.bak_20260910
# 记录备份路径与大小，确认成功后再删
```

## 2. 明确测试残留（建议删除）

### 2.1 用户（保留 admin，其余 QA/验证账号全部候选）
共 47 用户，**仅 `admin`(superuser) 为真实账号**，其余 46 个均为测试/验证账号：
`aibiverify`、`qa_dbg2`、`qa_dbg_60e1c8`、`qa_e2e_js8ulmul`、`qa_e2e_wpbi4knv`、
`qa_g2_A_*`(×5)、`qa_g2_B_*`(×5)、`qa_g2dbg_panmvh`、`qa_int_mm6vn6hv`、
`qa_lock_35733e/7b9946/b028e1`、`qa_perf_*`(×5)、`qa_sec_*`(×10)、`qa_ui_c8o6cd`、
`qa_user_*`(×5)、`qa_user2_*`(×4)、`roadshow_verify`、`upauth_e868db8000`、`greenlabel_test`。
> ⚠️ 删除用户会影响其 `created_by` 指向的看板/数据集（但这些列是字符串非强 FK，删用户不会级联，看板/数据集记录仍在）。是否连同其创建的看板一起删，见 2.2/2.3。

### 2.2 看板（保留 risk_demo_v2_05，其余候选）
| 看板名 | 份数 | 性质 |
|---|---|---|
| `D24c看板` | 6 | 测试重复 |
| `U1私有看板` | 3 | 测试 |
| `alert(1)` | 2 | **XSS 注入测试载荷（安全）** |
| `OWNER测试` / `U1测试` | 各1 | 测试 |
| `演示测试数据集_1789871252108看板` | 3 | 测试 |
| `S3-verify-dataset看板` | 6 | 验证 |
| `绿标验证_c680e3看板` | 1 | 绿标验证 |
| `路演验证_a5b4a4看板` | 1 | 路演验证 |
| `QA销售数据集看板` | 1 | QA |

### 2.3 数据集（保留 risk_demo_v2_05 对应表，其余候选）
| 数据集名 | duckdb_table | 份数 | 性质 |
|---|---|---|---|
| `<img src=x onerror=alert(1)>` | ds_14561845_… | 1 | **XSS 注入载荷（安全）** |
| `G2数据集` | ds_5bd315e3_… | 1 | 测试 |
| `QA销售数据集` | ds_04d68399_… | 1 | QA |
| `S3-verify-dataset` | ds_d9fcd451_… | 1 | 验证 |
| `anon` | ds_eb891242_… | 1 | 测试 |
| `e2e验收_贷款明细_*` | ds_1aa17791/643c7750/53e48855/7d5e221b/7cf25ff3 | 5 | E2E |
| `l8_test` | ds_7aa4410e_… | 1 | 测试 |
| `qc_dirty` | ds_16bfea77/…(5表) | 5 | 质量脏数据 |
| `演示测试数据集_1789871252108` | ds_4920434e_… | 1 | 测试 |
| `绿标验证_c680e3` | ds_4036d442_… | 1 | 绿标验证 |
| `路演验证_a5b4a4` | ds_c4da0c26_… | 1 | 路演验证 |
| `验收_xlsx放款数据` | ds_bc074d81_… | 1 | 验收 |
| `验收测试_贷款明细` | ds_00e11129/2b5cf5c6 | 2 | 验收 |

## 3. 疑似真实 demo 种子（需你确认保留 or 删除）
这些 `risk_demo_v2_*` / `销售样本` 命名像大赛官方 demo 数据，建议保留，但请你拍板：
- 看板 `risk_demo_v2_02_客户风险画像表看板`（created_by=`current`，异常，需确认）
- 数据集 `risk_demo_v2_01_贷款明细表`(×3)+`_验证`、`risk_demo_v2_02_客户风险画像表`(×2)、`risk_demo_v2_05_合规月度表`(另一副本 ds_cb0a9738)、`销售样本`、`risk_demo_v2_数据字典.md`

## 4. 删除顺序（FK 感知，先子后父）
1. 备份（见 §1）。
2. 删看板子表：`dashboard_versions`(dashboard_id)、`share_links`(dashboard_id)、`charts`(dashboard_id)、`export_tasks`(dashboard_id)、`chat_sessions`(dashboard_id)、`brain_traces`(dashboard_id) — 按目标看板 ID。
3. 删目标看板行（`dashboards`）。
4. 删数据集子表：`charts`(dataset_id)、`lineage_nodes/edges`(dataset_id)、`quality_issues`(dataset_id)、`clean_rules`(dataset_id) — 按目标数据集 ID。
5. 删目标数据集行（`datasets`）。
6. **同步 DROP DuckDB 物理表**：上述 `ds_*` 表存在于 `qa_aibi.db`（或各自 .db）；SQLite 行删除不会级联 DuckDB，必须 `DROP TABLE IF EXISTS ds_xxx`。
7. 最后删测试用户（`users`）—— 仅当其创建的看板/数据集已在上步清掉；否则 `created_by` 成悬空字符串（不影响运行，但建议一并清）。

## 5. 风险
- **不可逆**：删前必须 §1 备份且校验大小。
- **DuckDB  orphan 表**：只删 SQLite 行会留 DuckDB 死表，占空间且干扰"数据集列表"——必须第 6 步同步 DROP。
- **强 FK 报错**：若先删父表会因外键约束失败；严格按 §4 顺序。
- **误删真实数据**：`risk_demo_v2_05_合规月度表`(ds_3716856d) 与 admin 账号**严禁删除**（Item 1 依赖）。

## 6. 待你拍板
请确认：
- (A) 测试用户 46 个是否全删？（建议：是，仅留 admin）
- (B) §2.2/§2.3 看板/数据集是否全删？（建议：是）
- (C) §3 的 `risk_demo_v2_*` demo 种子保留还是删？（建议：保留 v05 真实看板相关，其余 demo 视你意见）
- (D) 确认后我再生成精确 ID 级 DELETE + DROP 脚本，**执行前再请你最终确认一次**。

> 本会话**未执行任何 DELETE / DROP**。
