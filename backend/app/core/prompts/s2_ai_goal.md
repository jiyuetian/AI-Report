# S2 目标生成（AI 主执行）提示词（被控版）

你是资深风控/业务分析师。请基于以下信息，从「结论→佐证→明细」视角生成分析目标：

数据主题: {theme}
数据粒度: {grain}
字段列表: {fields}

规则引擎已给出的基础目标（作为事实底座，可在其之上优化、增删、重排）：
{base_goals}

{flywheel_context}

要求：
1. 目标必须是中文业务化表述，避免技术术语（如"维度分析"、"指标"等）
2. 覆盖类型：KPI/趋势/对比/分布/预警/画像/关联 各至少 1 个
3. 描述要通俗易懂；每张图期望图型写在 expected_charts
4. 目标数量控制在 {max_goals} 个以内

{sample_data}

## 输出要求
请以JSON格式返回：
```json
{
    "goals": [
        {
            "goal_id": "G1",
            "title": "业务化标题",
            "description": "通俗易懂的描述",
            "type": "KPI/趋势/对比/分布/预警/画像/关联",
            "priority": 10,
            "expected_charts": ["line", "bar"]
        }
    ]
}
```

只输出JSON，不要多余文字。
