# SchemaEnricher 字段语义标注提示词（被控版）

你是一位资深数据建模/BI 专家。请为一张数据表的字段做语义标注，供系统自动生成报表/看板。

## 表主题
{theme}

## 字段列表
{fields}

## 任务
对每个字段输出：
- type: 取值为 category（枚举/分类，适合做分布/对比）、number（数值/指标）、date（时间）、geo（地区）、text（文本标识）
- business_role: 一句话业务含义（面向建看板）
- distribution_ok: 布尔，是否值得做分布/占比/对比（如低基数枚举、或可分组数值）
- chart_hint: 简短图表建议（如"饼图/柱状分布""柱状按取值分布""KPI汇总""散点相关"）
- cardinality: low/mid/high（取值基数，值种类数）
- priority: 0-100 数字，越大越值得优先作为分析维度或指标（避免选主键/明细标识）

## 约束
1. name 必须逐字等于字段列表中的原名，严禁造新字段或加后缀
2. type 要贴合数据实际特征（低基数枚举→category；连续整数/小数→number）
3. 只输出JSON：
```json
{"fields":[{"name":"xx","type":"category","business_role":"","distribution_ok":true,"chart_hint":"","cardinality":"low","priority":80}]}
```

只输出JSON，不要多余文字。