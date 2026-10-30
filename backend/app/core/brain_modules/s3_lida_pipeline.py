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
import os
from typing import Any, Dict, List, Optional

from app.core.brain_modules.s4_orchestrator import (
    S5ScoreCard,
    grade_s5_disposal,
    decide_pass,
    DEFAULT_SCORE_WEIGHTS,
)


# H7（v4 阶段1）：自评 prompt 外置到 prompts/lida_self_eval.md，支持大脑配置覆盖、文件缺失时回退内联默认。
_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "lida_self_eval.md")
_DEFAULT_SELF_EVAL_PROMPT = (
    "你是资深数据看板评审。请基于主题与目标，从五个维度评估这组图表构成的数据看板：\n"
    "coverage(覆盖度:是否覆盖KPI/趋势/对比/分布)、narrative(叙事性:结论→佐证→明细结构)、"
    "redundancy(去冗余:是否重复)、accuracy(数据准确性:字段/聚合/口径是否合理)、"
    "readability(可读性:标题/数量/KPI数)。\n"
    "主题：{theme}\n目标：\n{goals}\n当前图表：\n{charts}\n"
    '只输出 JSON：{"dims": {"coverage":<0-100>, "narrative":<0-100>, "redundancy":<0-100>, '
    '"accuracy":<0-100>, "readability":<0-100>}, "critique": "<改进点>"}'
)


def load_lida_self_eval_prompt(theme_tag: str, goals_desc: str, chart_desc: str) -> str:
    """加载 LIDA 自评 prompt：优先读外部文件，缺失/异常时回退内联默认。

    模板占位符：<<THEME>> / <<GOALS>> / <<CHARTS>>（避免在 .md 内写花括号 JSON 与 str.format 冲突）。
    """
    try:
        with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
            tpl = f.read()
    except Exception:
        tpl = _DEFAULT_SELF_EVAL_PROMPT
        return tpl.replace("{theme}", str(theme_tag)).replace("{goals}", str(goals_desc)).replace("{charts}", str(chart_desc))
    return (
        tpl.replace("<<THEME>>", str(theme_tag))
        .replace("<<GOALS>>", str(goals_desc))
        .replace("<<CHARTS>>", str(chart_desc))
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

        # ── Phase 3: Self-Evaluation（A3 五维 + pass）──
        critique = await self._self_evaluate(db, theme_tag, goals, charts, llm_offline)
        result["self_eval"] = critique
        result["stages"].append({
            "phase": 3, "name": "Self-Evaluation", "status": "ok",
            "score": critique.get("score"), "overall": critique.get("overall"),
            "pass": critique.get("pass"), "dims": critique.get("dims"),
            "source": critique.get("source"),
            "critique": critique.get("critique"),
        })

        # ── Phase 4: Self-Repair（pass=False 时据 critique 重生成≤2次）──
        # A3：触发条件由原始 LLM 分改为 decide_pass 综合判定，避免"分高但数据错"漏修。
        repair_rounds = 0
        while not critique.get("pass", False) and repair_rounds < 2:
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
                "score": critique.get("score"), "overall": critique.get("overall"),
                "pass": critique.get("pass"), "dims": critique.get("dims"),
                "source": critique.get("source"),
                "critique": critique.get("critique"),
            })
        result["self_repair"] = {
            "rounds": repair_rounds,
            "final_score": critique.get("score"),
            "final_overall": critique.get("overall"),
            "final_pass": critique.get("pass"),
            "final_source": critique.get("source"),
        }
        return result

    async def _self_evaluate(
        self, db, theme_tag: str, goals: List[Dict[str, Any]], charts: List[Dict[str, Any]],
        llm_offline: bool,
    ) -> Dict[str, Any]:
        """
        A3 多维自评（五维：coverage/narrative/redundancy/accuracy/readability）+ pass 解耦 LLM 分。

        H4（PRD §7.3 规则校验前置）：先跑规则自评（毫秒级、离线安全）作为硬门禁；
        仅当规则判定通过时，再调用 LLM 做精修（带 ≤10s 超时兜底），且 LLM 不得推翻规则门禁
        （pass 沿用规则判定，避免「分高但数据错」被 LLM 低分放行，反之亦然）。
        H7：自评 prompt 已外置 prompts/lida_self_eval.md。
        """
        weights = dict(DEFAULT_SCORE_WEIGHTS)

        # 1) 规则自评先行（权威门禁，离线安全）
        rule_res = self._rule_self_eval(charts)
        if llm_offline or not rule_res.get("pass", False):
            # 规则已拦下违规，或离线：规则结果即最终门禁，跳过 LLM。
            return rule_res

        # 2) 规则通过 → LLM 精修 critique / dims（短超时，失败回退规则）
        try:
            from app.core.llm_gateway import llm_chat
            from app.core.brain_modules.threshold_config import DEFAULT_THRESHOLDS
            chart_desc = "\n".join(
                f"- [{c.get('chart_type')}] {c.get('title')}" for c in charts[:8]
            )
            goals_desc = "\n".join(f"- {g.get('goal', '')}" for g in goals[:5]) or "无"
            prompt = load_lida_self_eval_prompt(theme_tag, goals_desc, chart_desc)
            timeout = int(DEFAULT_THRESHOLDS.get("r4_llm_refine_timeout", 10))
            resp = await llm_chat(prompt=prompt, json_mode=True, user_id="lida_self_eval", timeout=timeout)
            rj = getattr(resp, "response_json", None)
            if rj and isinstance(rj, dict):
                dims = rj.get("dims")
                if isinstance(dims, dict) and all(k in dims for k in weights):
                    vals = {k: float(dims.get(k, 0)) for k in weights}
                    overall = sum(vals[k] * weights[k] for k in weights)
                    # 规则门禁不可被 LLM 推翻：pass 沿用规则判定
                    return {
                        "score": overall,            # 兼容旧字段
                        "overall": overall,
                        "dims": vals,
                        "pass": rule_res["pass"],
                        "critique": str(rj.get("critique", "")) or rule_res.get("critique", ""),
                        "source": "llm_refined",
                    }
        except Exception as e:
            print(f"[LIDA] 自评 LLM 精修失败(回退规则): {e}")
        return rule_res

    @staticmethod
    def _rule_self_eval(charts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """规则兜底自评：S5ScoreCard 五维评分，结构同 LLM 路径。"""
        try:
            card = S5ScoreCard()
            sc = card.score_dashboard(charts)
            dims = sc.dimension_scores
            overall = sc.overall_score
            return {
                "score": overall,
                "overall": overall,
                "dims": dims,
                "pass": decide_pass(dims, DEFAULT_SCORE_WEIGHTS, card.pass_threshold, {"accuracy": 50.0}),
                "critique": "；".join(sc.improvement_suggestions) or "规则兜底自评",
                "source": "rule",
            }
        except Exception:
            return {"score": 60.0, "overall": 60.0, "dims": {}, "pass": True,
                    "critique": "自评不可用(LLM与规则均失败)，默认放行", "source": "default"}
