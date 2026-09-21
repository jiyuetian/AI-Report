"""1.7 暗色模式视觉证据：用与 frontend 完全一致的配色令牌，真实栅格化明/暗两张图。
注意：这是设计保真渲染（matplotlib），非 React DOM 截图；真实交互截图请用 darkmode_preview.html 本机打开。
配色取自 App.tsx RISK_THEME_TOKENS / theme.css / chartThemeApply.ts 的 CHART_THEMES。"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

PALETTE = ['#5B8FF9','#5AD8A6','#F6BD16','#E86452','#6DC8EC','#945FB9','#FF9845','#1E9493']
PRIMARY = '#1677ff'

THEMES = {
    'light': dict(fig='#f5f7fa', card='#ffffff', border='#f0f0f0', text='#262626',
                  title='#666666', ctext='#333333', axis='#dddddd', split='#f0f0f0',
                  nav='#ffffffd9', navborder='#e8e8e8'),
    'dark':  dict(fig='#0e1016', card='#1f1f1f', border='#303030',
                  text='#ffffffe0', title='#ffffffa6',
                  ctext='#dddddd', axis='#444444', split='#333333',
                  nav='#141414d9', navborder='#303030'),
}

KPIS = [
    ('担保总额', '¥1.28亿', '+3.2% 环比', '#52c41a', False),
    ('在保笔数', '1,284', '+1.1% 环比', '#52c41a', False),
    ('逾期率', '4.6%', '+0.8% 环比', '#ff4d4f', True),
    ('平均抵押率', '58.3%', '-0.4% 环比', '#52c41a', False),
]
BAR = [('个人消费贷',512),('企业经营贷',368),('住房抵押贷',241),('助学担保',96),('农户贷',67)]
PIE = [('华东',486),('华北',312),('华南',268),('西南',124),('东北',94)]
MONTHS = ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06']
LINE = [95.2,94.8,93.9,94.1,93.4,95.4]

def draw(theme):
    t = THEMES[theme]
    fig = plt.figure(figsize=(12, 9), facecolor=t['fig'])
    gs = fig.add_gridspec(4, 4, height_ratios=[0.75, 1.15, 3, 2.1], hspace=0.32, wspace=0.22,
                          left=0.03, right=0.97, top=0.94, bottom=0.04)

    # ---- 顶部导航 ----
    axn = fig.add_subplot(gs[0, :]); axn.axis('off')
    axn.add_patch(plt.Rectangle((0,0),1,1, transform=axn.transAxes, facecolor=t['nav'],
                                edgecolor=t['navborder'], lw=1))
    axn.text(0.02, 0.5, 'AI', transform=axn.transAxes, fontsize=13, fontweight='bold',
             color='white', bbox=dict(boxstyle='round,pad=0.3', fc=PRIMARY, ec='none'), va='center')
    axn.text(0.09, 0.62, 'AI快速BI', transform=axn.transAxes, fontsize=11, fontweight='bold', color=t['text'], va='center')
    axn.text(0.09, 0.32, '报表工具', transform=axn.transAxes, fontsize=8, color=t['title'], va='center')
    for i,(lab,act) in enumerate([('数据上传',True),('我的看板',False),('管理后台',False)]):
        x=0.30+i*0.12
        axn.text(x,0.5,lab,transform=axn.transAxes,fontsize=10,color=PRIMARY if act else t['text'],
                 va='center', bbox=dict(boxstyle='round,pad=0.25', fc=PRIMARY if act else 'none',
                 ec='none', alpha=0.08) if act else None)

    # ---- KPI 行（4 列） ----
    for i,(name,val,chg,col,warn) in enumerate(KPIS):
        ax = fig.add_subplot(gs[1, i]); ax.axis('off')
        ax.add_patch(FancyBboxPatch((0.02,0.05),0.96,0.9, boxstyle='round,pad=0.01,rounding_size=0.04',
                     transform=ax.transAxes, facecolor=t['card'],
                     edgecolor='#ff4d4f' if warn else t['border'], lw=1.2))
        ax.text(0.08,0.72,name,transform=ax.transAxes,fontsize=11,color=t['title'],va='center')
        ax.text(0.08,0.42,val,transform=ax.transAxes,fontsize=18,fontweight='bold',color=t['text'],va='center')
        ax.text(0.08,0.16,chg,transform=ax.transAxes,fontsize=9,color=col,va='center')

    # ---- 柱状图 ----
    axb = fig.add_subplot(gs[2,0:2]); axb.set_facecolor(t['card'])
    names=[b[0] for b in BAR]; vals=[b[1] for b in BAR]
    axb.bar(names, vals, color=PALETTE[:len(vals)])
    axb.set_title('贷款类型分布', color=t['ctext'], fontsize=12, fontweight='bold')
    axb.tick_params(colors=t['ctext']); axb.spines['bottom'].set_color(t['axis']); axb.spines['left'].set_color(t['axis'])
    for s in ['top','right']: axb.spines[s].set_visible(False)
    axb.set_ylabel('笔数', color=t['ctext'])
    axb.tick_params(axis='x', labelrotation=15)
    axb.grid(axis='y', color=t['split'], alpha=0.6)

    # ---- 饼图 ----
    axp = fig.add_subplot(gs[2,2:4]); axp.set_facecolor(t['card'])
    pnames=[p[0] for p in PIE]; pvals=[p[1] for p in PIE]
    axp.pie(pvals, labels=pnames, colors=PALETTE, autopct='%1.0f%%',
            textprops=dict(color=t['ctext'], fontsize=9),
            wedgeprops=dict(edgecolor=t['card'], lw=1.5))
    axp.set_title('地区分布（按地区）', color=t['ctext'], fontsize=12, fontweight='bold')

    # ---- 折线图（整行） ----
    axl = fig.add_subplot(gs[3,:]); axl.set_facecolor(t['card'])
    axl.plot(MONTHS, LINE, color=PRIMARY, marker='o', lw=2, markersize=6)
    axl.fill_between(MONTHS, LINE, min(LINE)-2, color=PRIMARY, alpha=0.10)
    axl.set_title('合规率月度趋势', color=t['ctext'], fontsize=12, fontweight='bold')
    axl.tick_params(colors=t['ctext']); axl.spines['bottom'].set_color(t['axis']); axl.spines['left'].set_color(t['axis'])
    for s in ['top','right']: axl.spines[s].set_visible(False)
    axl.set_ylim(90,100); axl.set_ylabel('合规率(%)', color=t['ctext'])
    axl.grid(axis='y', color=t['split'], alpha=0.6)

    out = f'C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/defect_fix_evidence/final_fixes/darkmode_{theme}.png'
    fig.savefig(out, dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)
    print('saved', out)

for th in ('light','dark'):
    draw(th)
