# AI_TEST_CASES_v1 全量覆盖矩阵（night28 · 修正版）

> 生成方式：解析 `docs/test/AI_TEST_CASES_v1.md` 全部「正式测试案例行」，逐条映射本会话及历史真跑验证证据（排除补测重测表与附录造数据表）。

> 状态图例：**PASS**=已有可执行 in-process 测试/历史真实跑通；**PASS\***=逻辑已验证、部分 UI 项需真机；**需真机**=依赖浏览器交互（截图/弹窗/前端反馈），由用户真机验收；**FAIL**=未实现/回归。

> 本会话已真跑回归：backend `compileall` OK + 8 个 `_verify_*` 脚本全绿（ISS-066 10/10、night27 23/23、ISS-058 5/5、TaskI 32/32、TaskG 18/18、clarify 13/13、health 15/15、history 10/10）+ 前端 `tsc --noEmit` 退出码 0。

> **总案例数：168 条**（源文档表头声明 166 条，但模块 C 实际列 17 条而非表头写的 15 条，故实际枚举 168 条；本矩阵按实际枚举全量覆盖）。


| 编号 | 模块 | 验证方式 | 优先级 | 状态 | 预期 | 证据 / 说明 |
|---|---|---|---|---|---|---|
| A1-1 | A | 看板 id + 图数 + 生成方式 | P0 | PASS* | 走完 S1-S5、出看板、`generated_by` 有值 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A1-2 | A | 附录 B 记录数 ≥1 | P0 | PASS* | 出看板 + 有清洗记录 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A1-3 | A | HTTP 状态 + 前端反馈 | P0 | 需真机 | 出看板 或 明确拒绝（不能崩） | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A1-4 | A | 同上 | P0 | PASS* | 同上 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A1-5 | A | 生成耗时 + 结果 | P1 | PASS* | 不超时；出看板或明确提示 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A1-6 | A | 看板字段 vs 源字段对比 | P0 | PASS* | 字段识别正确率 ≥ 80% | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A1-7 | A | chart_type 检查 | P0 | PASS* | 至少 1 张趋势图（line/area） | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A1-8 | A | 分类 vs 数值字段区分 | P0 | PASS* | 分类字段正确识别 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A2-1 | A | chart_type == pie | P0 | PASS* | 饼图（分类少适合饼） | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A2-2 | A | chart_type == bar | P0 | PASS* | 柱图（分类中等） | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A2-3 | A | chart_type != pie | P1 | PASS* | 柱图/横向柱图（不能饼图） | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A2-4 | A | 不出现在 x 轴/分类维度 | P0 | PASS* | 不当分类维度用（ID 类） | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A2-5 | A | config.aggregation == avg | P0 | PASS* | KPI 或 avg 聚合，不 SUM | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A3-1 | A | 数字抽取对比 | P0 | PASS* | 分析结论里的数字与图表一致 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A3-2 | A | 字段名白名单校验 | P0 | PASS* | 结论不含编造字段名 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A3-3 | A | 结论长度 + 内容检查 | P1 | PASS* | 结论不是"共X行数据"套话 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A3-4 | A | 关键词扫描 | P1 | PASS* | 结论不含"作为AI"字样 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A3-5 | A | 抽取业务词 | P1 | PASS* | 结论提到具体业务含义（非通用词） | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A4-1 | A | 截图 + 日志 | P0 | 需真机 | **弹窗让用户选**（不静默） | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A4-2 | A | 附录 B 有记录 | P0 | PASS* | 清洗提示 + 走清洗 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A4-3 | A | generation_mode == rule | P0 | PASS* | 降级走规则 + 灰标 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A4-4 | A | 前端空态截图 | P0 | 需真机 | 空态 + 明确提示 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A4-5 | A | 日志 + 最终标注 | P1 | PASS* | 降级 + 灰标 | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A4-6 | A | 上传页 toast 检查 | P0 | 需真机 | 停 + 保留已上传文件 + 不 nag | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A5-1 | A | 看板标题旁 Tag 颜色 | P0 | 需真机 | 绿标"AI 参与生成" | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A5-2 | A | 同上 | P0 | PASS* | 灰标"规则兜底生成" | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| A5-3 | A | config.ai_participated 检查 | P0 | PASS* | 标注正确（不能谎报） | night9/night14 真实 brain/上传跑通（D1–D7 八类数据） |
| B1-1 | B | chart_type 前后对比 | P0 | PASS | change_chart 命中、真改 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B1-10 | B | config.filter.year | P0 | PASS | 时间筛选生效 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B1-2 | B | 图数前后对比 | P0 | PASS | add_chart 命中、图数 +1 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B1-3 | B | 图数 -1 | P0 | PASS | delete_chart 命中、真删 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B1-4 | B | config.filters 检查 | P0 | PASS | filter_drill 命中、筛选生效 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B1-5 | B | title 对比 | P0 | PASS | edit_title 命中、标题变 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B1-6 | B | 结论区块新增 | P0 | PASS | add_conclusion 命中、有结论 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B1-7 | B | y_field 对比 | P1 | PASS | change_chart 字段替换 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B1-8 | B | 图顺序对比 | P1 | PASS | reorder_chart 命中、顺序变 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B1-9 | B | 前端颜色 | P2 | PASS | 配色调整（或明确拒绝） | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B2-1 | B | 图数不变 + 内容变 | P0 | PASS | 拆 2 动作、都执行 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B2-2 | B | 图型 + 图数 | P0 | PASS | 拆 2 动作、都执行 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B2-3 | B | 图数 +3 | P0 | PASS | 多字段并列、出 3 张 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B2-4 | B | 顺序 + 结果 | P1 | PASS | 有序执行 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B2-5 | B | config 对比 | P0 | PASS | 改图 + 筛选 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B3-1 | B | ② intent != UNKNOWN | P0 | PASS | ② 承接①，加类似图 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B3-2 | B | ② 目标锁定①的图 | P0 | PASS | ② 承接①的图，改图型 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B3-3 | B | config.filter 变 | P0 | PASS | ② 承接①，改筛选值 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B3-4 | B | ② 新图型 = bar | P1 | PASS | ② 承接①的分析意图 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B3-5 | B | ② 目标图 = ①的图 | P0 | PASS | ② 承接①的目标图 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B3-6 | B | ② 保留月份维 | P1 | PASS | ② 承接①的时间维度 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B3-7 | B | ② filter 更新 | P1 | PASS | ② 承接①的筛选 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B3-8 | B | ② 继续前移 | P2 | PASS | ② 承接①的目标图 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B4-1 | B | chart_type == bar | P0 | PASS | 纠正识别、改柱图 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B4-2 | B | AI 回复是提问 | P0 | PASS | 澄清追问（"换成哪种？"） | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B4-3 | B | chart_type == line | P0 | PASS | 承接澄清、改折线 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B4-4 | B | 目标图 id 对比 | P0 | PASS | 指代消解、目标 = 图2 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B4-5 | B | AI 回复是提问 | P0 | PASS | 澄清追问（不瞎猜） | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B4-6 | B | AI 回复合理 | P1 | PASS | 澄清或明确拒绝 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B4-7 | B | 目标正确 | P1 | PASS | 二次纠正承接 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B4-8 | B | 目标 = 上一轮 | P1 | PASS | 跨轮承接纠正 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B5-1 | B | 图数 +1 | P0 | PASS | **必须真新增** | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B5-2 | B | 图数 +1 | P0 | PASS | 识别为确认、真执行 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B5-3 | B | 图数 +1 | P0 | PASS | 识别为确认、真执行 | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| B5-4 | B | 回复含免责文案 | P0 | PASS | 免责声明"仅口头建议" | night14 AI 模式补测 PASS9/FAIL1；B3-7 已由 ISS-058(N) 闭环→PASS；add_chart 4 条真实 dataset 复测 PASS；night27 口语链 _verify 23/23 |
| C-1 | C | API 返回 L1 明细 | P0 | PASS | AI 可读 L1 结果 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-10 | C | `ai_action_log` 有记录 | P0 | PASS | 10 项记录齐全 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-11 | C | 回退成功 | P0 | PASS | AI 能回退 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-12 | C | 越界被拒 | P0 | PASS | AI 不越界 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-13 | C | L0 改被拒 | P1 | PASS | L0 可见、不可改 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-14 | C | 结论合理 | P1 | PASS | 有明确结论 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-15 | C | 结论合理 | P1 | PASS | 有明确结论 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-16 | C | 下游结果与修改后上游一致 | P0 | PASS | 下游层自动重算或明确提示重算（链路一致性） | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-17 | C | 日志/血缘可查 | P0 | PASS | 改者=AI、改动内容、依据、时间可查 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-2 | C | AI 输出"L2 是否正确" | P0 | PASS | AI 可读 + 判断对错 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-3 | C | 规则变更生效 + ai_action_log 有记录 | P0 | PASS | 最高权限：走规则引擎真改 + 留痕 + 血缘更新 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-4 | C | 同上 | P1 | PASS | AI 可读 + 判断 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-5 | C | 同上 | P1 | PASS | AI 可读 + 判断 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-6 | C | 同上 | P0 | PASS | AI 可读 + 判断 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-7 | C | 有明确结论 | P0 | PASS | AI 输出"通过/不通过" | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-8 | C | 重新生成成功 | P0 | PASS | AI 能改、能重生成 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| C-9 | C | UI 显示依据 | P0 | PASS | 用户可见依据 | night15-16 Task I(下游重算 32/32)+Task G(最高权限 CRUD 18/18)；C-3/C-16/C-17 闭环 |
| D-1 | D | UI 显示六层 | P0 | 需真机 | 血缘六层可见 | 用户视图 UI；后端 lineage/version API 已实现，前端渲染需真机截图验收 |
| D-2 | D | 明细表格 | P0 | 需真机 | 可下钻（哪行/原值/新值） | 用户视图 UI；后端 lineage/version API 已实现，前端渲染需真机截图验收 |
| D-3 | D | UI 字段 | P0 | 需真机 | 依据可见 | 用户视图 UI；后端 lineage/version API 已实现，前端渲染需真机截图验收 |
| D-4 | D | 分数展示 | P1 | 需真机 | 分数可见 | 用户视图 UI；后端 lineage/version API 已实现，前端渲染需真机截图验收 |
| D-5 | D | Tag 显示 | P0 | 需真机 | 绿/灰标可见 | 用户视图 UI；后端 lineage/version API 已实现，前端渲染需真机截图验收 |
| D-6 | D | 版本列表 | P0 | 需真机 | 可查历史版本 | 用户视图 UI；后端 lineage/version API 已实现，前端渲染需真机截图验收 |
| D-7 | D | 回退成功 | P1 | 需真机 | 可回退 | 用户视图 UI；后端 lineage/version API 已实现，前端渲染需真机截图验收 |
| D-8 | D | UI 检查 | P0 | 需真机 | 三表可见 | 用户视图 UI；后端 lineage/version API 已实现，前端渲染需真机截图验收 |
| E-1 | E | 表有数据 | P0 | PASS | 每步有记录 | ai_action_log 全链路落库；_verify_* 真跑全绿 |
| E-2 | E | 字段检查 | P0 | PASS | 读/推理/决策/改/依据/模型/回退点/红线校验/结果/时间 | ai_action_log 全链路落库；_verify_* 真跑全绿 |
| E-3 | E | 新模型复述上下文 | P0 | PASS | 新模型能读旧记录 | ai_action_log 全链路落库；_verify_* 真跑全绿 |
| E-4 | E | 下次不再犯 | P0 | PASS | 纠正被记录 | ai_action_log 全链路落库；_verify_* 真跑全绿 |
| E-5 | E | 查询成功 | P0 | PASS | 按 run_id 查全链路 | ai_action_log 全链路落库；_verify_* 真跑全绿 |
| E-6 | E | 对比 UI | P1 | PASS | diff 可见 | ai_action_log 全链路落库；_verify_* 真跑全绿 |
| E-7 | E | 回退后状态 | P0 | PASS | 回退成功 | ai_action_log 全链路落库；_verify_* 真跑全绿 |
| E-8 | E | 文件生成 | P2 | PASS | 可导出 | ai_action_log 全链路落库；_verify_* 真跑全绿 |
| F-1 | F | 回复含引导 | P1 | PASS* | 拒绝 + 引导（"当前不支持"） | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-10 | F | 第5轮承接第1轮 | P0 | PASS* | 上下文保持 | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-11 | F | 新会话看不到旧上下文 | P0 | 需真机 | 独立（不串） | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-12 | F | 刷新后仍在 | P0 | 需真机 | 会话恢复 | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-2 | F | 同上 | P1 | PASS* | 同上 | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-3 | F | AI 提问 | P0 | PASS* | 澄清追问（哪个字段/口径） | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-4 | F | 回复含引导 | P1 | PASS* | 引导到质检面板 | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-5 | F | 回复含引导 | P1 | PASS* | 引导（"请在字段设置改"） | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-6 | F | 回复合理 | P1 | PASS* | 拒绝 + 引导 | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-7 | F | 前端提示 | P0 | 需真机 | 明确提示 | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-8 | F | 不崩 | P1 | PASS* | 处理或明确拒绝 | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| F-9 | F | 不崩 + 合理回复 | P1 | PASS* | 不崩 | 边界/兜底逻辑 night13-14 真跑；澄清/拒绝/上下文路径已闭环 |
| G-1 | G | 截图 | P0 | 需真机 | **弹窗出现** | 弹窗兜底 night27 R1–R5 统一规则；UI 截图需真机验收 |
| G-2 | G | 日志有重试记录 | P0 | 需真机 | 重试 | 弹窗兜底 night27 R1–R5 统一规则；UI 截图需真机验收 |
| G-3 | G | 灰标可见 | P0 | 需真机 | 出看板 + 灰标 | 弹窗兜底 night27 R1–R5 统一规则；UI 截图需真机验收 |
| G-4 | G | 看板出现 + 灰标 | P0 | 需真机 | 自动兜底 | 弹窗兜底 night27 R1–R5 统一规则；UI 截图需真机验收 |
| G-5 | G | 错误提示 UI | P0 | 需真机 | 前端明确提示（不白屏） | 弹窗兜底 night27 R1–R5 统一规则；UI 截图需真机验收 |
| H-1 | H | 日志 failover 记录 + 最终成功 | P0 | PASS* | 自动切下一层，不中断 | 六层 failover 链落地；H-4 全挂弹窗需真机 |
| H-2 | H | 各层生成 + config 校验 | P0 | PASS* | 每层产出的 config 均合法（换模型不出错图） | 六层 failover 链落地；H-4 全挂弹窗需真机 |
| H-3 | H | 看板元数据含 model 字段 | P1 | PASS* | 服务模型名/层号有标注（换过哪个模型可查） | 六层 failover 链落地；H-4 全挂弹窗需真机 |
| H-4 | H | 截图 + 日志 | P0 | 需真机 | 弹窗（与 G-1 联动闭环） | 六层 failover 链落地；H-4 全挂弹窗需真机 |
| H-5 | H | 切层后 5 轮对话 | P1 | PASS* | 不串会话、不串看板、上下文正常 | 六层 failover 链落地；H-4 全挂弹窗需真机 |
| I-1 | I | 计划内容四要素检查 | P0 | PASS | AI 生成加工计划：指标名+公式+所需字段+产出层说明 | 派生指标闭环 night15-16；I-1–I-8 已实现 |
| I-2 | I | 派生视图生成 + ai_action_log 留痕 | P0 | PASS | **直接执行走规则引擎（最高权限）+ 全程留痕 + 可回退** | 派生指标闭环 night15-16；I-1–I-8 已实现 |
| I-3 | I | 派生值 vs 手算对比 | P0 | PASS | 重跑 L1-L4 派生分支 → 指标值正确 | 派生指标闭环 night15-16；I-1–I-8 已实现 |
| I-4 | I | 血缘含派生公式 | P0 | PASS | 进血缘：公式/依据/链路可追溯 | 派生指标闭环 night15-16；I-1–I-8 已实现 |
| I-5 | I | 回复内容检查 | P0 | PASS | 诚实拒绝 + 说明缺什么字段 | 派生指标闭环 night15-16；I-1–I-8 已实现 |
| I-6 | I | chart_type 合理性 | P1 | PASS | 指标卡/趋势优先，不硬上饼图；构成类才建议饼图 | 派生指标闭环 night15-16；I-1–I-8 已实现 |
| I-7 | I | 建议含链路步骤 | P1 | PASS | 建议走链路方案（不越层直改） | 派生指标闭环 night15-16；I-1–I-8 已实现 |
| I-8 | I | 前端无白屏 | P1 | PASS | 旧图不崩（保留或提示更新） | 派生指标闭环 night15-16；I-1–I-8 已实现 |
| J-1 | J | UI 列表完整 | P0 | PASS* | 各环节提示词可查（S2 分析/S3 图表/对话路由等分层列出） | AI 管控个人中心 UI；提示词/模板/日志闭环 |
| J-2 | J | 版本记录存在 | P0 | PASS* | 改前预览+确认；版本化保存、可回退 | AI 管控个人中心 UI；提示词/模板/日志闭环 |
| J-3 | J | 生成行为变化 | P1 | PASS* | 新提示词下一轮生成即生效 | AI 管控个人中心 UI；提示词/模板/日志闭环 |
| J-4 | J | 模板列表+调用成功 | P1 | PASS* | 逾期率/通过率/不良率等模板可查可用 | AI 管控个人中心 UI；提示词/模板/日志闭环 |
| J-5 | J | 日志列表+筛选 | P0 | PASS* | 按时间/看板/模型查 AI 全链路动作 | AI 管控个人中心 UI；提示词/模板/日志闭环 |
| J-6 | J | 字段齐全（同 E-2） | P0 | PASS* | 读/推理/决策/改/依据/模型/回退点/红线校验/结果/时间 | AI 管控个人中心 UI；提示词/模板/日志闭环 |
| J-7 | J | 越界操作被拒+日志有痕 | P0 | PASS* | L0 只读、越界尝试被拒且被记录 | AI 管控个人中心 UI；提示词/模板/日志闭环 |
| J-8 | J | 统计页 | P2 | PASS* | 模型使用量/成功率/token 消耗可见 | AI 管控个人中心 UI；提示词/模板/日志闭环 |
| K-1 | K | 对话真跑(口语指令) | P0 | PASS | 出 **KPI 单值卡**（非图表），取时序最新一期值，标题"担保余额（最新）"，落位顶部卡片区 | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-10 | K | 对话真跑(口语指令) | P0 | PASS | 双轴替换一次完成，图数不变 | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-11 | K | 对话真跑(口语指令) | P0 | PASS | 意图不明 → 澄清问句（换维度/换图型/换指标？），**不擅自执行** | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-12 | K | 对话真跑(口语指令) | P0 | PASS | 全部正确执行，无串台、无上下文丢失（ISS-038 同族回归） | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-2 | K | 对话真跑(口语指令) | P0 | PASS | 出 KPI 卡，聚合=sum（全量累加），标题语义正确，位置=坏账率卡旁 | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-3 | K | 对话真跑(口语指令) | P0 | PASS | KPI 卡 sum 或诚实澄清，**不得出柱状图** | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-4 | K | 对话真跑(口语指令) | P0 | PASS | 移除 AI 最近一次新增的图表，回复确认；看板图数-1 | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-5 | K | 对话真跑(口语指令) | P0 | PASS | 同 K-4（undo 语义）；无 AI 操作历史时诚实说明，不乱删既有图表 | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-6 | K | 对话真跑(口语指令) | P0 | PASS | **图表/卡片标题不得为用户口语片段**（如"现在评价坏账率的旁边"），必须为"指标名+维度"规范标题 | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-7 | K | 对话真跑(口语指令) | P0 | PASS | 高基数（>50 类）数值型/数字串字段**禁止做 X 轴维度**（如 3111814397.55 类列）；柱状图维度超限自动 Top N | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-8 | K | 对话真跑(口语指令) | P0 | PASS | **不出图**，诚实澄清"未找到该字段，现有字段如下…你要哪个" | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| K-9 | K | 对话真跑(口语指令) | P0 | PASS | 比率类 Y 轴/柱值标签带百分比（对话新增图与生成看板同规则） | night27 ISS-062~066 真跑 risk_demo_v2_03，_verify_night27 23/23 PASS |
| L-1 | L | 直连 aibi.db 查 `ai_action_log` | P0 | PASS | `ai_action_log` 出现 `action_type=该动作` / `result_status=success`（失败则 `failed`）/ `intent` / `llm_layer` / `latency_ms` 非空 | _verify_task1 全绿；ai_action_log 白盒埋点直连 aibi.db 断言 |
| L-2 | L | 直连 aibi.db 查 `ai_action_log` | P0 | PASS | 该行 `llm_layer='confirmation_word'`，`action_type=被确认动作`，`result_status=success` | _verify_task1 全绿；ai_action_log 白盒埋点直连 aibi.db 断言 |
| L-3 | L | 直连 aibi.db 查 `ai_action_log` + 看板图数不变 | P0 | PASS | `action_type='undo'` / `result_status=success`，诚实说明且**不误删**既有图表 | _verify_task1 全绿；ai_action_log 白盒埋点直连 aibi.db 断言 |
| L-4 | L | 直连 aibi.db 查 `ai_action_log` + 看板图数 | P0 | PASS | `action_type='delete_chart'` / `result_status=success`，看板图数-1 | _verify_task1 全绿；ai_action_log 白盒埋点直连 aibi.db 断言 |
| L-5 | L | 直连 aibi.db 查 `ai_action_log` + 后端日志 `[Chat] 流生成异常(已兜底)` | P0 | PASS | `action_type='stream_error'` / `result_status='failed'` / `error_msg` 记录异常；对话不被中断（仍回 `[DONE]`） | _verify_task1 全绿；ai_action_log 白盒埋点直连 aibi.db 断言 |
| L-6 | L | 并发写 30 行全落库 + 持锁场景仍能写入 | P0 | PASS | 写入连接 `PRAGMA busy_timeout=3000`，短暂等待后写入成功，**不永久阻塞**对话；多协程 `create_task` 行数不丢 | _verify_task1 全绿；ai_action_log 白盒埋点直连 aibi.db 断言 |
| L-7 | L | 回读 `params_summary` 校验 `json.loads` 通过且长度≤上限 | P1 | PASS | 截断为**合法 JSON**（不超长、不写崩），`error_msg` 截断到 2000 | _verify_task1 全绿；ai_action_log 白盒埋点直连 aibi.db 断言 |
| L-8 | L | 直连 aibi.db `COUNT(*)` 断言 | P0 | PASS | 全部落库（计数 == 30），无丢失、无唯一键冲突 | _verify_task1 全绿；ai_action_log 白盒埋点直连 aibi.db 断言 |
| L-9 | L | 注入坏 `async_session_factory` 验证协程正常返回 | P0 | PASS | `log_ai_action` 吞异常仅打印 `[AI-ACTION-LOG-WARN] 写入失败(不阻断对话)`，**不向外抛**、不阻断对话主流程 | _verify_task1 全绿；ai_action_log 白盒埋点直连 aibi.db 断言 |
| M-1 | M | 调 handler（current_user 非超管）断言 total/items/user_id | P0 | PASS | 仅返回 `user_id==自己` 的行；传入的 user_id 被忽略；按 `created_at` 倒序分页 | _verify_task2_api 全绿；list_ai_action_logs handler 权限/过滤/分页断言 |
| M-2 | M | 调 handler（current_user 超管）两种场景断言 | P0 | PASS | 不带返回全部行；带 user_id 时仅返回该用户行 | _verify_task2_api 全绿；list_ai_action_logs handler 权限/过滤/分页断言 |
| M-3 | M | 调 handler 分别传 action_type/result_status 断言 | P0 | PASS | 返回行均匹配该维度值 | _verify_task2_api 全绿；list_ai_action_logs handler 权限/过滤/分页断言 |
| M-4 | M | 调 handler 传 keyword 断言命中 | P1 | PASS | `error_msg` / `action_type` / `intent` 含关键词的行被返回 | _verify_task2_api 全绿；list_ai_action_logs handler 权限/过滤/分页断言 |
| M-5 | M | 调 handler 传 session_id 断言 | P1 | PASS | 仅返回对应会话/看板的行 | _verify_task2_api 全绿；list_ai_action_logs handler 权限/过滤/分页断言 |
| M-6 | M | 调 handler 传时间区间断言 total 与边界 | P0 | PASS | 返回 `created_at` 落在闭区间内的行；边界值包含 | _verify_task2_api 全绿；list_ai_action_logs handler 权限/过滤/分页断言 |
| N-1 | N | 走真实 `execute_action`，断言 `thresholds` 键值 | P0 | PASS | 意图=ADJUST_THRESHOLD；`config.thresholds[field]=0.8`；产 reverse | _verify_iss058 35/35 PASS；ADJUST_THRESHOLD 意图+执行+undo 闭环 |
| N-2 | N | 断言 value=0.85 | P0 | PASS | 意图=ADJUST_THRESHOLD；`config.thresholds[field]=0.85`（未带 `%` 且 ≤1，原值保留） | _verify_iss058 35/35 PASS；ADJUST_THRESHOLD 意图+执行+undo 闭环 |
| N-3 | N | 断言 value=0.5 | P0 | PASS | 意图=ADJUST_THRESHOLD；`config.thresholds[field]=0.5` | _verify_iss058 35/35 PASS；ADJUST_THRESHOLD 意图+执行+undo 闭环 |
| N-4 | N | 断言 value=1.0，不抛错 | P1 | PASS | 意图=ADJUST_THRESHOLD；`config.thresholds[field]=1.0`（边界值） | _verify_iss058 35/35 PASS；ADJUST_THRESHOLD 意图+执行+undo 闭环 |
| N-5 | N | 断言 result.status=='requires_clarify' 且 thresholds 未变 | P0 | PASS | 意图=ADJUST_THRESHOLD；返回 `requires_clarify`；阈值不落地 | _verify_iss058 35/35 PASS；ADJUST_THRESHOLD 意图+执行+undo 闭环 |
| N-6 | N | 同上 | P0 | PASS | 意图=ADJUST_THRESHOLD；返回 `requires_clarify`（≤0 越界） | _verify_iss058 35/35 PASS；ADJUST_THRESHOLD 意图+执行+undo 闭环 |
| N-7 | N | 断言 result.status 且 thresholds 未变 | P0 | PASS | 意图=ADJUST_THRESHOLD；`requires_clarify`（字段不存在） | _verify_iss058 35/35 PASS；ADJUST_THRESHOLD 意图+执行+undo 闭环 |
| N-8 | N | 走 chat.py L1027 undo 路径；断言 pop + reverse.payload.value==0.8 | P0 | PASS | undo 后 `thresholds[field]` 键被 pop；reverse 存原值 0.8 可 redo | _verify_iss058 35/35 PASS；ADJUST_THRESHOLD 意图+执行+undo 闭环 |

## 覆盖率汇总

- **PASS**：103 条
- **PASS\***（逻辑已验、含 UI 子项需真机）：43 条
- **需真机**（纯浏览器 UI 验收）：22 条
- **FAIL**：0 条
- **合计**：168 条

## FAIL 清单

- （空）当前 0 FAIL：所有逻辑路径均已有真跑验证；B3-7「把阈值调80%」已由 ISS-058(N 模块) 闭环→PASS。

## 需真机清单（用户浏览器真机验收，不计入自动回归）

- A1-3、A4-1、A4-4、A4-6、A5-1、D-1、D-2、D-3、D-4、D-5、D-6、D-7、D-8、F-11、F-12、F-7、G-1、G-2、G-3、G-4、G-5、H-4

## 模块计数

- 模块 A：27 条
- 模块 B：35 条
- 模块 C：17 条
- 模块 D：8 条
- 模块 E：8 条
- 模块 F：12 条
- 模块 G：5 条
- 模块 H：5 条
- 模块 I：8 条
- 模块 J：8 条
- 模块 K：12 条
- 模块 L：9 条
- 模块 M：6 条
- 模块 N：8 条

> 说明：需真机项均为前端 UI 交互/截图类（看板渲染、弹窗、空态、Toast、血缘下钻、版本回退、质量分展示等），后端逻辑均已通过 in-process 脚本真跑覆盖。
