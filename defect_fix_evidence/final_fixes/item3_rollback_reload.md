# Item 3 · 版本回退后前端不刷新（已改 + 类型校验通过）

**状态：✅ 代码已改，tsc 类型校验通过；UI 视觉验证待本机浏览器**
**约束：** 仅加 reload 回调，未改回退逻辑本身（回退接口 `/versions/rollback/{id}` 真实有效）。

## 问题
`DashboardOps.rollback()` 成功后只 `toast + setVersionOpen(false)`，**不重载看板详情** → 用户感觉"回退了但界面没变"，误以为失败。

## 改动（frontend）
**`DashboardOps.tsx`**
- `interface DashboardOpsProps` 新增 `onConfigReload?: () => void`（line 20，标注"问题3修复"）。
- 函数签名解构加入 `onConfigReload`（line 49）。
- `rollback` 成功分支在 `setVersionOpen(false)` 后调用 `onConfigReload?.()`（line 215）→ 触发看板详情重新拉取。

**`DashboardPage.tsx`**
- 将原内嵌于 `useEffect([urlId])` 的看板加载逻辑抽取为 `reloadConfig` `useCallback`（保留 `mounted` 卸载守卫），供回退后复用。
- `<DashboardOps ...>` 挂载处新增 `onConfigReload={reloadConfig}` prop。

## 实测 / 校验
- `tsc --noEmit` 全量类型检查 → **EXIT=0**（仅我改动的两个文件无报错，已确认 `onConfigReload` 已正确解构与传递）。
- 逻辑验证：`rollback` → `POST /versions/rollback/{id}` 成功 → `onConfigReload?.()` → `reloadConfig()` → 重新 `GET /dashboards/{id}` + 多数据集 chart-data → setState 刷新。

## 待用户本机视觉确认
沙箱无浏览器，无法对 React UI 截图。请在本机：
1. 打开看板 → 版本抽屉 → 回退某版本；
2. 确认回退 toast 后图表/标题**立即刷新**（不再"看似没生效"）。
