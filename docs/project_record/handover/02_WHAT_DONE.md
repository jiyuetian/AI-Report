# 02 · 已完成项（WHAT_DONE）· v2

> 覆盖 night1 → night18 全量提交链。按时间序（旧→新），每条一行「hash · 类型 · 说明」。

## night1-4 · 项目基建 + 大扫除（2026-09-22）

```
0ba98b1 docs: 阶段6 ISS 债清单
01ce96b chore: 阶段3 清理（根目录诊断文档归位 + .gitignore 防护）
ba82356 fix(env): .env.example 指向正确业务库 aibi.db
c8273d5 docs: 阶段2 定规范 RULES/CONVENTIONS/CHANGELOG
bb5e35b docs: 阶段0 项目健康体检报告
693d90c fix(app): 修正启动打印误查仓库根/.env 的假告警
718019d fix(env): DuckDB 绝对路径化 + 启动 fail-fast（根治双库静默错配）
```

## night5-6 · LLM 限流诊断 + 对话承诺诚实化（2026-09-24）

- `docs/project_record/night_runs/night5/LLM_RATE_LIMIT_ANALYSIS.md`
- 修 A：llm_gateway failover 吞错（HTTP 200 内嵌错误体未切备胎）
- 修 D：chat.py 自然回复「假承诺」诚实兜底
- b.ai provider 删除（余额 0），zhipu 换 `glm-5.3-flash`
- ISS-030/031 登记

## night7 · 全量修复（2026-09-28）

```
c18537d fix(llm): failover 识别 HTTP 200 内嵌错误体并切备胎
05b7cd7 fix(chat): 诚实兜底 D 方案升级 + 跨会话冒领校验 + 入口探针
d12c419 fix(alert): 弹窗 P0 三件：探针测真实 provider 链 + 用户选择不静默吞 + 前端旁路封堵
4e6a667 fix(feasibility): 修复 _GENERIC_CONCEPT_WORDS NameError 致所有动作意图崩溃 (ISS-032)
b340e98 fix(chat): Q11 可行性检查放宽——泛指词不当字段要求
4e90ee5 fix(chat): 修复 _rule_extract_add_charts 中 is_avg 未初始化
```

## night8 · 图表引擎 + 台账（2026-09-29）

```
45fbcfa chore(backend): 启动日志打印 6 层 LLM provider 链
351f89a fix(chart): 修复规则引擎 CHART-01/02/03（散点/热力图 config 占位符 + 兜底饼图基数校验 + 直方图 bins 自适应）(ISS-034/035/036)
```

## night9-11 · 跨看板串号 + AI vs Rule + AI 参与率（2026-09-29 → 10-01）

- 跨看板上下文串号修复（`chat.py` 按「当前 dashboard_id + 登录用户」重定位）——ISS-038
- `DashboardPage.tsx` 加 `key={urlId}` 双保险
- `action_planner` 新增 `detect_confirmation`（好/可以/确认 → 执行 proposal；先不/不好 → cancel）

## night12-13 · K 基线 + AI 对话增强（2026-10-01）

- `night13/K_BASELINE.md` — AI 对话动作体系全量基线
- `action_planner` C 确认词承接（B5-1~B5-4）
- ISS-043/044 六层 LLM failover 模型透传 bug 修复

## night14 · Task A/B/C/D + ISS-058 登记（2026-10-02）

```
d62c4c3 docs(project_record): night14 变更日志登记 Task3
50308ea docs(ledger): night14 Task A LLM 链 7 层调整登记 (D-020)
a33f655 feat(chart-template): Task B 后端（表+CRUD+8预置+一键套用）
76e81ea feat(chart-template): Task B 前端（模板库入口+一键套用面板）
47681b1 feat(clean-chain): Task C 链路规则引擎（YAML+fail-fast+rule_id回链+改前备份）
269663c test(b-module)+docs(issues): Task D 模块B收尾 + 登记 ISS-058
```

- AI_TEST_CASES_v1.md v1.5：+模块 L（AI 操作日志白盒化 9 条）+ 模块 M（查询 API 6 条）
- ISS-058「把阈值调X%」登记为 OPEN（本轮只登记不实现）

## night15-16 · Task E/F/G/H/I（2026-10-02）

```
dd7af5c fix(frontend): Task E ISS-048 对话新增图柱值标签/长数字串格式化漏点修复
fed1476 fix(gateway): Task F ISS-045 LLM 调用失败指数退避重试（最多 3 次，8/16/24s）
a01deb1 feat(crud): Task G 最高权限 CRUD（走规则引擎 fail-fast）
2932834 feat(metric): Task H 派生指标完整版（14 业务指标 + 前端展示）
5f6c6a5 feat(recalc): Task I 下游重算一致性（C-16，事件驱动+依赖图+校验）
```

## night17 · Task J/K 使用统计 + 全链路联调（2026-10-02）

```
45a7ad6 night17: Task J 使用统计（J-8）+ Task K 全链路联调
e338981 night17 fix: analytics defaultdict 导入 + test_cases 断言修复 + usage_stats 完善
```

**night17 遗留**：`analytics.py` 只补了 `defaultdict` 遗漏 `time`；`test_runner.py` 契约不匹配（bool vs 元组）。

## night18 · ISS-058 阈值调整 + TEST-2 全量回归（2026-10-03）

```
f0cc1fb feat(threshold): ISS-058 阈值调整（adjust_threshold）+ remove_on_undo 撤销闭环
3ada5f8 docs(night18): ISSUES.md ISS-058 标 DONE + night18/ROUND_NOW.md 台账
849ccba fix(analytics): import time（night17 遗留 NameError 修复）
af4fd5b fix(test_runner): 兼容 IntegrationTestCase.run() bool 返回契约
```

**night18 交付**：
- ISS-058 落码：`intent_classifier`（ADJUST_THRESHOLD 意图 + 前缀停用词剥离 + % 归一化）+ `action_planner`（映射）+ `action_executor`（`_execute_adjust_threshold`，写 `config.thresholds`，区间 `(0,1]` 护栏，`remove_on_undo` 短路）
- TEST-2 全量回归：`_verify_taskg.py` 14/14 + `_verify_taski.py` 32/32 + `_verify_taskjk.py` 17/17（8 处脚本 bug 修复后）+ `_verify_iss058.py` 35/35 = **98 检查点全 PASS**
- 暴露 2 个真实生产 bug（`analytics.py import time`、`test_runner.py` 契约不匹配）——同批修复
- 新登记 **ISS-059**：`compute_stats` 对 `e["data"]` 未 `.get` 防御

## 本轮（v2 handover）文档补齐

- 4 份 NIGHT_SUMMARY 补齐：night15/16/17/18
- handover 7 文件重写：v1（`0ba98b1`）→ v2（`af4fd5b`）
- `AI_TEST_CASES_v1.md` v1.6：+模块 N（ISS-058 阈值调整 8 条）

## 提交纪律

- 每 night 至少一份 `NIGHT_SUMMARY.md`（本轮补 night15-18 后，全部无断档）
- 每 night 台账登 `AI_CHANGES.md`（本轮 AI_CHANGES 已到 §14）
- ISS 编号不复用（ISS-037 已澄清规则）
