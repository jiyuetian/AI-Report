# -*- coding: utf-8 -*-
"""AI 调用预算与失败可见性的单一真相源（Task #702 · 2026-11-12）。

背景：此前三条链路各自硬编码预算，导致「看板生成 60s×3 且规则兜底吸收失败」
与「质检 12s 单发且失败显式暴露」表现完全不可比，绿标门槛也不一致。
本模块把预算、节点结果、链路汇总、绿标判定统一成一份契约：

- 预算：NODE_BUDGET（每节点 timeout / 轮训重试 / max_tokens）+ CHAIN_BUDGET_S（每条链路总闸），
  可用环境变量 AI_NODE_<NODE>_TIMEOUT 覆盖，禁止在业务文件里再写死数字。
- 结果：node_result() 统一产出 {by, llm_called, attempts, self_corrected, reason, latency_ms}。
- 汇总：chain_summary() 计算 ai_coverage 与 ai_governed（**每个节点都由 AI 把关**才算全链 AI 掌权）。
- 绿标：green_badge() 门槛从「任一节点 LLM 成功」改为「全链 AI 掌权且无规则接管」。
- 失败可见性：AI 全链失败必须显式 fallback_used=True + failure_reason，禁止伪装 done。

护栏定位（项目设计真意 · 权限矩阵 v2）：规则/流程是辅助 AI 的兜底，不是审批者。
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

# ── 每节点预算：三条链路共用 ────────────────────────────────────────────────
# timeout 为节点硬闸（asyncio.wait_for），retries 为网关内 provider 轮训重试，
# max_tokens 防止推理模型把 token 烧在 reasoning 上（见 11-12 质检事故根因）。
# 2026-11-13（#33）按真机实测重定：同一 understand prompt 三次真实网关调用
# 分别耗时 46.6s / 19.7s / 12.4s，旧 14s 硬闸导致首节点必超时、整链降级规则。
# 新值取实测 p90；调用时再由「链路剩余时间」夹紧，见 ai_governor._ai_node(deadline=...)。
NODE_BUDGET: Dict[str, Dict[str, int]] = {
    # 2026-11-13 二次校正（#33）：真机 /health/llm 探针 53827ms（首打 45s 超时
    # + 第二层约 9s 成功），故 understand 需 65s 才跑得完一次完整 failover；
    # 链总闸 170s + deadline/remaining() 夹紧保证不会五个节点各吃满 65s。
    "understand": {"timeout": 65, "retries": 0, "max_tokens": 600},
    # 2026-11-16（#40）：真机 run aigov_6f78f917 的 N2 plan 首层 45s 超时后直接
    # 「LLM超时(attempt 1)」整链降级；同轮 execute=37.6s / verify=38.4s 也全贴上限。
    # 根因：_ai_node 单次调用上限 45s，而旧 plan/execute/verify/revise 总预算 <= 单次上限，
    # 第二层 provider 拿到 0 秒 failover 余量，等于把「首打慢」直接判成「AI 不可用」。
    # 修法：每个治理节点总预算 = 45s 首打 + 15s failover；链总闸 170s 不变，
    # 各节点仍由 deadline/remaining() 夹紧，不会五节点各吃满 60s。
    "plan":       {"timeout": 60, "retries": 0, "max_tokens": 900},
    "execute":    {"timeout": 60, "retries": 0, "max_tokens": 600},
    "verify":     {"timeout": 60, "retries": 0, "max_tokens": 500},
    "revise":     {"timeout": 60, "retries": 0, "max_tokens": 900},
    "quality":    {"timeout": 20, "retries": 1, "max_tokens": 1600},
    "s3":         {"timeout": 60, "retries": 2, "max_tokens": 2400},
}

# ── 每条链路总闸（秒）────────────────────────────────────────────────────
CHAIN_BUDGET_S: Dict[str, int] = {
    "chat": 170,     # 对话改看板：前四节点硬闸 155s + 4×3s 收敛余量 = 167s；
                      # 170s < SSE 客户端 180s，且每个节点按 remaining() 夹紧
    "quality": 60,    # 2026-11-13：留出「首打两次超时 + provider failover」时间；
                      # 前端轮询上限由本值下发动态计算，不再写死 30s
    # 2026-11-16 #38：本值约束的是「AI 阶段累计可申请的等待时间」，不是整链墙钟上限。
    # 整链墙钟还包含 DuckDB 取数、字段画像、规则候选池、事实包构建、落库与网关排队，
    # 受网络抖动影响没有稳定上界。此前把 wall_elapsed > budget 直接当成
    # 「AI 预算耗尽 -> 规则接管 -> 熄灭绿标」，在真机 176.17s / 170s 上造成虚假降级
    # 并污染 ai_failure_reason。正确判据见 ChainClock.ai_starved：只有确实有 AI 阶段
    # 因剩余预算不足被 clamp 压缩、或被直接跳过时，才允许按预算降级。
    # 因此这里不再随实测耗时追着调大数字；与 chat 链对齐，brain/run 为后台任务
    # + /status 轮询（上限 330s），不受 SSE 客户端 180s 约束。
    "dashboard": 170,
}

# AI 自检发现疑问后允许回灌重做的最大轮数（「有疑问可以随时调整」）
MAX_SELF_CORRECTIONS = 2

# AI 全链不可用时是否允许规则兜底（必须为 True，但结果必须显式打标）
ALLOW_RULE_FALLBACK = True


def budget_for(node: str) -> Dict[str, int]:
    """取节点预算，支持环境变量覆盖；未知节点回落 quality 档。"""
    base = dict(NODE_BUDGET.get(node) or NODE_BUDGET["quality"])
    env_key = "AI_NODE_%s_TIMEOUT" % node.upper()
    try:
        v = os.getenv(env_key)
        if v:
            base["timeout"] = max(2, int(float(v)))
    except (TypeError, ValueError):
        pass
    return base


def chain_budget(chain: str) -> int:
    """取链路总闸，支持 AI_CHAIN_<CHAIN>_BUDGET_S 覆盖。"""
    base = CHAIN_BUDGET_S.get(chain, 75)
    try:
        v = os.getenv("AI_CHAIN_%s_BUDGET_S" % chain.upper())
        if v:
            base = max(5, int(float(v)))
    except (TypeError, ValueError):
        pass
    return base


def node_result(
    node: str,
    *,
    by: str = "ai",
    llm_called: bool = True,
    attempts: int = 1,
    self_corrected: bool = False,
    reason: Optional[str] = None,
    latency_ms: int = 0,
    fallback_used: bool = False,
) -> Dict[str, Any]:
    """统一节点结果契约。by 只有 ai / rule_fallback 两种取值。"""
    return {
        "node": node,
        "by": "rule_fallback" if (fallback_used or by != "ai") else "ai",
        "llm_called": bool(llm_called),
        "attempts": int(attempts),
        "self_corrected": bool(self_corrected),
        "reason": reason,
        "latency_ms": int(latency_ms),
        "budget": budget_for(node),
    }


def chain_summary(nodes: List[Dict[str, Any]], *, chain: str = "chat") -> Dict[str, Any]:
    """汇总链路：AI 覆盖率、是否全链 AI 掌权、规则是否接管、失败原因。

    绿标门槛：所有节点 by == 'ai' 且 llm_called == True，且没有规则接管。
    """
    clean = [n for n in (nodes or []) if isinstance(n, dict)]
    ai_nodes = [n for n in clean if n.get("by") == "ai" and n.get("llm_called")]
    rule_nodes = [n for n in clean if n.get("by") == "rule_fallback"]
    coverage = (len(ai_nodes) / len(clean)) if clean else 0.0
    governed = bool(clean) and len(ai_nodes) == len(clean) and not rule_nodes
    reasons = [n.get("reason") for n in rule_nodes if n.get("reason")]
    return {
        "chain": chain,
        "total_budget_s": chain_budget(chain),
        "node_count": len(clean),
        "ai_node_count": len(ai_nodes),
        "ai_coverage": round(coverage, 3),
        "ai_governed": governed,
        "by_node": {n.get("node", "?"): n.get("by") for n in clean},
        "self_corrected": any(n.get("self_corrected") for n in clean),
        "self_correction_rounds": sum(1 for n in clean if n.get("node") == "revise"),
        "fallback_used": bool(rule_nodes),
        "failure_reason": "; ".join(dict.fromkeys(reasons)) or None,
        "nodes": clean,
    }


def green_badge(summary: Dict[str, Any]) -> bool:
    """「AI 生成」绿标：全链 AI 把关 + AI 自检通过 + 无规则接管，三者缺一不可。"""
    return (
        bool(summary.get("ai_governed"))
        and not summary.get("fallback_used")
        and summary.get("verified", True) is not False
    )


def failed_result(chain: str, reason: str) -> Dict[str, Any]:
    """全链 AI 不可用时的诚实结果：绝不伪装成 done/成功。"""
    n = node_result(chain, by="rule_fallback", llm_called=False,
                    reason=reason, fallback_used=True)
    return chain_summary([n], chain=chain)


class ChainClock:
    """链路总闸时钟（Task #714）——真正包住整条流水线，而不是只写在字典里。

    - 覆盖所有 AI 阶段的累计耗时；交互等待（等用户点选）用 pause()/resume() 排除，
      不占用 AI 预算，也不破坏「暂停等用户」的生命周期。
    - clamp(timeout, stage) 给每个阶段的 asyncio.wait_for 做上限收敛：
      任何单个 AI 阶段都不能越过整链 deadline，预算耗尽后不再发起新的 AI 调用
      （wait_for 立即超时，交由既有规则兜底逻辑接管）。
    - #38 关键区分：exceeded() 只表示「整链墙钟超过预算」，是纯观测事实，
      不等于 AI 失败；ai_starved 才表示「确实有 AI 阶段因预算不足被压缩/跳过」，
      是唯一允许按预算降级的信号。绿标不得被墙钟抖动单独熄灭。
    - summary() 供 governance / 真机验证白盒取证
      （budget / wall_elapsed / paused / ai_starved / checkpoints）。
    """

    def __init__(self, chain: str = "dashboard") -> None:
        self.chain = chain
        self.budget_s = float(chain_budget(chain))
        self.t0 = time.monotonic()
        self._paused_at: Optional[float] = None
        self.paused_s = 0.0
        self.checkpoints: List[Dict[str, Any]] = []
        # #38：真正允许按预算降级的信号——确实有 AI 阶段被压缩/跳过
        self.ai_starved = False
        self.starved_stages: List[str] = []

    def elapsed(self) -> float:
        now = time.monotonic()
        extra_paused = (now - self._paused_at) if self._paused_at is not None else 0.0
        return max(0.0, now - self.t0 - self.paused_s - extra_paused)

    def pause(self) -> None:
        if self._paused_at is None:
            self._paused_at = time.monotonic()

    def resume(self) -> None:
        if self._paused_at is not None:
            self.paused_s += time.monotonic() - self._paused_at
            self._paused_at = None

    def remaining(self) -> float:
        return max(0.0, self.budget_s - self.elapsed())

    def exceeded(self) -> bool:
        return self.remaining() <= 0.05

    def mark_starved(self, stage: str, reason: str = "") -> None:
        """标记「确实有 AI 阶段因预算不足被压缩/跳过」——唯一允许按预算降级的信号。"""
        self.ai_starved = True
        tag = ("%s: %s" % (stage, reason)) if reason else stage
        if tag not in self.starved_stages:
            self.starved_stages.append(tag)

    def clamp(self, timeout: float, stage: str = "") -> float:
        r = self.remaining()
        requested = float(timeout)
        granted = max(0.2, min(requested, r))
        # 只有「预算已耗尽且本阶段申请时长被压掉」才是真饿死；
        # 墙钟超预算但本阶段足额拿到时间，不算 AI 降级。
        starved = bool(self.exceeded() and granted < requested)
        if starved:
            self.mark_starved(stage or "unknown",
                              "预算耗尽，wait_for 由 %.2fs 压到 %.2fs" % (requested, granted))
        if stage:
            self.checkpoints.append({
                "stage": stage, "requested_s": round(requested, 2),
                "granted_s": round(granted, 2),
                "remaining_s": round(r, 2), "exceeded": self.exceeded(),
                "ai_starved": starved,
            })
        return granted

    def summary(self) -> Dict[str, Any]:
        wall = self.elapsed()
        return {
            "chain": self.chain,
            "budget_s": round(self.budget_s, 2),
            "elapsed_s": round(wall, 2),
            "wall_elapsed_s": round(wall, 2),
            "remaining_s": round(self.remaining(), 2),
            "paused_s": round(self.paused_s, 2),
            # 墙钟超预算：仅观测，不触发降级
            "exceeded": self.exceeded(),
            # 真有 AI 阶段被压缩/跳过：唯一允许按预算降级的信号
            "ai_starved": self.ai_starved,
            "starved_stages": list(self.starved_stages),
            "checkpoints": self.checkpoints[-20:],
        }


class NodeTimer:
    """节点计时小工具，供各链路统一 latency_ms 口径。"""

    def __init__(self) -> None:
        self.t0 = time.perf_counter()

    @property
    def ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)
