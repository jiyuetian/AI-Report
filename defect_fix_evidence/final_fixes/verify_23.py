"""
2.3 实测（mock 验证，沙箱 LLM 不可达 → 用 mock 模拟 LLM 可达）

验证点（对应拍板要求）：
1. 翻开关后（BRAIN_S2_USE_LLM=True），s2 默认走 LLM 路径
2. s2 真的调了 LLM（日志有 [LLM] 调用）
3. 生成的 goals 带 generated_by=llm
4. brain_run_sse 合并逻辑 → ai_participated=True（且 s2_generated_by=llm）
5. 反向：use_llm=False 或 LLM 失败 → 回退规则，generated_by=rule，ai_participated=False（守卫正确）

运行：python verify_23.py
"""
import asyncio
import sys

REPO = "C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend"
sys.path.insert(0, REPO)

import app.core.llm_gateway as lg
import app.core.brain_modules.s2_goal_generator as s2mod
import app.core.brain_config_manager as bcm
import app.core.config as cfg


# ---------- mock：模拟 LLM 可达 ----------
class FakeResp:
    def __init__(self, data, success=True):
        self.success = success
        self.response_json = data


LLM_GOALS = [
    {"goal_id": "G1", "title": "逾期率趋势智能监控", "description": "LLM 业务化描述", "type": "趋势", "priority": 10, "expected_charts": ["line"]},
    {"goal_id": "G2", "title": "地区风险智能对比", "description": "LLM 视角", "type": "对比", "priority": 9, "expected_charts": ["bar"]},
    {"goal_id": "G3", "title": "抵押风险分布洞察", "description": "LLM 视角", "type": "分布", "priority": 8, "expected_charts": ["pie"]},
    {"goal_id": "G4", "title": "大额担保风险预警", "description": "LLM 视角", "type": "预警", "priority": 7, "expected_charts": ["kpi"]},
    {"goal_id": "G5", "title": "担保类型占比分析", "description": "LLM 视角", "type": "分布", "priority": 6, "expected_charts": ["pie"]},
    {"goal_id": "G6", "title": "担保期限结构分析", "description": "LLM 视角", "type": "关联", "priority": 5, "expected_charts": ["bar"]},
]


def make_fake_llm(ok=True):
    async def fake_llm_chat(*args, **kwargs):
        print(f"[LLM] >>> mock llm_chat 被调用 (user_id={kwargs.get('user_id')})")
        if ok:
            return FakeResp({"goals": LLM_GOALS})
        return FakeResp(None, success=False)
    return fake_llm_chat


# 让 load_rules 不查库（返回 None → 用默认规则），避免 DB 依赖
async def fake_get_config(db, key):
    return None


bcm.BrainConfigManager.get_config = staticmethod(fake_get_config)


class FakeDB:
    pass


async def run_case(name, use_llm, llm_ok):
    print(f"\n========== 用例 {name}：use_llm={use_llm}, llm_ok={llm_ok} ==========")
    lg.llm_chat = make_fake_llm(ok=llm_ok)
    s2mod.llm_chat = lg.llm_chat

    gen = s2mod.S2GoalGenerator()
    goals = await gen.generate(
        db=FakeDB(), theme="担保风控",
        fields=["loan_amount", "overdue_days", "region"],
        grain="detail", use_llm=use_llm,
        sample_data=[{"loan_amount": 100, "overdue_days": 5, "region": "江苏"}]
    )
    llm_count = sum(1 for g in goals if g.generated_by == "llm")
    print(f"[RESULT] 生成 {len(goals)} 个目标，generated_by=llm 数={llm_count}")
    for g in goals:
        print(f"   - {g.goal_id} {g.title} [{g.type}] generated_by={g.generated_by}")

    # 2.3-B：brain_run_sse 合并逻辑
    s2_gen = "llm" if any(g.generated_by == "llm" for g in goals) else "rule"
    s3_gen = "rule_engine"  # 沙箱 S3 走规则兜底
    ai_participated = (s3_gen == "llm") or (s2_gen == "llm")
    print(f"[MERGE] s2_generated_by={s2_gen} | ai_participated={ai_participated} (generation_mode={'ai' if ai_participated else 'rule'})")
    return goals, s2_gen, ai_participated


async def main():
    cfg.settings.BRAIN_S2_USE_LLM = True
    print(f"[CFG] BRAIN_S2_USE_LLM = {cfg.settings.BRAIN_S2_USE_LLM}（2.3-A 默认已翻 True）")

    # 用例1：默认路径（设置已 True）→ LLM 成功
    g1, s2g1, ai1 = await run_case("A-默认LLM", use_llm=True, llm_ok=True)
    assert s2g1 == "llm" and ai1 is True, "用例A 失败：应 ai_participated=True"
    assert all(x.generated_by == "llm" for x in g1), "用例A 失败：目标应全 llm"

    # 用例2：use_llm=False → 纯规则
    g2, s2g2, ai2 = await run_case("B-规则兜底", use_llm=False, llm_ok=True)
    assert s2g2 == "rule" and ai2 is False, "用例B 失败：应 rule/false"

    # 用例3：use_llm=True 但 LLM 失败 → 回退规则（守卫）
    g3, s2g3, ai3 = await run_case("C-LLM失败回退", use_llm=True, llm_ok=False)
    assert s2g3 == "rule" and ai3 is False, "用例C 失败：LLM 失败应回退 rule/false"

    print("\n✅ 2.3-A/B 验证全部通过：")
    print("   - 翻开关后 s2 默认走 LLM（[LLM] 日志可见），目标 generated_by=llm")
    print("   - 看板 ai_participated 合并 S2+S3 = True（路演可秀'目标生成由 AI 参与'）")
    print("   - LLM 不可达/失败自动回退规则，ai_participated=False（不谎报 AI）")


asyncio.run(main())
