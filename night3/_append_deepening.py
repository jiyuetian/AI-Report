"""给 5 张任务卡追加「深度补充（Deepening Round 1）」小节。幂等：已追加则跳过。"""
import io
import os

BASE = 'night3/tasks'

SECTIONS = {
    'A_31_upload_layout.md': """
## 深度补充（Deepening Round 1）— 2026-09-21 23:44:40（commit fee2792）

【发现的缺口】首修只收缩了 Dragger，但「上传队列」Card 仍无条件渲染 N 行 List，
N=10 约 720px，首屏照样被占 → 用户要的"不占第一屏"只做了一半。

【补充】
- queueCollapsed = 有文件 && 无 uploading/error && 未手动展开
- 边界：有 uploading（要看进度条/取消）或 error（要点重试）时必须保持展开
- 收缩态一行 + 展开按钮；展开态右上角「收起」

【证据】test_31_queue_collapse.js 9 用例 ALL PASS（含 2 个关键反例）
【收益】N=10 首屏节省约 672px；N=20 节省约 1312px
【校验】tsc --noEmit EXIT=0

【耗时订正】首修 23:10:51 → 深补 23:44:40，跨度约 34 分钟（期间穿插其他项）
【达标】首修 ❌（<20 分钟）；含深度补充后 ✅
""",
    'D1_33_kpi_span.md': """
## 深度补充（Deepening Round 1）— 2026-09-21 23:48:15（commit 2f9e8de）

【发现的缺口】isKpiChart 大小写敏感且不认中文别名，与后端三处归一化不一致：
  action_executor.CHART_TYPE_MAPPING（KPI/KPI卡 → kpi）
  intent_classifier.py:568（kpi/KPI/指标卡/指标 → kpi）
  lineage_service.py:631（str(type).lower() == 'kpi'）
→ chart_type='KPI' 的卡片被漏出 KPI 层：列宽算错（留白复发）、被当普通图渲染、详情弹窗判定错。

【补充】
- 新增 normChartType()：chart_type||type → trim → lower → 中文别名表
- isKpiChart / isTableChart 统一走归一化
- 调用点全改：覆盖率统计 / 渲染 switch / 图表层过滤 / 详情弹窗，共 5 处

【证据】test_33_chart_type_norm.js 全通过。
  同一份混合数据实测：旧判定 KPI=2，新判定 KPI=5（漏 3 张）
【校验】tsc --noEmit EXIT=0

【耗时订正】首修 23:17:57 → 深补 23:48:15，跨度约 30 分钟
【达标】首修 ❌（<20 分钟）；含深度补充后 ✅

【遗留】kpiSpanFor 未指定 md/xl/xxl，AntD 向下继承 → md(768~992px) 沿用 sm 的 2 列，可能偏宽，未真机验证。
""",
    'D2_35_attribution.md': """
## 深度补充（Deepening Round 1）— 2026-09-21 23:40:30（commit 154255f）

【发现的缺口】真实 Excel 列名常带首尾/全角空格（" 抵押率 "），
旧实现 field_index.get(name) 精确匹配 → 一律判 missing（假阴性），AI 仍会误报"字段不存在"。

【补充】_norm（trim）/ _squash（去半角+全角空格）/ _lookup（精确→去空格→大小写不敏感）三级归一化

【自己引入的回归并修掉】把原名与去空格别名都塞进 field_index →
len(field_index) 重复计数，"已实查 N 个字段"虚高，样例字段可能吐出去空格后的怪名字。
→ 拆出 field_names 只存原名，专供计数/举例。

【证据】test_35_attribution.py 6 → 12 用例（新增：首尾空格/反向空格/全角/大小写/防假阳性/计数不污染）
  12/12 ALL PASS，旧话术"请先刷新看板页面"出现 0 次
【校验】py_compile 通过

【耗时订正】首修 23:24:20 → 深补 23:40:30，跨度约 16 分钟
【达标】首修 ❌（<20 分钟）；含深度补充后 ⚠️（跨度 16 分钟，仍偏短，但 12 用例覆盖到位）
""",
    'E1_36_admin_settings.md': """
## 深度补充（Deepening Round 1）— 2026-09-21 23:50:53（commit 3170f3b）

【发现的缺口（三个）】
① loading 与 unknown 同态：请求在飞却显示"健康检查未返回"，仍是失真
② 永不刷新：antd5 Tabs 不销毁非激活面板，useEffect([]) 只跑一次 → LLM 恢复可达后页面不自愈
③ 取值过严：typeof v==='boolean'，后端返回 0/1/"true"/"false" 时把"不可达"误报成"未知"

【补充】
- 四态：检测中 / 可达 / 不可达 / 未知，并展示检测时间
- 新增「重新检测」按钮（解决 Tabs 不重挂）
- 兼容布尔/数值/字符串三形态；无法判定仍归"未知"不谎报

【证据】test_36_health_state.js 全通过。
  实测旧逻辑对 6 种取值形态全部误报为"未知"（1/0/"true"/"false"/"1"/"0"）
【校验】tsc --noEmit EXIT=0

【耗时订正】首修 23:28:23 → 深补 23:50:53，跨度约 22 分钟
【达标】首修 ❌（<20 分钟）；含深度补充后 ✅

【遗留】/health 未做显式超时控制，接口挂起会一直停在"正在检测"（取决于 http 封装是否有默认超时）。
""",
    'E2_37_shell_audit.md': """
## 深度补充（Deepening Round 1）— 2026-09-21 23:56:30（commit 6d24556）

【发现的缺口】上一轮是人工审 DashboardOps.tsx 的 24 处 message.*，只有 1 个文件，
不可复跑、不可证明完备。

【补充】人工审计 → 机器资产：scan_37_fake_actions.py
  范围：全前端 36 文件 / 139 个 onClick 处理器
  v1 失败：取最内层花括号 → 几乎全误报
  v2 失败：缩进法取包围函数 → 命中的多是 .then 回调窄体
  v3 成功：按钮级判据（处理器体只有一句 message.* 且无 await/请求/setState）
  分级：R1 假动作 / R2 空壳可点 / R3 诚实标注
  自测：注入 5 个已知样本验证判定不反（无自测则"0 命中"与"扫描器坏了"不可区分）

【唯一 R1 命中并修掉】DashboardOps.tsx:472 删除按钮已 disabled，
但残留 onClick={() => message.success('已删除')} —— 死代码里的谎报，去掉 disabled 就复活。已删除。

【结果】R1=0、R2=0、R3=2（均为 disabled+Tooltip 诚实标注）；自测 PASS；tsc EXIT=0

【耗时订正】首修 23:32:31 → 深补 23:56:30，跨度约 24 分钟
【达标】首修 ❌（<20 分钟）；含深度补充后 ✅
""",
}


def main():
    for fn, sec in SECTIONS.items():
        p = os.path.join(BASE, fn)
        if not os.path.exists(p):
            print('[missing]', p)
            continue
        s = io.open(p, encoding='utf-8').read()
        if '深度补充（Deepening Round 1）' in s:
            print('[skip]', fn)
            continue
        if not s.endswith('\n'):
            s += '\n'
        s += sec
        io.open(p, 'w', encoding='utf-8').write(s)
        print('[ok]', fn, '→', len(s), 'chars')


if __name__ == '__main__':
    main()
