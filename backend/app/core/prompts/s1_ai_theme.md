# S1 主题识别（AI 主执行）提示词（被控版）

你是一位资深数据分析师。请分析以下数据集的主题：

## 数据集名称
{dataset_name}

## 字段列表
{fields}
字段数量: {field_count}
{sample_str}

## 可识别的主题候选
{theme_domains}

## 规则词典参考
规则词典给出的参考主题（置信度 {dict_confidence}）：{dict_theme}
你可以沿用参考主题，也可以结合字段语义与样本数据提出更贴切的新主题。

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
