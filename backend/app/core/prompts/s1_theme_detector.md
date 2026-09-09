# S1 主题识别（LLM兜底）提示词（被控版）

你是一位数据分析师。请分析以下数据集的主题：

## 数据集名称
{dataset_name}

## 字段列表
{fields}
字段数量: {field_count}
{sample_str}

## 可识别的主题（从下列主题中选最匹配的一个，或提出新的主题）
{theme_domains}

## 输出要求
请以JSON格式返回：
```json
{
    "theme_tag": "主题标签",
    "confidence": 0.95,
    "reason": "识别理由"
}
```

只输出JSON，不要多余文字。