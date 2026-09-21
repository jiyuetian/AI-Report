# ev_17 — 1.7 暗色模式（C 范围：图表 + 仪表盘核心）

> 交付物：方案细化 + diff 摘要 + tsc + 视觉证据 + 断点更新
> 范围严格按用户拍板的 **C 方案**：仅做「图表 + 仪表盘核心」，不扩到全量。

## 一、C 范围边界（明确不做）

| 做 ✓ | 不做 ✗ |
|---|---|
| ① ECharts 图表明/暗两套配色（集中主题注入） | 表格（附录/数据表）暗色 |
| ② KPI 卡片背景 + 文字对比度 | 弹窗内部控件暗色（仅详情弹窗图表接了主题） |
| ③ 页面背景 + 导航栏 | 下拉/抽屉/Select 暗色 |
| 切换开关保留（右上角已有，Moon/Sun） | 附录面板暗色 |

设计原则（用户要求）：
- 用 AntD `ConfigProvider` + `theme.token` 语义变量（已有，本项不重复造）。
- ECharts **用 theme 切换**，不在各图表分支散落硬编码色值 → 新建 `chartThemeApply.ts` 集中注入。
- 暗色下文字对比度必须够 → KPI 暗色加了 `.kpi-title`/`.kpi-value` 提亮。

## 二、改动文件清单（4 文件）

### 1. `frontend/src/components/charts/chartThemeApply.ts`（新建）
主题令牌注入单一出口。导出 `themeChartOption(option, theme: 'light'|'dark')`：
- 调色板 `color`、背景 `backgroundColor`、全局 `textStyle.color` 取自 `CHART_THEMES`（与 `ThemeProvider.tsx` 同源，杜绝双份硬编码）。
- 覆盖 `title`/`legend`/`tooltip`/`xAxis`/`yAxis`/`angleAxis`/`radiusAxis`/`visualMap` 的文字色、轴色、分隔线色。
- tooltip 暗底用 `#1f1f1f`/边框 `#303030` 高对比。

### 2. `frontend/src/views/dashboard/DashboardPage.tsx`
- import 新增 `useChartTheme`（ThemeProvider）+ `themeChartOption`（chartThemeApply）。
- 组件体 `const { theme } = useChartTheme();`（第 ~303 行）。
- 主图（第 1157 行）：`option={sanitizeChartOption(themeChartOption(option, theme))}`。
- 详情弹窗图（第 1336 行）：`option={sanitizeChartOption(themeChartOption(generateChartOption(detailChart), theme))}`。

### 3. `frontend/src/components/charts/ChartRenderer.tsx`
- import 新增 `useChartTheme` + `themeChartOption`（第 22-23 行）。
- `LineChart`/`BarChart`/`PieChart`/`ScatterChart` 四子组件各加 `const { theme } = useChartTheme();`。
- 四处 `return <ReactECharts option={sanitizeChartOption(themeChartOption(option, theme))} ... />`。
  （对话页 line/bar/pie/scatter 走此处，随主题切换。）

### 4. `frontend/src/views/dashboard/DashboardPage.css`
- 新增暗色 KPI 对比度提亮（避免灰底看不清）：
  ```css
  [data-theme="dark"] .kpi-title { color: rgba(255, 255, 255, 0.65); }
  [data-theme="dark"] .kpi-value .ant-statistic-content { color: rgba(255, 255, 255, 0.88); }
  ```

## 三、diff 摘要（核心片段）

```diff
--- a/frontend/src/components/charts/ChartRenderer.tsx
+import { useChartTheme } from './ThemeProvider';
+import { themeChartOption } from './chartThemeApply';
 const LineChart = ... => {
+  const { theme } = useChartTheme();
   const option = { ... };
-  return <ReactECharts option={sanitizeChartOption(option)} ... />;
+  return <ReactECharts option={sanitizeChartOption(themeChartOption(option, theme))} ... />;
 };
 /* BarChart / PieChart / ScatterChart 同上 4 处 */
```

```diff
--- a/frontend/src/views/dashboard/DashboardPage.tsx
+import { useChartTheme } from '../../components/charts/ThemeProvider';
+import { themeChartOption } from '../../components/charts/chartThemeApply';
   const { theme } = useChartTheme();
   /* 主图 */
-  option={sanitizeChartOption(option)}
+  option={sanitizeChartOption(themeChartOption(option, theme))}
   /* 详情弹窗图 */
-  option={sanitizeChartOption(generateChartOption(detailChart))}
+  option={sanitizeChartOption(themeChartOption(generateChartOption(detailChart), theme))}
```

```diff
--- a/frontend/src/views/dashboard/DashboardPage.css
+[data-theme="dark"] .kpi-title { color: rgba(255, 255, 255, 0.65); }
+[data-theme="dark"] .kpi-value .ant-statistic-content { color: rgba(255, 255, 255, 0.88); }
```

## 四、tsc 校验
```
node node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json
TSC_EXIT=0   ✅ 通过
```
（注：本会话初核对发现前序 ChartRenderer 四图 return 与 DashboardPage 详情图未真正落盘「编辑未落地」残留，已全部补全并重跑 tsc 通过。）

## 五、视觉证据（沙箱无浏览器，替代方案）

沙箱环境无浏览器内核、playwright 装不上 → **无法自动 React DOM 像素截图**。提供两类证据：

1. **可交互预览页** `darkmode_preview.html`（仓库根）：与本仓库 frontend 同色令牌、同 `themeChartOption` 注入逻辑，CDN 加载 echarts，右上角切换开关。本机双击打开即得 **真实明暗截图**（含 KPI 区 + 图表区）。
2. **matplotlib 栅格化设计保真图**（非 React 像素，仅证配色/布局逻辑正确）：
   - `darkmode_light.png`（明）
   - `darkmode_dark.png`（暗，#1f1f1f 面板 + #ddd 文字 + #444 轴，对比度已提亮）
   - 生成脚本 `gen_darkmode_shot.py`
   - ⚠️ DejaVu Sans 无中文字形，图内中文标签显示缺字方框属正常，不影响配色/布局判定。

**真实交互截图需用户本机开 `darkmode_preview.html` 或 `npm run dev` 后点右上角切换。**

## 六、结论
- 1.7 按 C 范围完成：ECharts 图表主题切换（集中注入，无散落硬编码）、KPI 对比度、页面背景/导航（沿用既有 AntD darkAlgorithm + `[data-theme=dark]` CSS）。
- 切换开关保留可用。
- 未做项（表格/弹窗控件/下拉/抽屉/附录）按 C 范围明确排除，不在本项。
