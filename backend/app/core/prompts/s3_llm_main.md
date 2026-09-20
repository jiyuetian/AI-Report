# S3 图表推荐 - LLM 主生成提示词（被控版）

你是一位数据可视化专家。请根据以下信息生成图表配置：

## 数据主题
{theme}

## 字段列表及类型（务必据此选择分析维度，不要逐客户堆明细）
{fields_desc}

## 业务场景维度建议
{dim_hint}

## 数据粒度
{grain_with_label}

## 分析目标
{goals}

## 约束条件
1. 生成5个图表配置
2. 图表类型必须是以下之一：kpi, line, bar, pie, scatter, table
3. 字段必须从上面的字段列表中选择
4. 标题简洁明了（不超过20字）
5. 贴合【业务场景维度建议】，5个图尽量覆盖不同分析维度，不要反复用同一对字段
6. 所有 x_field/y_field/category_field/value_field 必须是【字段列表及类型】中存在的【确切原始字段名】；严禁臆造不存在字段（如'年龄_分桶'、'status_flag'），连续数值字段直接引用原字段名即可
7. {grain_rule}

{error_section}

## 输出格式
必须是有效的JSON，格式如下：
{
  "charts": [
    {
      "chart_type": "line",
      "title": "担保金额趋势",
      "x_field": "日期",
      "y_field": "担保金额",
      "config": {},
      "reason": "趋势分析需要折线图"
    }
  ]
}

请只输出JSON，不要其他文字。