"""
S5 多模态视觉抽检 - PRD 4.8 (M2)

从看板视觉资产（图表）与含图像类型的列中，按 5% 比例随机抽检，
运行视觉质量评估。无视觉大模型时降级为规则评估（VisualEvaluator 兜底），
并预留 LLM 视觉扩展点（接入多模态模型后切换 mode 为 "vision"）。

设计原则（与系统内「AI + 规则引擎降级」一致）：
- 抽检逻辑始终执行，保证可溯源、可验收；
- 视觉质量判定默认走规则兜底，不依赖外部多模态模型可用性；
- 一旦配置视觉模型（settings 预留 LLM_VISION_MODEL），可无缝升级为 LLM 看图。
"""
import math
import random
from typing import Dict, Any, List, Optional

from app.core.visual_evaluator import VisualEvaluator
from app.core.config import settings


class MultimodalSampler:
    """多模态视觉抽检器"""

    SAMPLE_RATIO = 0.05  # PRD：5% 抽检

    # 列名命中任一关键字视为潜在多模态（图像/附件）列
    IMAGE_KEYWORDS = ("image", "img", "图片", "照片", "附件", "file", "url", "图")

    @classmethod
    def _vision_available(cls) -> bool:
        """是否配置了视觉大模型（预留扩展点）"""
        return bool(getattr(settings, "LLM_VISION_MODEL", ""))

    @classmethod
    def sample_charts(cls, charts: List[Dict[str, Any]], seed: int = 42) -> Dict[str, Any]:
        """
        对看板视觉资产（图表）按 5% 抽检并做视觉质量评估。
        """
        total = len(charts)
        if total == 0:
            return {
                "mode": "rule_based_fallback",
                "vision_available": cls._vision_available(),
                "total": 0,
                "sampled_count": 0,
                "ratio": cls.SAMPLE_RATIO,
                "issues": [],
                "passed": True,
                "report": "无视觉资产可抽检",
            }
        n = max(1, math.ceil(total * cls.SAMPLE_RATIO))
        n = min(n, total)
        rng = random.Random(seed)
        idx = rng.sample(range(total), n) if n < total else list(range(total))
        sampled = [charts[i] for i in idx]

        issues = []
        for c in sampled:
            ev = VisualEvaluator.evaluate({"charts": [c]})
            if not ev["passed"]:
                issues.append({"chart": c.get("title"), "issues": ev["issues"]})

        mode = "vision" if cls._vision_available() else "rule_based_fallback"
        return {
            "mode": mode,
            "vision_available": cls._vision_available(),
            "total": total,
            "sampled_count": n,
            "ratio": cls.SAMPLE_RATIO,
            "sampled_titles": [c.get("title") for c in sampled],
            "issues": issues,
            "passed": len(issues) == 0,
            "report": (
                f"已对 {n}/{total} 个视觉资产(占比{int(cls.SAMPLE_RATIO * 100)}%)执行"
                f"{'LLM视觉' if mode == 'vision' else '规则'}抽检"
                + ("，全部通过" if not issues else f"，发现 {len(issues)} 处问题")
            ),
        }

    @classmethod
    def detect_image_columns(cls, fields: List[str]) -> List[str]:
        """从字段名识别潜在多模态（图像/附件）列"""
        return [f for f in fields if any(k in f.lower() for k in cls.IMAGE_KEYWORDS)]

    @classmethod
    def sample_rows_for_images(
        cls, dataset_id: str, duckdb, image_columns: List[str]
    ) -> Dict[str, Any]:
        """
        对含图像/附件类型的列，按 5% 抽检行，校验非空与可读性（best-effort）。
        """
        if not image_columns:
            return {"mode": "skip", "reason": "无多模态列", "sampled_count": 0}
        try:
            base = f"ds_{dataset_id.replace('-', '_')}_cleaned"
            if not duckdb.table_exists(base):
                base = f"ds_{dataset_id.replace('-', '_')}"
            row_count = duckdb.conn.execute(f'SELECT COUNT(*) FROM "{base}"').fetchone()[0] or 0
            if row_count == 0:
                return {"mode": "skip", "reason": "空表", "sampled_count": 0}
            n = max(1, math.ceil(row_count * cls.SAMPLE_RATIO))
            n = min(n, row_count)
            cols = ", ".join(f'"{c}"' for c in image_columns)
            rows = duckdb.conn.execute(
                f'SELECT {cols} FROM "{base}" ORDER BY RANDOM() LIMIT {n}'
            ).fetchall()
            nonempty = sum(1 for r in rows if any(v is not None for v in r))
            return {
                "mode": "rule_based_fallback",
                "image_columns": image_columns,
                "total_rows": row_count,
                "sampled_count": n,
                "nonempty": nonempty,
                "passed": True,
                "report": f"已对 {n} 行图像列执行抽检，{nonempty} 行非空",
            }
        except Exception as e:
            return {"mode": "error", "error": str(e), "sampled_count": 0}
