# ev_33 — 3.3 KPI 卡片单卡留白（复查 + 修复）

## 一、复查结论：旧修复"在代码里"，但**不完整**（这才是"没生效"的真因）

### 事实 1：aa716cd 的修复确实已落盘
`DashboardPage.tsx` 现存 `kpiSpan` 自适应逻辑（1→24 / 2→12 / 3→8 / ≥4→6），`<Col {...kpiSpan}>` 已生效，tsc 通过。**单卡(n=1)确实会占满整行**——代码层面没丢。

### 事实 2：但它只解决了"总数 ≤4"，≥5 时末行照样留白（真 bug）
旧逻辑按**总数**定列宽，不区分"是不是末行"：
- n=5 → 前 4 张各 1/4，第 5 张**仍是 1/4**，右侧空 18/24 格（75% 空白）← 这就是用户看到的"单卡留白"
- n=6 → 末行 2 张各 1/4，空 12/24 格
- n=7 → 末行 3 张各 1/4，空 6/24 格

而演示看板 KPI 常为 5~6 个 → **用户实际看到的一直是"末行单卡 + 大片空白"**，故体感"没修好"。

### 事实 3：KPI 判定与后端不一致（隐藏 bug，会导致计数偏小）
- 后端 `report_generator.py:333`：`chart_type=='kpi' or type=='kpi'`（两种写法都认，历史数据混用）
- 前端旧逻辑：`effectiveCharts.filter(c => c.chart_type === 'kpi')` —— **只认 chart_type**
- 后果：若某看板 KPI 用 `type` 字段存储 → ① 不计入 KPI 层（**数量偏小 → 列宽按错的数量算**）② 漏进图表层被当普通图渲染（双重错误）

## 二、修复（单文件：`DashboardPage.tsx`）

### 1. 归一化 KPI 判定（对齐后端）
```diff
+ function isKpiChart(c: any): boolean {
+   return c?.chart_type === 'kpi' || c?.type === 'kpi';
+ }
- const kpiCharts = effectiveCharts.filter((c: any) => c.chart_type === 'kpi');
+ const kpiCharts = effectiveCharts.filter(isKpiChart);
  // 图表层同步（避免 type='kpi' 漏进图表层）
- const nonKpiCharts = effectiveCharts.filter(c => c.chart_type !== 'kpi' && c.chart_type !== 'table');
+ const nonKpiCharts = effectiveCharts.filter(c => !isKpiChart(c) && c.chart_type !== 'table');
```

### 2. 按「所在行卡片数」算列宽，末行均分整行
```diff
+ function kpiSpanFor(index: number, total: number) {
+   const spanFor = (perRow: number) => {
+     const full = Math.floor(total / perRow) * perRow;      // 满行卡片数
+     const inRow = index < full ? perRow : ((total % perRow) || perRow);
+     return Math.round(24 / inRow);
+   };
+   return { xs: 24, sm: spanFor(2), lg: spanFor(4) };       // lg 最多 4 张/行
+ }
- const kpiSpan = kpiCount >= 4 ? {...} : ...;               // 旧：只看总数
+ const kpiSpan = kpiSpanFor(index, kpiCount);               // 新：按所在行
```

## 三、实测（`kpi_span_test.js`，node 直跑）

| n | 旧(lg) | 新(lg) | 末行空白格数（旧→新） |
|---|---|---|---|
| 1 | 24 | 24 | 0 → 0 |
| 2 | 12,12 | 12,12 | 0 → 0 |
| 3 | 8,8,8 | 8,8,8 | 0 → 0 |
| 4 | 6,6,6,6 | 6,6,6,6 | 0 → 0 |
| **5** | 6,6,6,6,**6** | 6,6,6,6,**24** | **18 → 0** |
| **6** | 6,… ,**6,6** | 6,… ,**12,12** | **12 → 0** |
| **7** | 6,… ,**6,6,6** | 6,… ,**8,8,8** | **6 → 0** |
| 8 | 6×8 | 6×8 | 0 → 0 |
| **9** | 6,… ,**6** | 6,… ,**24** | **18 → 0** |

```
[断言1] n=1 单卡占满整行: lg=24 PASS
[断言2] n=5 第5张不再留白: 旧=6 新=24 PASS
[断言3] n=6 末行2张均分: 12,12 PASS
[断言5] n=4 与旧逻辑一致(不改既有观感): 6,6,6,6 PASS
[断言6] sm 断点 n=3 末行占满: 12,12,24 PASS
末行仍有空白的 n 数量 = 0 => ALL PASS
```
- **tsc**：`--noEmit` → **EXIT=0**

## 四、边界覆盖
| 边界 | 处理 |
|---|---|
| n≤4 | 与旧逻辑**逐位一致**，既有看板观感零变化（断言5 证明） |
| n=0 | `kpiCharts.length===0` → return null（不变） |
| n≥5 | 末行均分，留白归零 |
| `type='kpi'` 历史数据 | 归一化后计入 KPI 层，且不再漏进图表层 |
| sm/xs 断点 | 同样按行均分（sm 每行 2、xs 每行 1），末行不留白 |
| 与 auto 补图冲突 | `effectiveCharts` 只补 `pie`，不影响 KPI 计数 |

## 五、本机验证清单（沙箱无浏览器，须本机做）
1. 打开含 **1 个 KPI** 的看板 → 卡片占满整行、右侧无空白
2. 打开含 **5 个 KPI** 的看板 → 第 5 张占满整行（修复前是 1/4 + 大片空白）——**这一条是本次修复的关键验收点**
3. 打开含 **6/7 个 KPI** 的看板 → 末行 2 张各半 / 3 张各 1/3
4. 打开含 4 个 KPI 的看板 → 仍是 4 张均分（确认无回退）
5. 缩窄到 <992px（sm）→ 末行同样不留白
6. 截图：n=5 场景修复前后对比（可用 `make_demo_db.py` 造数据）

## 六、风险
- **低**：纯列宽计算，未改 KPI 卡片结构与样式；n≤4 完全等价旧逻辑（有断言证明）。
- 唯一观感变化：n≥5 时末行卡片变宽（这正是修复目的）。
- 待拍板：若用户想要的是"单卡占满整行后**内部内容**横向铺开（避免卡内大片空白）"，那属**样式层改动**（需动 CSS / KPICard 结构）→ 按"涉多文件只给方案"纪律，本轮未做，记入待拍板。
