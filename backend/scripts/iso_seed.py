# -*- coding: utf-8 -*-
"""
隔离验证种子：向隔离 SQLite 写入 1 个测试用户 + 1 条 5 阶段运行记录（含每步 reasoning），
并 mint 与隔离后端同密钥的 JWT 写入 /tmp/iso_creds.json，供 Playwright 注入 localStorage。
不碰用户真实库/看板。
"""
import os
import sys
import asyncio
import json
import uuid
import time

# 必须在 import app 之前设好环境（与隔离后端完全一致）
ISO_DIR = "C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/backend/data"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{ISO_DIR}/iso_browser_test.db"
os.environ["DUCKDB_PATH"] = f"{ISO_DIR}/iso_browser_test.duckdb"
os.environ["REDIS_DISABLED"] = "1"
os.environ["DEBUG"] = "1"
os.environ["SECRET_KEY"] = "local-dev-secret-key"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import async_session_factory
from app.models.user import User
from app.models.brain import BrainTraceSummary, BrainTrace
from app.core.security import get_password_hash, create_access_token


REASONING = {
    "S1": {
        "step": "S1-主题识别", "input_summary": "用户上传《住房担保风控 V4.4 表结构.xlsx》，目标：生成担保业务总览看板",
        "ai_decision": "生成主题标签：担保风控总览", "ai_reason": "识别到表含 贷前/评分卡/贷中/贷后/垫付 等多模块，判定为综合风控主题，非单模块",
        "rules_applied": ["theme_classify_v1", "module_coverage_check"], "fallback_used": False,
        "output_ref": {"theme_tag": "担保风控总览", "charts_planned": 6},
    },
    "S2": {
        "step": "S2-目标拆解", "input_summary": "主题=担保风控总览，模块数=11",
        "ai_decision": "拆出 6 个看板目标（贷前准入/评分卡/贷中监控/贷后催收/垫付核销/通用指标）", "ai_reason": "按业务闭环顺序铺开，覆盖评分卡与贷后两个高风险模块",
        "rules_applied": ["goal_decompose_v2"], "fallback_used": False,
        "output_ref": {"goals": 6},
    },
    # S3 用 list：基础生成 + 契约自修（O10-3 自纠叙事）
    "S3": [
        {
            "step": "S3-AI图表生成", "input_summary": "6 目标 → 生成 6 张图表草稿",
            "ai_decision": "AI 原想：将'代偿率'用饼图展示占比", "ai_reason": "初判为构成占比类指标",
            "rules_applied": ["chart_type_heuristic"], "fallback_used": False,
            "output_ref": {"charts": 6},
        },
        {
            "step": "S3-AI契约自修", "input_summary": "契约校验发现'代偿率'为时序趋势指标，饼图误用",
            "ai_decision": "规则改成：代偿率→折线趋势图（AI 原想饼图被自修）", "ai_reason": "时序型比率指标须用折线/面积展示趋势，饼图违反图表语义契约",
            "rules_applied": ["contract_chart_semantics", "time_series_rule"], "fallback_used": False,
            "output_ref": {"repaired_chart": "代偿率趋势", "decision": "自修"},
        },
    ],
    "S4": {
        "step": "S4-洞察生成", "input_summary": "6 图表 + 评分卡模块",
        "ai_decision": "生成 3 条洞察：评分卡阈值漂移、贷后逾期抬头、垫付回收周期拉长", "ai_reason": "聚焦两个高风险模块 + 一项资金占用",
        "rules_applied": ["insight_priority_v1"], "fallback_used": False,
        "output_ref": {"insights": 3},
    },
    "S5": {
        "step": "S5-质检放行", "input_summary": "全链路输出进入评分卡",
        "ai_decision": "综合得分 88，判定放行（pass）", "ai_reason": "各阶段契约全过，无高危违规，自修项已闭环",
        "rules_applied": ["quality_gate_v1"], "fallback_used": False,
        "output_ref": {"score": 88, "passed": True},
    },
}


async def seed():
    async with async_session_factory() as s:
        # 用户（已存在则跳过，保证幂等）
        uid = str(uuid.uuid4())
        res = await s.execute(
            __import__("sqlalchemy").select(User).where(User.username == "iso_tester"))
        u = res.scalars().first()
        if not u:
            u = User(
                id=uid, username="iso_tester", email="iso_tester@example.com",
                hashed_password=get_password_hash("iso_pass_123"),
                full_name="隔离测试账号", is_active=True, is_superuser=False,
            )
            s.add(u)
            await s.commit()
            await s.refresh(u)
        uid = str(u.id)

        # 运行记录（已存在同 run_id 则复用）
        run_id = "iso-run-" + uuid.uuid4().hex[:8]
        summ = BrainTraceSummary(
            run_id=run_id, dataset_id=str(uuid.uuid4()), user_id=uid,
            overall_status="completed", s1_status="success", s2_status="success",
            s3_status="success", s4_status="success", s5_status="success",
            final_score=88, passed=1,
        )
        s.add(summ)
        for st in ["S1", "S2", "S3", "S4", "S5"]:
            s.add(BrainTrace(
                run_id=run_id, dataset_id=summ.dataset_id, user_id=uid,
                stage=st, stage_name=st, stage_status="success",
                stage_input={"echo": f"输入{st}"},
                stage_output={"result": f"{st} 产出OK", "score": 88 if st == "S5" else None},
                reasoning=REASONING[st],
            ))
        await s.commit()

        # mint token（与隔离后端同 SECRET_KEY）
        token = create_access_token(data={
            "sub": uid, "username": "iso_tester", "roles": ["user"], "is_superuser": False,
        })
        creds = {
            "token": token,
            "user": {
                "id": uid, "username": "iso_tester", "full_name": "隔离测试账号",
                "is_superuser": False, "roles": ["user"],
            },
            "run_id": run_id,
        }
        with open("/tmp/iso_creds.json", "w", encoding="utf-8") as f:
            json.dump(creds, f, ensure_ascii=False, indent=2)
        print("SEED_OK run_id=", run_id, "uid=", uid)
        print("CREDS_WRITTEN=/tmp/iso_creds.json")


if __name__ == "__main__":
    asyncio.run(seed())
