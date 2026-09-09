/* AI-Report 验收报告图表 */
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // 各组通过情况
  var c1 = echarts.init(document.getElementById('chart-by-group'), null, { renderer: 'svg' });
  c1.setOption({
    animation: false,
    color: [accent, accent2],
    tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
    grid: { left: 40, right: 20, top: 30, bottom: 40 },
    xAxis: {
      type: 'value', name: '用例数', nameTextStyle: { color: muted },
      axisLine: { lineStyle: { color: rule } }, axisLabel: { color: muted },
      splitLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'category',
      data: ['UI 端到端', '内置压测', 'Golden 回归', '并发 P', '异常安全 S', '边界 B', '功能 F'],
      axisLine: { lineStyle: { color: rule } }, axisLabel: { color: ink }
    },
    legend: { bottom: 0, textStyle: { color: muted }, data: ['通过', '用例数'] },
    series: [
      { name: '通过', type: 'bar', barWidth: 14,
        data: [6, 3, 3, 3, 6, 7, 21],
        itemStyle: { color: accent, borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', color: accent, fontWeight: 600 } },
      { name: '用例数', type: 'bar', barWidth: 14,
        data: [6, 3, 3, 3, 6, 7, 21],
        itemStyle: { color: accent2 + '22' },
        label: { show: true, position: 'right', color: muted } }
    ]
  });
  window.addEventListener('resize', function() { c1.resize(); });

  // 总通过率环形图
  var c2 = echarts.init(document.getElementById('chart-donut'), null, { renderer: 'svg' });
  c2.setOption({
    animation: false,
    color: [accent, accent2 + '2e'],
    tooltip: { trigger: 'item', appendToBody: true },
    series: [{
      type: 'pie', radius: ['62%', '82%'], avoidLabelOverlap: false,
      label: { show: true, position: 'center', formatter: '100%\n通过 50 / 50', color: ink, fontWeight: 700, fontSize: 18, lineHeight: 24 },
      labelLine: { show: false },
      data: [ { value: 50, name: '通过' }, { value: 0, name: '未通过' } ]
    }]
  });
  window.addEventListener('resize', function() { c2.resize(); });

  // Golden 关键指标对比
  var c3 = echarts.init(document.getElementById('chart-golden'), null, { renderer: 'svg' });
  c3.setOption({
    animation: false,
    color: [accent, accent2],
    tooltip: { trigger: 'axis', appendToBody: true },
    legend: { bottom: 0, textStyle: { color: muted } },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ['质量达标率(≥80%)', '主题匹配率(≥80%)', '用例通过', '断言通过'],
      axisLine: { lineStyle: { color: rule } }, axisLabel: { color: ink },
      splitLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value', min: 0, max: 100, name: '%', nameTextStyle: { color: muted },
      axisLine: { lineStyle: { color: rule } }, axisLabel: { color: muted },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [
      { name: '实际值', type: 'bar', barWidth: 22, data: [90, 100, 100, 100],
        itemStyle: { color: accent, borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: 'top', color: accent, fontWeight: 600, formatter: '{c}%' } },
      { name: '目标值', type: 'line', data: [80, 80, 100, 100],
        lineStyle: { color: accent2, width: 2, type: 'dashed' },
        itemStyle: { color: accent2 }, symbolSize: 8 }
    ]
  });
  window.addEventListener('resize', function() { c3.resize(); });
})();