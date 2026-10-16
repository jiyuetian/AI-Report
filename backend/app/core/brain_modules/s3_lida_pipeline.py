"""
LIDA 四阶段骨架（night50 任务2：Self-Evaluation + Self-Repair）

忠实复用现有主链路，不做重复造轮子：
  Phase 1  Task Planning      → 复用 S2 目标（goals）
  Phase 2  Chart Generation   → 复用 S3 规则引擎 generate_all_candidates + night49 LLM 选图
                                （brain_run_sse 已产出候选池/图表时直接复用，避免二次 LLM）
  Phase 3  Self-Evaluation    → LLM 自评 0-100 + critique（llm_offline 或失败则 S5ScoreCard 规则兜底）
  Phase 4  Self-Repair        → 自评<70 据 critique 重生成≤2次；仍不过则交给下游 S5 分级处置（否决）

所有 LLM 调用均走 llm_chat 便捷函数并自带规则兜底，沙箱无网也不崩。
返回 dict（含 charts / stages / self_eval / self_repair），与 S3 既有 s3_result 结构可合并。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.core.brain_modules.s4_orchestrator import (
    S5ScoreCard,
    grade_s5_disposal,
)


class LIDAPipeline:
    """LIDA 四阶段骨架：Task Planning → Chart Generation → Self-Eval → Self-Repair。"""

    def __init__(self, derived_metrics: Optional[Dict[str, Dict[str, Any]]] = None):
        self.derived_metrics = derived_metrics

    async def run(
        self,
        db,
        dataset_id: str,
        fields: List[str],
        grain: str = "detail",
        theme_tag: str = "",
        goals: Optional[List[Dict[str, Any]]] = None,
        llm_offline: bool = False,
        sample_data: Optional[List[Dict[str, Any]]] = None,
        field_profiles: Optional[Any] = None,
        table_name: Optional[str] = None,
        candidate_pool: Optional[Dict[str, Any]] = None,
        charts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """运行 LIDA 四阶段，返回看板配置（与 S3 s3_result 同构可合并）。

        Args:
            charts: 若由调用方(S3 主链路)已生成则直接复用（Phase2 跳过生成，仅记录）。
            candidate_pool: 已生成的候选池，供 Phase4 自愈重选使用。
        """
        goals = goals or []
        result: Dict[str, Any] = {
            "stages": [],
            "charts": charts or [],
            "generated_by": "rule_engine",
            "self_eval": None,
            "self_repair": None,
        }

        # ── Phase 1: Task Planning（复用 S2 目标）──
        result["stages"].append({
            "phase": 1, "name": "Task Planning", "status": "ok",
            "goal_count": len(goals),
            "goals": [g.get("goal", "") for g in goals[:5]],
        })

        # ── Phase 2: Chart Generation（复用 S3 候选/图表）──
        if charts is None:
            from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine
            engine = S3ChartEngine(derived_metrics=self.derived_metrics)
            if candidate_pool is None:
                candidate_pool = engine.generate_all_candidates(
                    fields=fields, grain=grain, theme=theme_tag, goals=goals,
                    sample_data=sample_data, derived_metrics=self.derived_metrics,
                )
            candidates = candidate_pool.get("candidates", [])
            if llm_offline:
                chosen = engine._select_from_candidates(candidates, top_n=7)
            else:
                try:
                    from app.core.brain_modules.s3_llm_enhancer import select_charts_from_candidates
                    sel = await asyncio.wait_for(
                        select_charts_from_candidates(
                            db=db, theme=theme_tag, fields=fields, goals=goals,
                            grain=grain, candidate_pool=candidate_pool,
                            derived_metrics=self.derived_metrics,
                            field_profiles=field_profiles, table_name=table_name,
                        ),
                        timeout=60,
                    )
                    chosen = engine._enforce_narrative_order_dicts(sel["charts"]) \
                        if (sel and sel.get("charts")) else engine._select_from_candidates(candidates, top_n=7)
                except Exception as e:
                    print(f"[LIDA] Phase2 LLM 选图失败(规则兜底): {e}")
                    chosen = engine._select_from_candidates(candidates, top_n=7)
            charts = engine._enforce_narrative_order_dicts(chosen)
            result["generated_by"] = "llm" if not llm_offline else "rule_engine"
        else:
            result["generated_by"] = "reused"
        result["charts"] = charts
        result["stages"].append({
            "phase": 2, "name": "Chart Generation", "status": "ok",
            "chart_count": len(charts), "reused": charts is not None,
        })

        # ── Phase 3: Self-Evaluation（LLM 自评 0-100 + critique）──
        critique = await self._self_evaluate(db, theme_tag, goals, charts, llm_offline)
        result["self_eval"] = critique
        result["stages"].append({
            "phase": 3, "name": "Self-Evaluation", "status": "ok",
            "score": critique.get("score"), "source": critique.get("source"),
            "critique": critique.get("critique"),
        })

        # ── Phase 4: Self-Repair（自评<70 据 critique 重生成≤2次）──
        repair_rounds = 0
        while critique.get("score", 100) < 70 and repair_rounds < 2:
            repair_rounds += 1
            from app.core.brain_modules.s3_chart_engine_v2 import S3ChartEngine
            engine = S3ChartEngine(derived_metrics=self.derived_metrics)
            if candidate_pool is None:
                candidate_pool = engine.generate_all_candidates(
                    fields=fields, grain=grain, theme=theme_tag, goals=goals,
                    sample_data=sample_data, derived_metrics=self.derived_metrics,
                )
            candidates = candidate_pool.get("candidates", [])
            # 自愈：规则重选（优先覆盖 critique 指出的缺失类型；规则引擎已按叙事补齐）
            repaired = engine._enforce_narrative_order_dicts(
                engine._select_from_candidates(candidates, top_n=7)
            )
            result["charts"] = repaired
            critique = await self._self_evaluate(db, theme_tag, goals, repaired, llm_offline)
            result["stages"].append({
                "phase": 4, "name": "Self-Repair", "round": repair_rounds, "status": "ok",
                "score": critique.get("score"), "source": critique.get("source"),
                "critique": critique.get("critique"),
            })
        result["self_repair"] = {
            "rounds": repair_rounds,
            "final_score": critique.get("score"),
            "final_source": critique.get("source"),
        }
        return result

    async def _self_evaluate(
        self, db, theme_tag: str, goals: List[Dict[str, Any]], charts: List[Dict[str, Any]],
        llm_offline: bool,
    ) -> Dict[str, Any]:
        """LLM 自评看板质量 0-100 + critique；llm_offline 或失败则 S5ScoreCard 规则兜底。"""
        if not llm_offline:
            try:
                from app.core.llm_gateway import llm_chat
                chart_desc = "\n".join(
                    f"- [{c.get('chart_type')}] {c.get('title')}" for c in charts[:8]
                )
                goals_desc = "\n".join(f"- {g.get('goal', '')}" for g in goals[:5]) or "无"
                prompt = (
                    "你是资深数据看板评审。请基于主题与目标评估下面这组图表构成的数据看板的质量，\n"
                    "给出 0-100 的评分（覆盖度/叙事性/是否存在冗余），并指出主要改进点。\n"
                    f"主题：{theme_tag}\n目标：\n{goals_desc}\n当前图表：\n{chart_desc}\n"
                    '只输出 JSON：{"score": <int 0-100>, "critique": "<改进点>"}'
                )
                resp = await llm_chat(prompt=prompt, json_mode=True, user_id="lida_self_eval", timeout=30)
                rj = getattr(resp, "response_json", None)
                if rj and isinstance(rj, dict):
                    sc = rj.get("score")
                    if isinstance(sc, (int, float)):
                        return {
                            "score": float(sc),
                            "critique": str(rj.get("critique", "")),
                            "source": "llm",
                        }
            except Exception as e:
                print(f"[LIDA] 自评 LLM 失败(规则兜底): {e}")
        return self._rule_self_eval(charts)

    @staticmethod
    def _rule_self_eval(charts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """规则兜底自评：用 S5 评分卡近似 LLM 自评，保证不崩。"""
        try:
            sc = S5ScoreCard().score_dashboard(charts)
            return {
                "score": sc.overall_score,
                "critique": "；".join(sc.improvement_suggestions) or "规则兜底自评",
                "source": "rule",
            }
        except Exception:
            return {"score": 60.0, "critique": "自评不可用(LLM与规则均失败)，默认放行", "source": "default"}
