# 问题4 · 附录表格右侧留白（P2）

## 根因（诊断已确认）
`frontend/src/components/appendix/AppendixPanel.tsx` 的 A/B/C 三张附录表均设 `scroll={{ x: 'max-content' }}`。
AntD 在设 `scroll.x` 时切 `table-layout: fixed` 并按内容定宽、不拉伸到容器 100%：
- A（字段字典，列少内容窄 ≈560px）、C（指标计算明细 ≈780px）均 < 容器 900~1400px → 右侧留白；
- B（清洗与质检）因列多 + "说明"列长文本恰好 ≥ 容器而偶然撑满（非特殊配置）。

## 修复（本次改动，仅 1 个文件）
`AppendixPanel.tsx` 三表去掉 `scroll.x`（保留 A 的纵向 `y`）：
- A：`scroll={{ x: 'max-content', y: 360 }}` → `scroll={{ y: 360 }}`（保留纵向滚动）
- B：`scroll={{ x: 'max-content' }}` → 删除 `scroll` 属性（弹性列自动吸满 100%）
- C：`scroll={{ x: 'max-content' }}` → 删除 `scroll` 属性

## 验证
- `tsc --noEmit`：`TSC_EXIT=0`（见 `p3p4_frontend_tsc.out`）✅
- ⚠️ **视觉截图门禁（手动，沙箱无浏览器无法自动截图）**：需在 dev 环境打开看板附录 Tab，确认：
  1. A 字段字典表撑满容器、无右留白（且纵向超 360px 仍可滚动）；
  2. C 指标计算明细表撑满、无右留白；
  3. B 清洗与质检表保持原样（仍撑满）；
  4. 贴出 A/C 与 B 的对比截图。
- 辅助：`visual_repro_p3p4.html` 含 A 表「修复前(留白)/修复后(撑满)」对比预览（非真机）。

## 改动文件
- `frontend/src/components/appendix/AppendixPanel.tsx`（3 处 scroll 配置）
