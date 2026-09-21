# 问题3 · KPI 卡片右侧空白（P1）

## 根因（诊断已确认）
`frontend/src/views/dashboard/DashboardPage.tsx` 的 KPI 层 `<Col xs={24} sm={12} lg={6}>` 列宽写死：
桌面 `lg=6` 即固定占 1/4 宽度，与卡片数量解耦。当看板只有 1 张 KPI 时，卡片只占容器 25%，右侧 75% 固定空白。属 bug（非设计）。

## 修复（本次改动，仅 1 个文件）
`DashboardPage.tsx` `renderKPILayer`：
- 新增 `kpiCount = kpiCharts.length` 与自适应 `kpiSpan`：
  - `≥4` → `{xs:24,sm:12,lg:6}`
  - `3`  → `{xs:24,sm:12,lg:8}`
  - `2`  → `{xs:24,sm:12,lg:12}`
  - `1`  → `{xs:24,sm:24,lg:24}`（占满整行，消除空白）
- `<Col>` 由 `<Col {...kpiSpan} key=...>` 渲染（之前写死 `xs={24} sm={12} lg={6}`）。

## 验证
- `tsc --noEmit`：`TSC_EXIT=0`（见 `p3p4_frontend_tsc.out`）✅
- ⚠️ **视觉截图门禁（手动，沙箱无浏览器无法自动截图）**：需在 dev 环境加载测试看板 `risk_demo_v2_05_合规月度表看板`（或其任意含 KPI 的看板），确认：
  1. 单 KPI 时卡片占满整行、无右侧空白；
  2. 2/3/≥4 张时正常排布；
  3. 窄屏（<768px）与宽屏各一张截图。
- 辅助：打开 `visual_repro_p3p4.html` 可在任意浏览器预览等价布局行为（非真机，仅逻辑确认）。

## 改动文件
- `frontend/src/views/dashboard/DashboardPage.tsx`（+10 行，仅 KPI 层）
