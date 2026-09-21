# 1.1 附录 A/B 表格去 scroll.x — 证据

## 根因（来自 LOCAL_TEST_FAILURES.md 查 2）
提交 `aa716cd` 仅删了 C 表（指标）的 `scroll.x`；A 表（`AppendixPanel.tsx:112`）仍带
`scroll={{ x: 'max-content', y: 360 }}`，B 表（`:122`）仍带 `scroll={{ x: 'max-content' }}`。
`scroll.x='max-content'` 把表格宽度锁成内容自然宽、不撑满容器 → 右留白、整体挤左。

## 改动
- `AppendixPanel.tsx:112`（附录 A）：`scroll={{ x: 'max-content', y: 360 }}` → `scroll={{ y: 360 }}`
- `AppendixPanel.tsx:122`（附录 B）：`scroll={{ x: 'max-content' }}` → `scroll={{ y: 360 }}`
去掉横向锁宽后，表格随容器宽度自适应撑满；保留 `y:360` 纵向滚动防止长表撑破页面。

## 实测
- `tsc --noEmit` EXIT=0（见 `ev_11_tsc.out`）。
- ⚠️ 沙箱无浏览器，无法自动截图；需用户本机 `npm run build && npm start` 后开看板附录页
  确认 A/B 表已撑满、右侧无留白。代码层面根因已消除（唯一锁宽属性已移除）。

## 完成标准核对
- UI 改动：diff + tsc(EXIT=0) ✅；视觉截图需用户本机确认（已在对话如实标注，未用"应该生效"）。
