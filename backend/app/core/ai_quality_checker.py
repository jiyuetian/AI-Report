"""
AI 数据质量补充检测
使用LLM分析数据样本，发现规则无法覆盖的潜在问题

功能：
1. 数据分析：检查数据分布异常、语义异常、字段关联矛盾
2. 分级输出：影响进场的阻断，不影响进场的提示
3. 修复方案：AI针对每个问题生成修复选项
"""
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

from app.core.llm_gateway import get_llm_gateway, LLMRequest, LLMResponse


@dataclass
class AIQualityIssue:
    """AI发现的质检问题"""
    severity: str  # "blocking" 或 "warning"
    column: str
    message: str
    detail: str
    type: str = "ai"
    row_count: int = 0
    sample_values: List[str] = field(default_factory=list)
    rule: str = "AI数据质量检测"
    repair_options: List[Dict] = field(default_factory=list)


@dataclass
class AIQualityResult:
    """AI质检结果"""
    issues: List[AIQualityIssue]
    summary: Dict[str, Any]


class AIQualityChecker:
    """
    AI 数据质量补充检测器
    
    规则检测完成后，对数据样本进行AI分析，识别：
    - 数据分布异常（如数值字段存在极端离群值）
    - 语义异常（如字段值不符合业务语义）
    - 字段关联矛盾（如多个字段组合不符合业务规则）
    - 潜在的数据质量问题（如数据倾斜、编码混乱）
    """
    
    def __init__(self, duckdb_manager, table_name: str, columns: List[Dict], config: Optional[Dict] = None):
        self.db = duckdb_manager
        self.table_name = table_name
        self.columns = columns
        self.config = config or {}
    
    def _collect_sample_data(self, max_rows: int = 50) -> List[Dict]:
        """收集数据样本用于AI分析（统计信息用单次STRAIGHT聚合查询合并，避免逐列多次全表扫描）"""
        col_names = [c["name"] for c in self.columns[:10]]  # 最多取10列
        col_str = ', '.join([f'"{c}"' for c in col_names])

        # 获取样本数据（含空值，让AI也看到空值情况）
        rows = self.db.conn.execute(f"""
            SELECT {col_str} 
            FROM {self.table_name} 
            LIMIT {max_rows}
        """).fetchall()

        # 总行数（单次）
        total = self.db.conn.execute(f"SELECT COUNT(*) FROM {self.table_name}").fetchone()[0]

        # 单次聚合查询同时算所有字段的统计，避免每列4次全表扫描
        agg_exprs = []
        for c in self.columns[:10]:
            cname = c["name"]
            agg_exprs.append(f'COUNT("{cname}") AS "nonnull_{cname}"')
            agg_exprs.append(f'COUNT(DISTINCT "{cname}") AS "uniq_{cname}"')
            agg_exprs.append(
                f'SUM(CASE WHEN "{cname}" IS NULL OR CAST("{cname}" AS VARCHAR) = \'\' '
                f'THEN 1 ELSE 0 END) AS "null_{cname}"'
            )
        agg_sql = "SELECT " + ", ".join(agg_exprs) + f" FROM {self.table_name}"
        agg_row = self.db.conn.execute(agg_sql).fetchone()

        stats = {}
        for i, c in enumerate(self.columns[:10]):
            cname = c["name"]
            # 每列固定占3个位置：nonnull / uniq / null，按位置取值最稳（不依赖列名）
            non_null = int(agg_row[i * 3] or 0)
            unique = int(agg_row[i * 3 + 1] or 0)
            null_count = int(agg_row[i * 3 + 2] or 0)
            total = int(total or 0)

            # 取样例值（仅对非空值，DISTINCT 去重）
            samples = self.db.conn.execute(f"""
                SELECT DISTINCT CAST("{cname}" AS VARCHAR) 
                FROM {self.table_name} 
                WHERE "{cname}" IS NOT NULL 
                LIMIT 10
            """).fetchall()

            stats[cname] = {
                "type": c.get("type", "unknown"),
                "total_rows": total,
                "non_null": non_null,
                "null_count": null_count,
                "null_rate": round(null_count / total, 4) if total > 0 else 0,
                "unique_values": unique,
                "sample_values": [str(r[0]) for r in samples[:5]]
            }

        return {
            "columns": [{"name": c["name"], "type": c.get("type", "unknown")} for c in self.columns[:10]],
            "stats": stats,
            "sample_rows": [dict(zip(col_names, r)) for r in rows[:20]]
        }
    
    def _build_prompt(self, sample_data: Dict, existing_issues: List[Dict]) -> str:
        """构建AI分析提示词"""
        # 列描述
        col_desc = []
        for c in sample_data["columns"]:
            s = sample_data["stats"].get(c["name"], {})
            col_desc.append(
                f"- {c['name']} ({c['type']}): 非空{s.get('non_null', '?')}/{s.get('total_rows', '?')}行, "
                f"空值率{s.get('null_rate', 0)}, 唯一值{s.get('unique_values', '?')}个, "
                f"样例: {s.get('sample_values', [])}"
            )
        
        # 已有规则检测结果
        existing_desc = "无"
        if existing_issues:
            existing_desc = "\n".join([
                f"- [{i.get('severity', 'warning')}] {i.get('column', '?')}: {i.get('message', '?')}"
                for i in existing_issues[:10]
            ])
        
        prompt = f"""你是一个专业的数据质量分析师。请分析以下数据集，识别规则检测无法覆盖的潜在数据质量问题。

## 数据表结构
{chr(10).join(col_desc)}

## 数据样本（前20行）
```json
{json.dumps(sample_data['sample_rows'], ensure_ascii=False, default=str)[:3000]}
```

## 规则检测已发现的问题
{existing_desc}

## 分析要求
请从以下角度检测数据问题：
1. **数据分布异常**：数值字段是否存在极端离群值？数据分布是否合理？
2. **语义异常**：字段值是否存在不符合业务语义的情况？（如姓名中出现数字、金额字段出现负数等）
3. **字段关联矛盾**：字段组合是否存在不符合业务逻辑的情况？（规则检测未覆盖的）
4. **编码异常**：是否存在编码不一致、乱码、特殊字符等问题？
5. **数据完整性**：是否存在关键字段空值比例异常高的情况？
6. **其他潜在问题**：任何你发现的数据质量问题

## 输出要求
必须返回JSON格式，结构如下：
```json
{{
    "issues": [
        {{
            "column": "字段名",
            "severity": "blocking|warning",
            "message": "问题描述（一句话概括）",
            "detail": "详细说明问题影响和原因",
            "row_count": 受影响行数（估算，整数）,
            "sample_values": ["样例值1", "样例值2"],
            "repair_options": [
                {{"strategy": "策略ID", "label": "修复方案名称", "description": "方案说明"}}
            ]
        }}
    ]
}}
```

## 严重级别规则
- **blocking**: 严重影响后续分析且无法自动忽略的问题（如关键字段大面积异常、数据不可用等）
- **warning**: 不影响整体分析但建议关注的问题（如部分异常值、分布不均等）

## 修复方案要求
每个问题必须提供至少2个修复选项，供用户选择。"""
        
        return prompt
    
    async def analyze(self, existing_issues: Optional[List[Dict]] = None) -> AIQualityResult:
        """
        执行AI质检分析
        
        Args:
            existing_issues: 已有的规则检测结果（可选）
        
        Returns:
            AIQualityResult 包含AI发现的质检问题
        """
        # 1. 收集样本数据
        sample_data = self._collect_sample_data()
        
        # 2. 构建提示词
        prompt = self._build_prompt(sample_data, existing_issues or [])
        
        # 3. 调用LLM（AI质检使用较短超时，快速失败降级，避免拖慢整体质检流程）
        gateway = get_llm_gateway()
        request = LLMRequest(
            prompt=prompt,
            json_mode=True,
            max_tokens=3000,
            temperature=0.3,
            timeout=15.0  # AI质检对长prompt可能超时，短超时快速降级不影响规则检测结果
        )
        
        # 默认降级响应（LLM不可用时返回）
        fallback = {
            "issues": [],
            "note": "AI质检服务暂不可用，已跳过AI补充检测"
        }
        
        response: LLMResponse = await gateway.chat_complete(request, fallback)
        
        # 4. 解析结果
        issues = []
        if response.success and response.response_json:
            raw_issues = response.response_json.get("issues", [])
            for raw in raw_issues:
                try:
                    issue = AIQualityIssue(
                        severity=raw.get("severity", "warning"),
                        column=raw.get("column", "未知"),
                        message=raw.get("message", ""),
                        detail=raw.get("detail", ""),
                        row_count=raw.get("row_count", 0),
                        sample_values=raw.get("sample_values", []),
                        rule="AI数据质量检测",
                        repair_options=raw.get("repair_options", [])
                    )
                    issues.append(issue)
                except Exception as e:
                    print(f"[AI质检] 解析问题失败: {e}")
        
        # 5. 汇总
        blocking_count = sum(1 for i in issues if i.severity == "blocking")
        warning_count = len(issues) - blocking_count
        
        return AIQualityResult(
            issues=issues,
            summary={
                "total_issues": len(issues),
                "blocking_count": blocking_count,
                "warning_count": warning_count,
                "ai_analyzed": True,
                "llm_called": response.success and not response.fallback_used,
                "fallback_used": response.fallback_used
            }
        )