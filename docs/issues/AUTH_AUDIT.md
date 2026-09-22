# 鉴权面审计（AUTH_AUDIT）

> 分支：`p0-security-fixes`　｜　基准提交：`2541347`（两个 P0 已修并推送）
> 生成时间：2026-09-22 23:48
> 方法：**①静态全量扫描** `backend/app/api/*.py` 全部路由 + **②不带 token 实探**（用不存在的 id，不触碰真实数据）
> 关联：`docs/issues/ISSUES.md`（ISS-003 横向越权）、`RULES.md` 数据库/API 红线

---

## 0. 结论（TL;DR）

1. **本轮两个 P0 已修且实测通过**（`/dashboards/my` 归属过滤、DELETE 越权），见第 1 节。
2. **确实还有"第三个越权"，且不止一个**：实探发现 **14/25** 个业务端点在**完全不带 token** 的情况下就能抵达处理函数，其中 `POST /api/v1/versions/rollback/{dashboard_id}`、`POST /api/v1/shares/create`、`POST /api/v1/chat/message`、`POST /api/v1/exports/sync` 可直接操作**任意看板**，与刚修的两个 P0 属同一攻击面。详见第 3 节。
3. 写操作端点共 **106** 个，其中业务端点缺归属校验的 **61** 个；列表端点 **28** 个，业务端点未按 owner 过滤的 **15** 个。
4. 静态扫描有假阳性（依赖写在函数签名里时可能漏判），**以第 3 节实探结果为准**。

---

## 1. 本轮已修的两个 P0（提交 2541347）

| 端点 | 问题 | 修法 | 实测 |
|------|------|------|------|
| `GET /api/v1/dashboards/my` | `_OWNERS` 固定含 legacy `anonymous`/`current`，**任何登录用户**都能看到 pre-auth 演示看板 | legacy 仅**超管**可见；普通用户严格 `created_by/updated_by == 自身uid` | e2e_test=1 / user_d10=6 / admin=17，**两两交集 0** |
| `DELETE /api/v1/dashboards/{id}` | `is_legacy` 无条件放行，任何登录用户可删 legacy 看板（**已造成误删 risk_demo_v2_02 两次的真实事故**） | 去掉 legacy 特判，仅**创建者本人 or 超管**可删，其余 403 | e2e 删自有=200(控制组)；e2e 删 legacy/admin/**risk_demo**=**403**；admin 删自有/legacy=200 |

---

## 2. 静态全量扫描

### 2.1 写操作端点（DELETE / PATCH / PUT / POST）共 106 个

> 判定口径：`✅有归属校验`=函数内出现 `created_by/is_owner/_assert_dashboard_access/owner`；
> `⚠️仅角色校验`=只有 `require_admin/require_roles/is_superuser`，**没有对象级归属判断**；
> `❌无身份依赖`=完全没有注入当前用户；`❌无归属校验`=有登录身份但不校验归属。
> 分类"公开设计"指 login/register/health 等本就匿名；"内部/测试端点"指 `_internal`/`test`/`golden`/`loadtest`/`debug`。

| 端点 | 方法 | 处理函数 | 文件 | 归属/鉴权校验 | 风险 | 分类 |
|------|------|----------|------|----------------|------|------|
| `/api/v1/admin/users/{user_id}` | PATCH | `admin_update_user` | `admin.py` | ⚠️仅角色校验(require_admin) | 中 | 业务端点 |
| `/api/v1/admin/templates` | POST | `admin_create_template` | `admin.py` | ⚠️仅角色校验(require_admin) | 中 | 业务端点 |
| `/api/v1/admin/templates/{template_id}` | PATCH | `admin_update_template` | `admin.py` | ⚠️仅角色校验(require_admin) | 中 | 业务端点 |
| `/api/v1/admin/templates/{template_id}` | DELETE | `admin_delete_template` | `admin.py` | ⚠️仅角色校验(require_admin) | 中 | 业务端点 |
| `/api/v1/admin/prompts/{key}` | PUT | `save_prompt` | `admin_prompts.py` | ⚠️仅角色校验(require_roles) | 中 | 业务端点 |
| `/api/v1/admin/prompts/{key}/reset` | POST | `reset_prompt` | `admin_prompts.py` | ⚠️仅角色校验(require_roles) | 中 | 业务端点 |
| `/api/v1/auth/login` | POST | `login` | `auth.py` | ❌无身份依赖 | 高 | 公开设计 |
| `/api/v1/auth/forgot-password/send-code` | POST | `send_verification_code` | `auth.py` | ❌无身份依赖 | 高 | 公开设计 |
| `/api/v1/auth/forgot-password/verify-code` | POST | `verify_code` | `auth.py` | ❌无身份依赖 | 高 | 公开设计 |
| `/api/v1/auth/forgot-password/reset` | POST | `reset_password` | `auth.py` | ❌无身份依赖 | 高 | 公开设计 |
| `/api/v1/auth/logout` | POST | `logout` | `auth.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/auth/register` | POST | `register` | `auth.py` | ❌无身份依赖 | 高 | 公开设计 |
| `/api/v1/brain/configs/update` | POST | `update_threshold` | `brain.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/run` | POST | `brain_run` | `brain_run_sse.py` | ✅有归属校验(owner) | 低 | 业务端点 |
| `/api/v1/brain/run/{run_id}/cancel` | POST | `cancel_run` | `brain_run_sse.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/brain/run/{run_id}/resume` | POST | `resume_run` | `brain_run_sse.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/brain/configs` | POST | `create_or_update_config` | `brain_v2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/configs/{config_key}/rollback` | POST | `rollback_config` | `brain_v2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/trace/run/start` | POST | `start_run` | `brain_v2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/trace/stage/start` | POST | `start_stage` | `brain_v2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/trace/stage/complete` | POST | `complete_stage` | `brain_v2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/trace/run/complete` | POST | `complete_run` | `brain_v2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/_internal/init-configs` | POST | `init_default_configs` | `brain_v2.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/chat/sessions` | POST | `create_session` | `chat.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/chat/message` | POST | `send_message_stream` | `chat.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/chat/classify-intent` | POST | `classify_intent_api` | `chat.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/chat/execute-action` | POST | `execute_action_api` | `chat.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/chat/test/moderation` | POST | `test_moderation` | `chat.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/chat/test/retry` | POST | `test_retry_mechanism` | `chat.py` | ❌无归属校验 | 高 | 内部/测试端点 |
| `/api/v1/dashboards/{dashboard_id}` | DELETE | `delete_dashboard` | `dashboards.py` | ✅有归属校验(created_by,is_owner) | 低 | 业务端点 |
| `/api/v1/dashboards/` | POST | `create_dashboard` | `dashboards.py` | ✅有归属校验(created_by,owner) | 低 | 业务端点 |
| `/api/v1/dashboards/{dashboard_id}` | PATCH | `update_dashboard` | `dashboards.py` | ✅有归属校验(_assert_dashboard_access) | 低 | 业务端点 |
| `/api/v1/datasets` | POST | `create_dataset` | `datasets.py` | ✅有归属校验(created_by) | 低 | 业务端点 |
| `/api/v1/datasets/_internal/seed-test-data` | POST | `seed_test_data` | `datasets.py` | ⚠️仅角色校验(require_admin) | 中 | 内部/测试端点 |
| `/api/v1/datasets/{dataset_id}` | DELETE | `delete_dataset` | `datasets.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/exceptions/orphan-rows/detect` | POST | `detect_orphan_rows` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/data-bloat/detect` | POST | `detect_data_bloat` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/key-type/validate` | POST | `validate_key_type` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/schema/heal` | POST | `schema_self_healing` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/category/validate` | POST | `validate_category` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/sensitive/detect` | POST | `detect_sensitive_data` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/conflict/detect` | POST | `detect_edit_conflict` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/async/timeout-check` | POST | `check_async_timeout` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/expired/cleanup` | POST | `cleanup_expired_resources` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/grain/validate` | POST | `validate_data_grain` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exceptions/batch-check` | POST | `batch_check_exceptions` | `exceptions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exports/sync` | POST | `export_sync` | `exports.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/exports/async` | POST | `export_async` | `exports.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/golden/run` | POST | `run_golden_test` | `golden.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/golden/run-single/{dataset_id}` | POST | `run_single_golden_test` | `golden.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/golden/export-report/{report_id}` | POST | `export_golden_report` | `golden.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/lineage/build` | POST | `build_lineage` | `lineage.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/lineage/verify` | POST | `verify_lineage` | `lineage.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/lineage/rebuild-all` | POST | `rebuild_all_lineage` | `lineage.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/llm/chat` | POST | `chat_complete` | `llm.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/llm/chat/completions` | POST | `openai_compatible_chat` | `llm.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/llm/template/render` | POST | `render_template` | `llm.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/llm/_internal/test-retry` | POST | `test_retry_mechanism` | `llm.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/loadtest/run` | POST | `run_load_test` | `loadtest.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/loadtest/upload-100k` | POST | `test_upload_100k` | `loadtest.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/loadtest/concurrent-chat` | POST | `test_concurrent_chat` | `loadtest.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/loadtest/chart-10k` | POST | `test_chart_10k` | `loadtest.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/quality/check` | POST | `check_quality` | `quality.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/quality/fix` | POST | `fix_quality_issue` | `quality.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/quality/fix-batch` | POST | `fix_quality_issues_batch` | `quality.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/quality/_internal/test-quality` | POST | `test_quality_check` | `quality.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/quality/debug/inject-dup` | POST | `debug_inject_dup` | `quality.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/reports` | POST | `generate_report` | `reports.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s1/detect` | POST | `detect_theme_endpoint` | `s1.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s1/detect-v2-table` | POST | `detect_v2_table_theme` | `s1.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s1/_internal/test-v2-tables` | POST | `test_v2_tables` | `s1.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/brain/s2/generate` | POST | `generate_goals` | `s2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s2/generate-v2-table` | POST | `generate_v2_table_goals` | `s2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s2/_internal/test-v2-tables` | POST | `test_v2_table_goals` | `s2.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/brain/s3/recommend` | POST | `recommend_charts_endpoint` | `s3.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s3/generate-dashboard` | POST | `generate_dashboard_endpoint` | `s3.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s3/_internal/test-01-table` | POST | `test_01_table_dashboard` | `s3.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/brain/s3/_internal/test-grain-constraints` | POST | `test_grain_constraints` | `s3.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/brain/s3/generate-llm` | POST | `generate_with_llm` | `s3.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s3/validate-grain` | POST | `validate_chart_grain_endpoint` | `s3.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s3/_internal/test-self-healing` | POST | `test_self_healing` | `s3.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/brain/s4/orchestrate` | POST | `orchestrate_endpoint` | `s4_s5.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s5/score` | POST | `score_endpoint` | `s4_s5.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s4s5/orchestrate-and-score` | POST | `orchestrate_and_score_endpoint` | `s4_s5.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/_internal/test-score` | POST | `test_score_calculation` | `s4_s5.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/brain/_internal/test-orchestrate` | POST | `test_orchestrate` | `s4_s5.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/brain/_internal/test-retry` | POST | `test_retry_mechanism` | `s4_s5.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/shares/create` | POST | `create_share` | `share.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/shares/{share_code}/verify` | POST | `verify_share_password` | `share.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/shares/{share_id}/revoke` | POST | `revoke_share` | `share.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/tokens/applications/apply` | POST | `apply_for_extra_quota` | `token_applications.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/tokens/applications/admin/{application_id}/approve` | POST | `approve_application` | `token_applications.py` | ⚠️仅角色校验(require_admin) | 中 | 业务端点 |
| `/api/v1/tokens/applications/admin/{application_id}/reject` | POST | `reject_application` | `token_applications.py` | ⚠️仅角色校验(require_admin) | 中 | 业务端点 |
| `/api/v1/tokens/consume` | POST | `consume_tokens` | `tokens.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/tokens/admin/reset` | POST | `admin_reset_quota` | `tokens.py` | ⚠️仅角色校验(require_admin) | 中 | 业务端点 |
| `/api/v1/tokens/admin/schedule-reset` | POST | `trigger_scheduled_reset` | `tokens.py` | ⚠️仅角色校验(require_admin) | 中 | 业务端点 |
| `/api/v1/tokens/_internal/test-consume` | POST | `test_consume_tokens` | `tokens.py` | ❌无归属校验 | 高 | 内部/测试端点 |
| `/api/v1/tokens/_internal/test-warning` | POST | `test_warning_state` | `tokens.py` | ❌无归属校验 | 高 | 内部/测试端点 |
| `/api/v1/tokens/_internal/test-exhausted` | POST | `test_exhausted_state` | `tokens.py` | ❌无归属校验 | 高 | 内部/测试端点 |
| `/api/v1/files` | POST | `upload_file` | `upload.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/files/{file_id}` | DELETE | `delete_file` | `upload.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/files/{file_id}/select-sheet` | POST | `select_sheet` | `upload.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/files/{file_id}/select-encoding` | POST | `select_encoding` | `upload.py` | ❌无归属校验 | 高 | 业务端点 |
| `/api/v1/versions/create` | POST | `create_version` | `versions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/versions/rollback/{dashboard_id}` | POST | `rollback_version` | `versions.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/versions/compare` | POST | `compare_versions` | `versions.py` | ❌无身份依赖 | 高 | 业务端点 |

### 2.2 列表 / 查询端点（`/my`、`/list`、复数 GET）共 28 个

| 端点 | 方法 | 处理函数 | 文件 | 归属/鉴权校验 | 风险 | 分类 |
|------|------|----------|------|----------------|------|------|
| `/api/v1/admin/overview` | GET | `admin_overview` | `admin.py` | ⚠️仅角色校验 | 中 | 业务端点 |
| `/api/v1/admin/users` | GET | `admin_users` | `admin.py` | ⚠️仅角色校验 | 中 | 业务端点 |
| `/api/v1/admin/roles` | GET | `admin_roles` | `admin.py` | ⚠️仅角色校验 | 中 | 业务端点 |
| `/api/v1/admin/templates` | GET | `admin_list_templates` | `admin.py` | ⚠️仅角色校验 | 中 | 业务端点 |
| `/api/v1/brain/configs` | GET | `get_brain_configs` | `brain.py` | ⚠️仅角色校验 | 中 | 业务端点 |
| `/api/v1/brain/run/{run_id}/status` | GET | `get_run_status` | `brain_run_sse.py` | ❌未按owner过滤 | 高 | 业务端点 |
| `/api/v1/brain/configs` | GET | `list_configs` | `brain_v2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/chat/test/action-examples` | GET | `get_action_test_examples` | `chat.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/chat/test/intent-examples` | GET | `get_intent_test_examples` | `chat.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/dashboards/my` | GET | `list_my_dashboards` | `dashboards.py` | ✅按created_by过滤 | 低 | 业务端点 |
| `/api/v1/dashboards/stats/overview` | GET | `get_dashboard_stats` | `dashboards.py` | ✅按created_by过滤 | 低 | 业务端点 |
| `/api/v1/datasets/_internal/duckdb/tables` | GET | `list_duckdb_tables` | `datasets.py` | ⚠️仅角色校验 | 中 | 内部/测试端点 |
| `/api/v1/exports/my/list` | GET | `list_my_exports` | `exports.py` | ❌未按owner过滤 | 高 | 业务端点 |
| `/api/v1/golden/datasets` | GET | `list_golden_datasets` | `golden.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/llm/rate-limit/status` | GET | `get_rate_limit_status` | `llm.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/quality/{dataset_id}/issues` | GET | `get_quality_issues` | `quality.py` | ❌未按owner过滤 | 高 | 业务端点 |
| `/api/v1/quality/debug/clean-stats` | GET | `debug_clean_stats` | `quality.py` | ❌无身份依赖 | 高 | 内部/测试端点 |
| `/api/v1/brain/s2/types` | GET | `get_goal_types` | `s2.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s3/rules` | GET | `get_chart_rules` | `s3.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s3/field-types` | GET | `get_field_types` | `s3.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/brain/s3/chart-types` | GET | `get_chart_types` | `s3.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/shares/my/list` | GET | `list_my_shares` | `share.py` | ✅按created_by过滤 | 低 | 业务端点 |
| `/api/v1/skills` | GET | `list_skills` | `skills.py` | ❌无身份依赖 | 高 | 业务端点 |
| `/api/v1/tokens/applications/my-applications` | GET | `get_my_applications` | `token_applications.py` | ❌未按owner过滤 | 高 | 业务端点 |
| `/api/v1/tokens/applications/my-applications/{application_id}` | GET | `get_application_detail` | `token_applications.py` | ❌未按owner过滤 | 高 | 业务端点 |
| `/api/v1/tokens/status` | GET | `get_full_status` | `tokens.py` | ❌未按owner过滤 | 高 | 业务端点 |
| `/api/v1/files/{file_id}/sheets` | GET | `get_excel_sheets` | `upload.py` | ❌未按owner过滤 | 高 | 业务端点 |
| `/api/v1/versions/list/{dashboard_id}` | GET | `list_versions` | `versions.py` | ❌无身份依赖 | 高 | 业务端点 |

---

## 3. 实探验证：不带 token 直连（决定性证据）

> 用**不存在的 id** 探测，绝不触碰真实数据。
> `401/403` = 鉴权生效；`404/400/422` = 请求已抵达 handler（**说明无鉴权**）；`200` = 无鉴权且成功执行。

| 方法 | 端点 | 无 token 响应 | 判定 | 备注 |
|------|------|---------------|------|------|
| GET | `/api/v1/dashboards/my` | 401 | ✅鉴权生效 | P0-1 已修 |
| GET | `/api/v1/dashboards/stats/overview` | 401 | ✅鉴权生效 | 看板统计 |
| GET | `/api/v1/dashboards/no-such-id-000` | 401 | ✅鉴权生效 | 看板明细 |
| DELETE | `/api/v1/dashboards/no-such-id-000?confirm_name=x` | 401 | ✅鉴权生效 | P0-2 已修 |
| DELETE | `/api/v1/datasets/no-such-id-000` | 401 | ✅鉴权生效 | 删数据集 |
| DELETE | `/api/v1/files/no-such-id-000` | 401 | ✅鉴权生效 | 删文件 |
| GET | `/api/v1/tokens/status` | 200 | ❌无鉴权(成功执行) | 令牌状态 |
| GET | `/api/v1/exports/my/list` | 401 | ✅鉴权生效 | 我的导出 |
| GET | `/api/v1/shares/my/list` | 401 | ✅鉴权生效 | 我的分享 |
| GET | `/api/v1/versions/list/no-such-id-000` | 200 | ❌无鉴权(成功执行) | 版本列表 |
| GET | `/api/v1/quality/no-such-id-000/issues` | 401 | ✅鉴权生效 | 质检问题 |
| GET | `/api/v1/brain/run/no-such-id-000/status?dataset_id=no-such-id-000` | 401 | ✅鉴权生效 | run 状态 |
| GET | `/api/v1/files/no-such-id-000/sheets` | 401 | ✅鉴权生效 | Excel 页 |
| POST | `/api/v1/chat/message` | 200 | ❌无鉴权(成功执行) | AI 对话 |
| POST | `/api/v1/chat/sessions` | 200 | ❌无鉴权(成功执行) | 建会话 |
| POST | `/api/v1/versions/rollback/no-such-id-000` | 422 | ❌无鉴权(进到参数校验) | 版本回滚 |
| POST | `/api/v1/versions/create` | 422 | ❌无鉴权(进到参数校验) | 建版本 |
| POST | `/api/v1/shares/create` | 200 | ❌无鉴权(成功执行) | 建分享链接 |
| POST | `/api/v1/tokens/consume` | 422 | ❌无鉴权(进到参数校验) | 扣令牌 |
| POST | `/api/v1/quality/check` | 404 | ❌无鉴权(直达 handler) | 质检 |
| POST | `/api/v1/brain/s3/recommend` | 422 | ❌无鉴权(进到参数校验) | S3 推荐 |
| POST | `/api/v1/llm/chat` | 422 | ❌无鉴权(进到参数校验) | LLM 直连 |
| POST | `/api/v1/reports` | 404 | ❌无鉴权(直达 handler) | 生成报告 |
| POST | `/api/v1/lineage/build` | 404 | ❌无鉴权(直达 handler) | 建血缘 |
| POST | `/api/v1/exports/sync` | 200 | ❌无鉴权(成功执行) | 同步导出 |

### 3.1 必须优先处理的高危未鉴权端点

| 端点 | 风险 | 说明 |
|------|------|------|
| `POST /api/v1/versions/rollback/{dashboard_id}` | **P0** | 无鉴权即可回滚**任意看板**到指定版本 —— 与本次两个 P0 完全同一攻击面，是"第三个越权" |
| `POST /api/v1/shares/create` | **P0** | 无鉴权即可为**任意看板**创建分享链接（外发数据） |
| `POST /api/v1/chat/message` | **P0** | 无鉴权即可对**任意看板**发起 AI 改图（含删除图表动作） |
| `POST /api/v1/exports/sync` | **P1** | 无鉴权触发导出 |
| `POST /api/v1/versions/create` | **P1** | 无鉴权为任意看板建版本 |
| `GET /api/v1/versions/list/{dashboard_id}` | **P1** | 无鉴权读取任意看板版本历史（信息泄露） |
| `GET /api/v1/tokens/status` | **P1** | 无鉴权读令牌配额状态 |
| `POST /api/v1/chat/sessions` | **P2** | 无鉴权建会话 |
| `POST /api/v1/tokens/consume` | **P2** | 无鉴权扣减令牌 |
| `POST /api/v1/quality/check`、`/reports`、`/lineage/build`、`/brain/s3/recommend`、`/llm/chat` | **P2** | 无鉴权即可驱动管线（消耗 LLM 配额） |

---

## 4. 建议修复顺序（明早）

1. **P0 三件套**：给 `versions/rollback`、`shares/create`、`chat/message` 补 `get_current_user` + 对象归属校验（复用 `_assert_dashboard_access`）。
2. **P1**：`exports/sync`、`versions/create`、`versions/list`、`tokens/status` 补鉴权；`versions/*` 一并加归属。
3. **P2**：管线类端点统一加 `get_current_user` 兜底（防 LLM 配额被刷）。
4. 内部/测试端点（`_internal`、`golden`、`loadtest`）建议**按环境开关关闭**，生产不暴露。

> 红线提醒：改 API 契约须同步**全部调用点**（前端 + 其它服务）；一类一 commit、一类一 push，失败即 `git revert`。
