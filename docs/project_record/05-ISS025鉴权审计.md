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


---

# 附录 A：ISS-025 分类清单（2026-09-23 白天，第 1 步，只查不改）

> 分支 `p0-security-fixes`　基准 `7050ac4`
> 方法：①OpenAPI 全量扫描（193 个操作）　②静态端点扫描　③前端调用点全量扫描（36 个源文件，24 处裸 fetch）
> **状态：本附录为分类结论，尚未修改任何后端代码。**

## A0. 先答三个问题

### 问 1：这 14 个，哪些"有意公开"、哪些"真漏"？

| 分类 | 数量 | 端点 |
|------|------|------|
| **A 类（有意公开，保持）** | **0** | —— 14 个全是业务端点，没有一个 health/docs/静态资源 |
| **B 类（真漏，必须加）** | **13** | 见下表 A1 |
| **C 类（待确认，需拍板）** | **1** | `GET /api/v1/tokens/status` |

**C 类唯一一条的理由**：前端 `ChatPanel.tsx:86` 有明确注释
`// 非强制鉴权端点 /tokens/status，按设计不带 token（过期 token 会打挂）`。
这是**历史遗留的事实描述，不是设计决议**。加了鉴权会破坏"配额显示"，但也可能只是前端没同步改。
**需你拍板**：(a) 加鉴权 + 前端改带 authHeaders（推荐）；(b) 保持公开但改为只返回布尔不返回具体配额。

### 问 2：G3 修了 13 个，为什么这次又冒 14 个？

**结论：不是 G3 漏扫，是"范围本就分批" + "审计口径不同"叠加。**

证据（`75c279a fix(security): G3 13个未认证端点加鉴权`，见 `defect_fix_evidence/fixes/G3_FIX.md`）：

| 维度 | G3（13 个） | 本次 ISS-025（14 个） |
|------|-------------|----------------------|
| HTTP 方法 | **13 个全是 GET** | **12 个 POST + 2 个 GET** |
| 性质 | 读端点（列表/详情/配置） | **写端点为主**（回滚/建分享/改图/扣令牌）+ 2 个读 |
| 端点集合 | `/datasets`、`/brain/report/{id}`、`/quality/{id}/issues`、`/lineage/graph/{id}`、`/lineage/stats/{id}`、`/llm/config`、`/chat/sessions/latest`、`/brain/configs`×3、`/shares/my/list`、`/exports/my/list` | `/versions/rollback/{id}`、`/shares/create`、`/chat/message`、`/chat/sessions`、`/versions/create`、`/versions/list/{id}`、`/exports/sync`、`/tokens/status`、`/tokens/consume`、`/quality/check`、`/brain/s3/recommend`、`/llm/chat`、`/reports`、`/lineage/build` |
| **与对方重叠** | **0** | **0** |

**根因三条**：
1. **G3 是按"既有清单"修，不是全量扫描。** 清单来源是先前的缺陷登记，天然不含本次这 14 个。
2. **同文件只挑了 GET，漏了同文件的写端点。** 极干净的规律：`quality.py` 修了 `GET /{id}/issues` 没修 `POST /check`；`lineage.py` 修了 `GET /graph` `/stats` 没修 `POST /build`；`share.py` 修了 `GET /my/list` 没修 `POST /create`；`exports.py` 修了 `GET /my/list` 没修 `POST /sync`；`llm.py` 修了 `GET /config` 没修 `POST /chat`；`chat.py` 修了 `GET /sessions/latest` 没修 `POST /message`、`POST /sessions`。
3. **G3 自己登记过、但明说"不顺手改"。** `G3_FIX.md` 第 5 节原文：
   > `tokens.py`、`token_applications.py`、`chat.py` 中部分端点仍使用 `current_user: str = "anonymous"` 默认匿名（属鉴权规范化遗留），需在后续统一排查，本次不顺手改。
   
   这一条**正对**本次的 `tokens/status`、`tokens/consume`、`chat/message`、`chat/sessions`。

> 所以：G3 没有做错，是**当时就没打算覆盖写端点**；本次是第一次做"全量实探"，把写端点这一半翻出来了。

### 问 3：以后怎么防止"又冒一批"？

**必须先纠正一个规模误判：真实数字不是 14，是 134。**

昨晚只手工实探了 25 个端点，从里面发现 14 个无鉴权。今天用 **OpenAPI 全量扫描**：

```
总操作数          = 193
无 security 声明  = 134   ← 这才是真实全貌
```

按类别拆：

| 类别 | 约数 | 处理 |
|------|------|------|
| 设计公开（auth/login/register/captcha/忘记密码/health/root） | 10 | 白名单，永不报警 |
| `_internal` / `golden` / `loadtest` 测试端点 | 22 | 按 `settings.DEBUG` 环境开关关闭，生产不注册 |
| **业务端点真漏** | **约 100** | **这才是 ISS-025 的真实工作量** |

**防复发三件套（建议）**：
1. **CI 扫描脚本** `backend/scripts/auth_scan.py`：起后端 → 拉 `/openapi.json` → 对每个操作判 `security` 是否为空 → 对照白名单 → 输出清单 + 非零退出码。**接进 CI 当门禁**，新增端点不带鉴权直接红。
2. **前端裸 fetch 扫描** `frontend/scripts/bare_fetch_scan.ts`：扫 `frontend/src` 里所有 `fetch(`（排除 `utils/request.ts` 本体），凡未出现 `authHeaders()` 的报出来。本次已扫出 **24 处裸 fetch**，其中 **4 处在本轮 14 个端点上，必改**。
3. **白名单机制** `backend/scripts/auth_whitelist.json`：把"设计公开"和"测试端点"显式登记，扫描脚本只对白名单外的报警 —— 避免告警疲劳导致真漏被淹没。

---

## A1. B 类明细（13 个，必须加）— 含前端调用点

> 前端口径：`http.*` / `request()` 封装**自动注入 token**，安全；`fetch(` 裸调用**不带 token**，改后端必崩。

| # | 端点 | 风险 | 前端调用点 | 前端是否带 token | 后端加鉴权后前端会崩？ |
|---|------|------|-----------|------------------|------------------------|
| 1 | `POST /api/v1/versions/rollback/{dashboard_id}` | **P0** | `views/dashboard/DashboardOps.tsx:219` (`http.post`) | ✅ 自动带 | 不会 |
| 2 | `POST /api/v1/shares/create` | **P0** | `DashboardOps.tsx:131`、`views/share/SharePage.tsx:77` (`http.post`) | ✅ 自动带 | 不会 |
| 3 | `POST /api/v1/chat/message` | **P0** | `components/chat/ChatPanel.tsx:222`（**裸 fetch**） | ❌ **不带** | **会崩 → 必须同步改** |
| 4 | `POST /api/v1/chat/sessions` | P2 | `ChatPanel.tsx:163`（**裸 fetch**） | ❌ **不带** | **会崩 → 必须同步改** |
| 5 | `POST /api/v1/versions/create` | P1 | 无（0 处） | — | 不会 |
| 6 | `GET /api/v1/versions/list/{dashboard_id}` | P1 | `DashboardOps.tsx:100` (`http.get`) | ✅ 自动带 | 不会 |
| 7 | `POST /api/v1/exports/sync` | P1 | `DashboardOps.tsx:165` (`http.post`) | ✅ 自动带 | 不会 |
| 8 | `POST /api/v1/quality/check` | P2 | `components/quality/QualityCheckPanel.tsx:318`（**裸 fetch**） | ❌ **不带** | **会崩 → 必须同步改** |
| 9 | `POST /api/v1/tokens/consume` | P2 | 无（0 处） | — | 不会 |
| 10 | `POST /api/v1/reports` | P2 | `views/report/ReportPage.tsx:53` (`http.post`) | ✅ 自动带 | 不会 |
| 11 | `POST /api/v1/lineage/build` | P2 | 无（0 处） | — | 不会 |
| 12 | `POST /api/v1/brain/s3/recommend` | P2 | 无（0 处） | — | 不会 |
| 13 | `POST /api/v1/llm/chat` | P2 | 无（0 处） | — | 不会 |

**⚠️ 红线 5 命中清单（后端改完前端必崩，必须同批改）**：`ChatPanel.tsx:222`、`ChatPanel.tsx:163`、`QualityCheckPanel.tsx:318` —— 共 **3 处**。
（第 14 条 `tokens/status` 在 C 类，若拍板加鉴权则 `ChatPanel.tsx:87` 也要改，变 4 处。）

## A2. 顺带扫出的同类裸 fetch（不在 14 内，但同病，建议同批改）

| 位置 | 端点 | 说明 |
|------|------|------|
| `QualityCheckPanel.tsx:220` | `GET /quality/check/ai/{dsId}` | 同类质检读端点 |
| `QualityCheckPanel.tsx:443` | `POST /quality/fix` | 同类质检写端点 |
| `QualityCheckPanel.tsx:531` | `POST /quality/fix-batch` | 同类质检批量写 |
| `components/skills/SkillPanel.tsx:43` | `GET /skills` | 静态扫描也标为无身份依赖 |

> 这 4 处当前端点本身**是否鉴权未在本轮实探范围内**；但只要给它们加鉴权就会 401 白屏。建议同批带上 `authHeaders()`，成本极低。

## A3. 一个已排除的风险（重要）

**担心**：管线端点（`/brain/s3/recommend`、`/quality/check`、`/lineage/build`、`/reports`）是不是被后端自己用 HTTP 调用？若是，加鉴权会断内部链路。

**已排除**：全仓扫描 `backend/app` 下的 `httpx`/`requests` 调用，只有两处出网：
- `core/llm_gateway.py` → 打外部 LLM 网关（`token.sensenova.cn` / `localhost:8001`）
- `api/health.py:50` → 打外部 LLM 网关的 `/chat/completions` 探针

**后端不存在自调 `/api/v1/*` 的 HTTP 调用**；模块间是 Python 直接 import（绕过 HTTP 层，不受 `Depends()` 影响）。
`core/export_service.py:190` 的 `http://127.0.0.1:8000/downloads/...` 只是拼下载 URL 字符串，不是请求。

→ **结论：给管线端点加鉴权不会断内部链路。**

---

## 附录 B：134 个无 security 操作 —— 完整分类表（2026-09-23 OpenAPI 全量扫描）

> 扫描来源：`GET /openapi.json`，遍历 `paths[method].security`，空即无鉴权。
> 总操作数 193，无 security 声明 **134** 个。

### B.0 统计总览

- **A 类（有意公开，不改）**：10 个
- **测试端点（_internal/golden/loadtest/chat-test/quality-debug，本轮不修）**：38 个
- **C 类（用户拍板：可选鉴权）**：1 个（仅 `tokens/status`）
- **真漏必须修**：85 个  ← ISS-025 真实工作量
  - 其中 P0（写/烧配额/数据导出）：见下表
  - P1（读他人数据/有限写）：见下表
  - P2（只读/参考类）：见下表

> ⚠️ 上一轮手探只找到 14 个、先报 13 个 B 类 —— **那是严重低估**。OpenAPI 全量扫描显示真漏是 **85 个**（含 P0 35 个）。本轮只修用户指定的 3 个 P0 + tokens/status + 7 处裸 fetch；其余 真漏 进 ISS-025  backlog 按优先级排期。

### B.1 完整分类表

| # | 方法 | 端点 | 分类 | 优先级 | 说明 |
|---|------|------|------|--------|------|
| 1 | GET | `/` | A | - | 根路由/文档重定向 |
| 2 | GET | `/api/v1/auth/captcha` | A | - | 登录前图形验证码 |
| 3 | POST | `/api/v1/auth/forgot-password/reset` | A | - | 找回密码流程（发码/验码/重置） |
| 4 | POST | `/api/v1/auth/forgot-password/send-code` | A | - | 找回密码流程（发码/验码/重置） |
| 5 | POST | `/api/v1/auth/forgot-password/verify-code` | A | - | 找回密码流程（发码/验码/重置） |
| 6 | POST | `/api/v1/auth/login` | A | - | 登录 |
| 7 | POST | `/api/v1/auth/register` | A | - | 注册 |
| 8 | GET | `/api/v1/health` | A | - | 健康检查，LB/探针必需 |
| 9 | GET | `/api/v1/shares/{share_code}` | A | - | 公开分享页（持链接即可看，设计公开） |
| 10 | POST | `/api/v1/shares/{share_code}/verify` | A | - | 公开分享密码校验（设计公开） |
| 11 | POST | `/api/v1/brain/_internal/init-configs` | 测试 | - | _internal 测试桩 |
| 12 | POST | `/api/v1/brain/_internal/test-orchestrate` | 测试 | - | _internal 测试桩 |
| 13 | POST | `/api/v1/brain/_internal/test-retry` | 测试 | - | _internal 测试桩 |
| 14 | POST | `/api/v1/brain/_internal/test-score` | 测试 | - | _internal 测试桩 |
| 15 | POST | `/api/v1/brain/s1/_internal/test-v2-tables` | 测试 | - | _internal 测试桩 |
| 16 | POST | `/api/v1/brain/s2/_internal/test-v2-tables` | 测试 | - | _internal 测试桩 |
| 17 | POST | `/api/v1/brain/s3/_internal/test-01-table` | 测试 | - | _internal 测试桩 |
| 18 | POST | `/api/v1/brain/s3/_internal/test-grain-constraints` | 测试 | - | _internal 测试桩 |
| 19 | POST | `/api/v1/brain/s3/_internal/test-self-healing` | 测试 | - | _internal 测试桩 |
| 20 | GET | `/api/v1/chat/test/action-examples` | 测试 | - | 对话能力测试样例 |
| 21 | GET | `/api/v1/chat/test/intent-examples` | 测试 | - | 对话能力测试样例 |
| 22 | POST | `/api/v1/chat/test/moderation` | 测试 | - | 对话能力测试样例 |
| 23 | POST | `/api/v1/chat/test/retry` | 测试 | - | 对话能力测试样例 |
| 24 | GET | `/api/v1/golden/acceptance-check` | 测试 | - | Golden 回归测试套件 |
| 25 | GET | `/api/v1/golden/datasets` | 测试 | - | Golden 回归测试套件 |
| 26 | GET | `/api/v1/golden/datasets/{dataset_id}` | 测试 | - | Golden 回归测试套件 |
| 27 | POST | `/api/v1/golden/export-report/{report_id}` | 测试 | - | Golden 回归测试套件 |
| 28 | GET | `/api/v1/golden/report/{report_id}` | 测试 | - | Golden 回归测试套件 |
| 29 | GET | `/api/v1/golden/reports/latest` | 测试 | - | Golden 回归测试套件 |
| 30 | POST | `/api/v1/golden/run` | 测试 | - | Golden 回归测试套件 |
| 31 | POST | `/api/v1/golden/run-single/{dataset_id}` | 测试 | - | Golden 回归测试套件 |
| 32 | GET | `/api/v1/golden/stats/summary` | 测试 | - | Golden 回归测试套件 |
| 33 | GET | `/api/v1/llm/_internal/test-mock-response` | 测试 | - | _internal 测试桩 |
| 34 | GET | `/api/v1/llm/_internal/test-mock-s1` | 测试 | - | _internal 测试桩 |
| 35 | POST | `/api/v1/llm/_internal/test-retry` | 测试 | - | _internal 测试桩 |
| 36 | GET | `/api/v1/loadtest/acceptance-check` | 测试 | - | 压测套件 |
| 37 | POST | `/api/v1/loadtest/chart-10k` | 测试 | - | 压测套件 |
| 38 | POST | `/api/v1/loadtest/concurrent-chat` | 测试 | - | 压测套件 |
| 39 | GET | `/api/v1/loadtest/report/{report_id}` | 测试 | - | 压测套件 |
| 40 | GET | `/api/v1/loadtest/reports/latest` | 测试 | - | 压测套件 |
| 41 | POST | `/api/v1/loadtest/run` | 测试 | - | 压测套件 |
| 42 | POST | `/api/v1/loadtest/upload-100k` | 测试 | - | 压测套件 |
| 43 | POST | `/api/v1/quality/_internal/test-quality` | 测试 | - | _internal 测试桩 |
| 44 | GET | `/api/v1/quality/debug/clean-stats` | 测试 | - | 质检 debug 注入/统计 |
| 45 | POST | `/api/v1/quality/debug/inject-dup` | 测试 | - | 质检 debug 注入/统计 |
| 46 | POST | `/api/v1/tokens/_internal/test-consume` | 测试 | - | _internal 测试桩 |
| 47 | POST | `/api/v1/tokens/_internal/test-exhausted` | 测试 | - | _internal 测试桩 |
| 48 | POST | `/api/v1/tokens/_internal/test-warning` | 测试 | - | _internal 测试桩 |
| 49 | GET | `/api/v1/tokens/status` | C | P2 | 用户拍板：可选鉴权（无token返最小信息） |
| 50 | GET | `/api/v1/brain/configs` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 51 | POST | `/api/v1/brain/configs` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 52 | POST | `/api/v1/brain/configs/update` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 53 | GET | `/api/v1/brain/configs/{config_key}` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 54 | GET | `/api/v1/brain/configs/{config_key}/history` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 55 | POST | `/api/v1/brain/configs/{config_key}/rollback` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 56 | POST | `/api/v1/brain/s2/generate` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 57 | POST | `/api/v1/brain/s2/generate-v2-table` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 58 | POST | `/api/v1/brain/s3/generate-dashboard` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 59 | POST | `/api/v1/brain/s3/generate-llm` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 60 | POST | `/api/v1/brain/s4/orchestrate` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 61 | POST | `/api/v1/brain/s4s5/orchestrate-and-score` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 62 | POST | `/api/v1/brain/s5/score` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 63 | GET | `/api/v1/brain/s5/score-config` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 64 | POST | `/api/v1/chat/classify-intent` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 65 | POST | `/api/v1/chat/execute-action` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 66 | POST | `/api/v1/chat/message` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 67 | POST | `/api/v1/exceptions/schema/heal` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 68 | POST | `/api/v1/exports/async` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 69 | POST | `/api/v1/exports/sync` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 70 | POST | `/api/v1/lineage/build` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 71 | POST | `/api/v1/lineage/rebuild-all` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 72 | POST | `/api/v1/llm/chat` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 73 | POST | `/api/v1/llm/chat/completions` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 74 | POST | `/api/v1/quality/check` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 75 | GET | `/api/v1/quality/check/ai/{dataset_id}` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 76 | POST | `/api/v1/quality/fix` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 77 | POST | `/api/v1/quality/fix-batch` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 78 | GET | `/api/v1/reports` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 79 | POST | `/api/v1/reports` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 80 | GET | `/api/v1/reports/{report_id}/html` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 81 | GET | `/api/v1/reports/{report_id}/json` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 82 | POST | `/api/v1/shares/create` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 83 | POST | `/api/v1/versions/create` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 84 | POST | `/api/v1/versions/rollback/{dashboard_id}` | 真漏 | P0 | 写操作/烧LLM配额/数据导出 — 高危 |
| 85 | GET | `/api/v1/brain/report/{dataset_id}/export` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 86 | POST | `/api/v1/brain/s1/detect` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 87 | POST | `/api/v1/brain/s1/detect-v2-table` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 88 | POST | `/api/v1/brain/s3/recommend` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 89 | POST | `/api/v1/brain/trace/run/complete` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 90 | POST | `/api/v1/brain/trace/run/start` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 91 | POST | `/api/v1/brain/trace/stage/complete` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 92 | POST | `/api/v1/brain/trace/stage/start` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 93 | GET | `/api/v1/brain/trace/{run_id}` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 94 | GET | `/api/v1/brain/trace/{run_id}/summary` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 95 | POST | `/api/v1/chat/sessions` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 96 | POST | `/api/v1/exceptions/async/timeout-check` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 97 | POST | `/api/v1/exceptions/batch-check` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 98 | POST | `/api/v1/exceptions/category/validate` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 99 | POST | `/api/v1/exceptions/conflict/detect` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 100 | POST | `/api/v1/exceptions/data-bloat/detect` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 101 | GET | `/api/v1/exceptions/empty-dashboard/{dashboard_id}` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 102 | POST | `/api/v1/exceptions/expired/cleanup` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 103 | POST | `/api/v1/exceptions/grain/validate` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 104 | POST | `/api/v1/exceptions/key-type/validate` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 105 | POST | `/api/v1/exceptions/orphan-rows/detect` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 106 | GET | `/api/v1/exceptions/report/{dataset_id}` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 107 | POST | `/api/v1/exceptions/sensitive/detect` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 108 | GET | `/api/v1/exceptions/session/kickout/{user_id}` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 109 | GET | `/api/v1/exports/status/{task_id}` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 110 | GET | `/api/v1/lineage/impact/{node_id}` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 111 | GET | `/api/v1/lineage/resolve` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 112 | POST | `/api/v1/lineage/verify` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 113 | POST | `/api/v1/shares/{share_id}/revoke` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 114 | POST | `/api/v1/tokens/applications/apply` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 115 | GET | `/api/v1/tokens/applications/check-active` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 116 | GET | `/api/v1/tokens/applications/my-applications` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 117 | GET | `/api/v1/tokens/applications/my-applications/{application_id}` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 118 | POST | `/api/v1/tokens/consume` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 119 | GET | `/api/v1/versions/list/{dashboard_id}` | 真漏 | P1 | 读他人数据/有限写 — 中危 |
| 120 | GET | `/api/v1/brain/s1/dictionary` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 121 | GET | `/api/v1/brain/s2/prompt-template` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 122 | GET | `/api/v1/brain/s2/types` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 123 | GET | `/api/v1/brain/s3/chart-types` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 124 | GET | `/api/v1/brain/s3/field-types` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 125 | GET | `/api/v1/brain/s3/grain-recommendations/{grain}` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 126 | GET | `/api/v1/brain/s3/rules` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 127 | POST | `/api/v1/brain/s3/validate-grain` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 128 | GET | `/api/v1/llm/rate-limit/status` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 129 | POST | `/api/v1/llm/template/render` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 130 | GET | `/api/v1/llm/usage/{user_id}` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 131 | GET | `/api/v1/skills` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 132 | GET | `/api/v1/tokens/can-send` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 133 | GET | `/api/v1/tokens/quota` | 真漏 | P2 | 只读/参考类，信息敏感低 |
| 134 | POST | `/api/v1/versions/compare` | 真漏 | P2 | 只读/参考类，信息敏感低 |

### B.2 真漏 P0 清单（优先修，共 35 个）

| 方法 | 端点 | 风险 |
|------|------|------|
| GET | `/api/v1/brain/configs` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/configs` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/configs/update` | 写操作/烧LLM配额/数据导出 — 高危 |
| GET | `/api/v1/brain/configs/{config_key}` | 写操作/烧LLM配额/数据导出 — 高危 |
| GET | `/api/v1/brain/configs/{config_key}/history` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/configs/{config_key}/rollback` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/s2/generate` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/s2/generate-v2-table` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/s3/generate-dashboard` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/s3/generate-llm` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/s4/orchestrate` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/s4s5/orchestrate-and-score` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/brain/s5/score` | 写操作/烧LLM配额/数据导出 — 高危 |
| GET | `/api/v1/brain/s5/score-config` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/chat/classify-intent` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/chat/execute-action` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/chat/message` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/exceptions/schema/heal` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/exports/async` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/exports/sync` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/lineage/build` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/lineage/rebuild-all` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/llm/chat` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/llm/chat/completions` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/quality/check` | 写操作/烧LLM配额/数据导出 — 高危 |
| GET | `/api/v1/quality/check/ai/{dataset_id}` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/quality/fix` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/quality/fix-batch` | 写操作/烧LLM配额/数据导出 — 高危 |
| GET | `/api/v1/reports` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/reports` | 写操作/烧LLM配额/数据导出 — 高危 |
| GET | `/api/v1/reports/{report_id}/html` | 写操作/烧LLM配额/数据导出 — 高危 |
| GET | `/api/v1/reports/{report_id}/json` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/shares/create` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/versions/create` | 写操作/烧LLM配额/数据导出 — 高危 |
| POST | `/api/v1/versions/rollback/{dashboard_id}` | 写操作/烧LLM配额/数据导出 — 高危 |

### B.3 真漏 P1 清单（共 35 个）

| 方法 | 端点 | 风险 |
|------|------|------|
| GET | `/api/v1/brain/report/{dataset_id}/export` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/brain/s1/detect` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/brain/s1/detect-v2-table` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/brain/s3/recommend` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/brain/trace/run/complete` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/brain/trace/run/start` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/brain/trace/stage/complete` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/brain/trace/stage/start` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/brain/trace/{run_id}` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/brain/trace/{run_id}/summary` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/chat/sessions` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/async/timeout-check` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/batch-check` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/category/validate` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/conflict/detect` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/data-bloat/detect` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/exceptions/empty-dashboard/{dashboard_id}` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/expired/cleanup` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/grain/validate` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/key-type/validate` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/orphan-rows/detect` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/exceptions/report/{dataset_id}` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/exceptions/sensitive/detect` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/exceptions/session/kickout/{user_id}` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/exports/status/{task_id}` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/lineage/impact/{node_id}` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/lineage/resolve` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/lineage/verify` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/shares/{share_id}/revoke` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/tokens/applications/apply` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/tokens/applications/check-active` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/tokens/applications/my-applications` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/tokens/applications/my-applications/{application_id}` | 读他人数据/有限写 — 中危 |
| POST | `/api/v1/tokens/consume` | 读他人数据/有限写 — 中危 |
| GET | `/api/v1/versions/list/{dashboard_id}` | 读他人数据/有限写 — 中危 |

### B.4 真漏 P2 清单（只读/参考类，共 15 个）

| 方法 | 端点 | 风险 |
|------|------|------|
| GET | `/api/v1/brain/s1/dictionary` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/brain/s2/prompt-template` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/brain/s2/types` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/brain/s3/chart-types` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/brain/s3/field-types` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/brain/s3/grain-recommendations/{grain}` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/brain/s3/rules` | 只读/参考类，信息敏感低 |
| POST | `/api/v1/brain/s3/validate-grain` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/llm/rate-limit/status` | 只读/参考类，信息敏感低 |
| POST | `/api/v1/llm/template/render` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/llm/usage/{user_id}` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/skills` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/tokens/can-send` | 只读/参考类，信息敏感低 |
| GET | `/api/v1/tokens/quota` | 只读/参考类，信息敏感低 |
| POST | `/api/v1/versions/compare` | 只读/参考类，信息敏感低 |
