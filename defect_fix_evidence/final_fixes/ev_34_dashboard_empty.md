# 证据 · 3.4 看板"无可绘制数据"整看板空态

> 任务性质：验证型 + 单文件小修（前端 `DashboardPage.tsx`）。
> 纪律：tsc + 本机验证清单 + 不许"应该生效了"。

## 一、修复前现状（已读代码核实，非推断）

| 层级 | 文件:行 | 现状 |
|---|---|---|
| 单图级空态 | `DashboardPage.tsx:1215` | 已存在：每张图无数据时 `<Empty description="该图表无可绘制数据，请调整字段或更换图表类型" />`，且 `chartEmptyReason`(L687) 给真实原因 |
| 整看板级空态 | `renderKPILayer` L1141 / `renderChartLayer` L1178 | **缺失**：无图时两函数都 `return null` → 用户只看到头部 `DashboardOps` + 一片空白，无"该看板无可绘制数据"的整体指引 |
| 配置未加载 | `DashboardPage.tsx:1301` | 已存在：`config` 为 null 时友好 Empty + 刷新/返回出口 |

**结论**：单图级已覆盖，整看板级是真空白——正是 3.4 要补的。

## 二、修复内容（`DashboardPage.tsx`）

1. 导入补 `Alert`（`antd` 导入行 L8）。
2. 在 `config` 已加载后、各图层之前插入**整看板空态守卫**（L1353 附近）：
   - `effectiveCharts.length === 0` → `<Card><Empty description="该看板暂无图表">` + 「上传数据重新生成」「查看其他看板」按钮（真·无图）
   - `!chartData`（主数据集取数失败/未加载）→ `<Alert type="warning">` 根因提示（数据集为空 / 已清理 / 数据路由未指向正确仓库），避免每张图各自报"无可绘制数据"造成困惑
   - 否则 `null`（正常渲染）

> 触发条件刻意用 `!chartData`（null）而非 `data.length===0`：多数据集看板主集可能 0 行但其他集有数据，用 null 才精准代表"数据源取数失败"这一真问题（也是路由错时的表现）。

## 三、验证

### 3.1 类型检查
```
cd frontend && node tsc --noEmit -p tsconfig.json
TSC_EXIT=0  （无错误输出）
```

### 3.2 路由修复后验证（关键事实纠正）
用户/断点文件原写"数据在 qa_aibi.db"。**实测开 duckdb 核对后命名写反**：
- `backend/data/duckdb/aibi.db`（67MB）= 真实 DuckDB 数据仓库：458 张表，全 `ds_*` 数据集表且每行有真实数据（抽样 ds_00e…=48 行、ds_019…=60 行…）
- `backend/data/qa_aibi.db`（757KB）= 元数据库：users/files/**dashboards=18**/brain_traces…

`config.py:62` + `.env:10` 的 `DUCKDB_PATH=./data/duckdb/aibi.db` **指向 67MB 真实数据文件 → 路由正确**，真实看板不会误报空态。
→ 已在本轮更新 `PROJECT_STATUS.md` 关键事实 #1/#2 为准确命名，避免下个会话误路由。

### 3.3 本机验证清单（沙箱无浏览器，需用户本机开 `http://127.0.0.1:8000/dashboard?id=xxx` 确认）
- [ ] 打开一个**正常有数据**的看板 → 图表正常渲染（不触发新空态/Alert）
- [ ] 构造 `config.charts=[]` 的看板（或临时清空某看板 charts）→ 显示「该看板暂无图表」+ 两个出口按钮
- [ ] 把 `DUCKDB_PATH` 临时指到一个不存在文件 → 刷新看板 → 显示黄色 Alert「数据集暂未加载到数据」（根因提示）
- [ ] 暗色模式下 Empty / Alert 可读（antd ConfigProvider 主题已覆盖）

## 四、影响范围 / 风险
- 仅新增守卫分支，不改动既有渲染逻辑；既有单图空态(L1215)保留。
- `effectiveCharts` 为空仅发生在"config.charts 空 且 无 auto 饼图"（auto 饼图仅在 chartData 有列时追加），即真·无图场景，不会误伤正常看板。
- 无新增依赖、无 API 变更。
