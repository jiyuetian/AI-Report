# Item 5 · 隐藏空壳按钮 / 占位项（已改 + 类型校验通过）

**状态：✅ 已改，tsc 类型校验通过；UI 视觉验证待本机浏览器**
**约束：** 仅在 UI 层标注"即将上线"/禁用，未删除任何业务功能代码。

## 问题
若干按钮点击后只弹 `message.info('（演示）')` 冒充功能，属于空壳：
- 版本抽屉：预览版本、对比（两个"演示"提示）
- 看板操作：二维码（"演示"）
- 对话列表：导出对话（"演示"）

## 改动（frontend/src/views/dashboard/DashboardOps.tsx）
| 位置 | 原行为 | 现行为 |
|---|---|---|
| `previewVersion` (line 207) | `message.info('预览版本…（演示）')` | `message.info('版本预览即将上线')` |
| `compare` (line 221) | `message.info('对比 …（演示）')` | `message.info('版本对比即将上线')` |
| 版本列表预览按钮 (line 281) | 可点 | `disabled` + Tooltip「预览（即将上线）」 |
| 版本列表对比按钮 (line 283) | 可点 | `disabled` + Tooltip「对比（即将上线）」 |
| 二维码按钮 (line 385) | 可点 `message.info('二维码（演示）')` | `disabled` + Tooltip「二维码（即将上线）」 |
| 导出对话 (line 455) | 可点 `message.info('导出对话（演示）')` | `disabled` + Tooltip「导出对话（即将上线）」 |

> 说明：删除按钮（对话列表）保留原 `message.success('已删除')` 提示（非本次范围，未动）。

## 校验
- `tsc --noEmit` → EXIT=0。
- 逻辑：空壳操作不再以"演示"假提示冒充功能，改为明确"即将上线"并禁用，符合"隐藏空壳"要求。

## 待用户本机视觉确认
沙箱无浏览器，请本机打开看板操作区/版本抽屉，确认上述按钮为禁用态且 tooltip 显示"即将上线"。
