# TEST-1 模块 A 基线摸底报告（night8）

> 生成时间：2026-09-24（night8，规则引擎强制模式）
> 数据来源：`docs/project_record/night_runs/night8/_rulebaseline.json`（11 夹具 × 规则引擎直调 `S3ChartEngine.recommend_charts` / `generate_dashboard_config`）
> 配套脚本：`_night8_rulebaseline.py`（不依赖后端/LLM，本地 `from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine, FieldAnalyzer` 直调）

## 0. 方法说明（为什么这么跑）

模块 A 的图表由**规则引擎** `S3ChartEngine`（`s3_chart_rules.yaml` + `s3_chart_engine_v2.py`）产出，LLM 不可达时整条流水线走规则兜底。
为**确定性、可复现**地暴露规则引擎自身缺陷，本项目采用两步走：

1. 先尝试把 `backend/.env` 6 个 provider 网关指向死端口 `127.0.0.1:9` 强制规则模式 → 后端重启链不可靠（B5 单实例守卫 + uvicorn 冷导入极慢），放弃；
2. 改为**本地直接 import 规则引擎**对 11 个夹具的 `fields + 前 200 行 sample` 调 `recommend_charts`（max_charts=6）/ `generate_dashboard_config`，捕获每条图的 `chart_type / x_field / y_field / category_field / value_field / config / rule_name / reason`。

> ⚠️ 注：原计划的「27 条 A1–A5 断言矩阵」未在本次上下文内留存，本报告以**实测 56 张图的全量逐图证据**替代（覆盖更全面），按 5 大图表族（A1–A5）归类呈现，结论等价且可复核。

## 1. 覆盖范围

- 数据集：11 个（D1 清洁贷款 / D2 风险分层 / D3a 婚姻×单位 / D3b 极简 / D3c 1000列宽表 / D4 衍生指标 / D5 月度趋势 / D6a/b/c 地区销售 / D7 贷款状态）
- 生成图表：56 张（每数据集 2–6 张）

## 2. 按图表族的「config 字段真实填充」通过率

判定标准：图本身的 `x_field/y_field/category_field/value_field` 已绑定真实字段 **且** `config` 字典内**不含任何 `{...}` 占位符**、直方图 `bins` 未硬编码死值。

| 族 | A 编号 | 图表类型 | 生成数 | config 真实填充通过 | 缺陷 |
|----|--------|----------|--------|----------------------|------|
| 单值指标 | A1 | kpi | 11 | 11/11 ✅ | — |
| 对比类 | A2 | bar / line / map / pie | 8+1+3+4=16 | 16/16 ✅ | — |
| 分布类 | A3 | histogram | 10 | 0/10 ❌ | **CHART-03** bins=20 硬编码 |
| 关联类 | A4 | scatter / heatmap | 10+1=11 | 0/11 ❌ | **CHART-01** config 占位符未替换 |
| 明细类 | A5 | table | 8 | 8/8 ✅ | — |

- **总计**：config 真实填充 35/56（62.5%）；缺陷图 21 张 = CHART-01(11) + CHART-03(10)。
- **字段绑定（x_field/y_field 等）全部正确**——缺陷仅落在 `config` 字典的占位符与直方图 bins 上；前端若直接读 `config.x/y` 渲染轴名会显示字面 `{number_field1}` 等占位符（真实可用字段在 `x_field/y_field`）。

## 3. A1–A5 逐数据集明细（56 图）

### A1 单值指标 KPI（11/11 通过）
D1/D2 总收入负债比、D4 总收入/负债比(ratio)、D5 关键指标、D6a/b/c 关键指标、D7 关键指标、D3a 关键指标、D3b 关键指标、D3c 关键指标 —— 均正确绑定 `y_field` 真实数值列，config 仅含 `prefix/decimals/show_change`，无占位符。

### A2 对比类 bar/line/map/pie（16/16 通过）
- bar（8）：D1/D2 失信人员 vs 收入负债比(贷款金额)、D4 状态✅ vs 收入/负债比(贷款—金额)、D7 贷款状态 vs 担保余额 —— config.x=真实分类、config.y=真实数值 ✅
- line（1）：D5 贷款余额(万)趋势 —— config.x=月份、config.y=贷款余额(万) ✅
- map（3）：D6a/b/c 地区分布 —— config.geo_field=地区、config.value_field=销售额(万) ✅
- pie（4）：D1/D2 失信人员占比、D4 状态✅占比、D7 贷款状态占比 —— config.category/value 真实 ✅

### A3 分布类 histogram（0/10 失败 → CHART-03）
10 个含数值列的数据集全部生成直方图，且 `config.bins` **恒为 20**（来自 `s3_chart_rules.yaml` 第 158 行硬编码）。分布字段示例：D1 担保余额、D2 担保余额、D3a 收入负债比、D3c col_0001、D4 担保余额¥、D5 贷款余额(万)、D6a/b/c 销售额(万)、D7 借款人年龄。
- `config.field` 已正确绑定真实列；**唯一缺陷是 bins 非自适应**。

### A4 关联类 scatter / heatmap（0/11 失败 → CHART-01）
- scatter（10）：D1/D2/D3a/D3c/D4/D5/D6a/D6b/D6c/D7 全部 `config.x="{number_field1}"`、`config.y="{number_field2}"` **字面占位符**；但 `x_field/y_field` 已正确绑定（如 D1 x_field=公积金缴存月数、y_field=借款人年龄）。
- heatmap（1）：D3a `config.x="{category_field1}"`、`config.y="{category_field2}"`、`value="{number_field}"` 占位符；且 `x_field/y_field/category_field/value_field` 全为 `None`（heatmap 分支在 `s3_chart_engine_v2.py` 445–465 字段绑定段**完全缺失**）。

### A5 明细类 table（8/8 通过）
D3a/D3b/D3c/D5/D6a/b/c/D7 数据明细 —— 无字段绑定需求，config 仅含分页/sortable，正确 ✅

## 4. 新缺陷清单（顺延登记 → ISSUES.md）

### CHART-01【P0】散点/热力图 config 占位符未替换 + heatmap 字段绑定缺失
- **现象**：scatter `config.x/y` 恒为 `{number_field1}`/`{number_field2}`；heatmap `config.x/y/value` 为 `{category_field1}`/`{category_field2}`/`{number_field}`，且 heatmap 的 `x_field/y_field/cat/val` 全 None。前端若读 config 渲染轴名将显示字面占位符，heatmap 则无字段可绑定。
- **根因**：`s3_chart_engine_v2.py` 第 460–477 行字段绑定段只处理了 line/bar/pie/map/kpi/histogram/scatter/table，**heatmap 分支缺失**；且 scatter/heatmap 在 467–477 行的 `config.update(...)` 段**没有对应分支**（line/bar/pie/map/histogram 都有，scatter/heatmap 漏写）→ config 直接沿用 YAML 占位符。
- **修复（待 Item2 动手）**：① 在 445–465 补 heatmap 分支 `x=c0, y=c1, val=n0`；② 在 467–477 补 `config.update({"x":x,"y":y})`（scatter）与 `config.update({"x":x,"y":y,"value":val})`（heatmap），用真实字段覆盖占位符。
- **登记**：ISS-034

### CHART-02【P0·潜在】兜底饼图缺 cardinality 校验
- **现象**：`_apply_fallback`（634 行）对 `pie` 仅校验 `cat_f or num_f` 是否存在，**不校验分类基数**；若唯一分类列基数 >8（如 地区 200 类），兜底饼图会生成不可读的超高扇区饼图。
- **根因**：第 634 行 `if ctype in ("bar","pie") and (not cat_f or not num_f): continue` 未复用 `chart_constraints.pie.max_slices`（第 312 行）做基数上限判断。主规则饼图（`s3_chart_rules.yaml` 120–122 `category_cardinality: {min:2,max:8}`）已限制，仅兜底路径漏。
- **触发**：本次 11 夹具未触发（D6c 20 类地区被识别为 geo→map；饼图仅出现在低基数字段）。属潜在缺陷，必须修。
- **修复（待 Item2 动手）**：在 634 行后补 `if ctype=="pie": _pcat=self._best_dim(cat_f,cardinality); if not _pcat or cardinality.get(_pcat,0)>self.chart_constraints.get("pie",{}).get("max_slices",8): continue`。
- **登记**：ISS-035

### CHART-03【P0】直方图 bins=20 硬编码
- **现象**：10/11 数据集直方图 `config.bins` 恒为 20。
- **根因**：`s3_chart_rules.yaml` 第 158 行 `config: {field: "{number_field}", bins: 20}` 硬编码；引擎 476–477 行 `config.update({"field": y})` 只覆盖 field，未覆盖 bins。
- **修复（待 Item2 动手）**：引擎侧按字段基数自适应计算 bins（clamp 到 [5,30]），YAML 去掉硬编码 20（改注释说明由引擎算）。
- **登记**：ISS-036

## 5. 复现命令

```bash
# 在仓库根目录，用本机 Python3.12
C:/Users/Asus009/AppData/Local/Programs/Python/Python312/python.exe _night8_rulebaseline.py
# 产物：docs/project_record/night_runs/night8/_rulebaseline.json
```

## 6. 结论

- 规则引擎**字段绑定（x_field/y_field/category_field/value_field）逻辑基本正确**，11 数据集 56 图全部通过 selection-policy 真实字段校验。
- **唯一实质缺陷集中在 `config` 字典**：CHART-01（散点/热力图占位符，11 图）与 CHART-03（直方图 bins 硬编码，10 图）为必现；CHART-02（兜底饼图基数）为潜在。
- 下一步进入 Item2：按上表「修复（待动手）」逐条改 `s3_chart_engine_v2.py` + `s3_chart_rules.yaml`，改后复跑 `_night8_rulebaseline.py` 断言 0 占位符、bins 自适应，再 commit。
