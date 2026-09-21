# 1.7 暗色模式 — 实施方案（待确认，未改动代码）

> 用户要求：先给方案，确认后再改。以下为方案，不含任何代码改动。

## 1) 现状：明暗切换怎么实现的？
- 当前前端**没有统一的明暗主题系统**。Ant Design 的 `theme` / `ConfigProvider` 未启用 darkAlgorithm。
- `frontend/src/theme.css` 仅有少量静态样式；各组件用 AntD 默认亮色 + 内联 `style` 写死颜色（如附录里 `background:'rgba(0,0,0,.03)'`、`color:'#1677ff'`）。
- 结论：**只有"看起来是亮色"的默认态，没有暗色开关，也没有真正的配色体系**。所以"暗色模式"本质上是"从零建一套主题"，不是翻个开关。

## 2) 涉及组件清单（逐个）
- 基础：在 `App.tsx`/`main.tsx` 包一层 `<ConfigProvider theme={{ algorithm: darkAlgorithm, token:{...} }}>`，并用 `ThemeContext` 存 light/dark 状态。
- 布局/壳：`DashboardPage.tsx`、`DashboardOps.tsx`(+`.css`)、`theme.css`。
- 附录：`AppendixPanel.tsx`（A/B/C 三表 + 内联灰色背景块）。
- 图表：`LoadingPage.tsx`（含 AI 失败弹窗 Modal）、ECharts 封装组件（`src/components/charts/*`）—— ECharts 需按 theme 切 `backgroundColor` 与各系列 `color`、`axisLine`/`splitLine` 颜色。
- 通用：所有 `Table`/`Modal`/`Drawer`/`Empty`/`Tag` 走 AntD 暗色算法即可自动适配；但**所有手写 `style` 里的硬编码色（黑底灰块、蓝链）需逐个替换为主题变量**。
- 弹窗/抽屉/下拉：AntD 暗色算法覆盖大部分；自定义内容（如附录的 `<pre>` 代码块背景）需改。

## 3) 两套配色设计原则（规则，不逐色调）
- 用 AntD `theme.token` 集中定义语义变量：`colorPrimary`、`colorBgBase`、`colorBgContainer`、`colorText`、边框 `colorBorder`、表头 `colorFillSecondary`。
- 浅色：AntD 默认；深色：`darkAlgorithm` + `colorBgBase:#141414`、`colorBgContainer:#1f1f1f`、`colorText:rgba(255,255,255,.85)`。
- ECharts：定义两套 `echartsTheme`（`bg`、`textStyle.color`、`axisLine`、`splitLine`、`seriesPalette` 6 色），按当前主题注入 `echarts.init(dom,{theme})` 或 `setOption(themeColors)`。
- 硬编码色改为 `var(--xxx)` 或读 `theme.token`；不允许散落 `#fff/#000/#1677ff`。
- 切换时把主题持久化到 `localStorage`，刷新保留。

## 4) 改动量 / 风险 / 工时
- 改动量：中~大。核心切换（ConfigProvider + ThemeContext）小；但**逐组件清硬编码色 + ECharts 双主题**是主工作量；约 15~25 个文件动到。
- 风险：ECharts 暗色若只改背景不改轴线/分割线，会出现"黑底白线看不见"；内联 style 漏改会留亮块。需逐页自测。
- 工时（路演前若做）：约 1~1.5 天（含自测）；若仅做"图表+仪表盘"核心、暂缓表格/弹窗细节，可压到 0.5 天但留瑕疵。

## 5) 路演是否必须演示暗色？
- **非必须**。当前 P0 路演清单里暗色不是验收项（原排第 1.7，属 Layer1 但非阻塞）。
- 建议：**降到 P2**，路演前不做；等路演后作为"体验增强"统一做（与 6.x 规范同批，避免临门一脚引入视觉回归）。
- 若你坚持路演演示暗色，请确认范围（全量 / 仅图表+仪表盘），我按确认范围实施。

---
请确认：A) 路演前不做（降 P2）；B) 路演前做全量；C) 路演前只做图表+仪表盘核心。确认后我再改。
