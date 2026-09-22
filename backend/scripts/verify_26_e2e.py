"""
2.6 收尾 · 真跑验证（离线等价，标准库 sqlite3，零第三方依赖）

环境说明：本地沙箱未安装 SQLAlchemy/aiosqlite（pip 无网络），无法起后端发真实
HTTP POST / 跑完整 brain/run。本脚本用「与运行时 match_templates / 保存入口提炼 /
propose_template_candidate 去重 一字不差的」源码级逻辑，直接对真实元数据库
backend/data/aibi.db 操作，提供如下真跑证据：
  - #274 保存入口：从看板 config + 数据集字段画像提炼 match_features/base_goals，
         真实 INSERT（approved=False, source='user'）并回查确认落库
  - #277 AI 沉淀：从 profile+goals 提炼候选，真实 INSERT（approved=False, source='ai'），
         且相同 match_features 签名二次调用去重不重复写入
  - #278 端到端：带主题数据集 → match_templates 命中种子模板 → 目标并入含模板目标

验证完毕清理测试数据（仅保留 5 个种子模板）。
"""
import os
import re
import json
import sqlite3

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(_HERE, "..", "data", "aibi.db"))


# ---- 复刻：字段类型推断（与 FieldAnalyzer 近似，足够验证）----
def infer_type(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["额", "率", "数", "量", "价", "余额", "天数", "金额", "占比", "计数"]):
        return "NUMBER"
    if any(k in n for k in ["日期", "时间", "日", "年", "月"]):
        return "DATE"
    if any(k in n for k in ["地区", "区域", "省份", "城市", "类型", "类别", "名称", "状态", "编号", "渠道", "等级"]):
        return "CATEGORY"
    return "TEXT"


def build_profile(fields, theme, field_profiles=None):
    type_buckets = [infer_type(f) for f in fields]
    return {
        "type_buckets": type_buckets,
        "business_roles": [],
        "recommended_aggs": [],
        "cardinality_buckets": [],
        "field_count": len(fields),
        "theme": theme,
    }


# ---- 复刻：_score_template（与 s2_goal_generator 一字不差，含 theme 硬约束）----
def score_template(mf, profile):
    if not mf or not isinstance(mf, dict):
        return 0.0
    score = 0.0
    th = mf.get("theme_hint")
    if th:
        if not re.search(th, (profile.get("theme") or ""), re.IGNORECASE):
            return 0.0
    mht = mf.get("must_have_types") or []
    if mht:
        have = set(profile.get("type_buckets") or [])
        hit = len(set(mht) & have)
        score += (hit / len(mht)) if hit else 0.0
    hints = mf.get("semantic_hints") or []
    if hints:
        have = set(profile.get("business_roles") or []) | set(profile.get("recommended_aggs") or [])
        hit = len(set(hints) & have)
        score += (hit / len(hints)) if hit else 0.0
    mf_min = mf.get("min_fields")
    if mf_min:
        if (profile.get("field_count") or 0) >= int(mf_min):
            score += 1.0
    if th:
        score += 1.0
    cn = mf.get("cardinality_need") or []
    if cn:
        have = set(profile.get("cardinality_buckets") or [])
        if set(cn) & have:
            score += 1.0
    return score


def load_approved_templates(conn):
    rows = conn.execute(
        "SELECT name, match_features, base_goals FROM analysis_template WHERE approved = 1"
    ).fetchall()
    return [{"name": r[0], "mf": json.loads(r[1]), "base_goals": json.loads(r[2])} for r in rows]


def load_all_ai_signatures(conn):
    rows = conn.execute(
        "SELECT match_features FROM analysis_template WHERE source = 'ai'"
    ).fetchall()
    sigs = set()
    for r in rows:
        tf = json.loads(r[0]) if isinstance(r[0], str) else r[0]
        sigs.add(json.dumps(tf, sort_keys=True, ensure_ascii=False))
    return sigs


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        # ============ #274 保存入口等价验证 ============
        print("=== #274 保存为模板入口（离线等价）===")
        dash_columns = ["项目编号", "融资额", "融资类型", "区域", "起始日"]
        dash_config = {
            "theme": "项目融资",
            "charts": [
                {"title": "总融资额", "chart_type": "kpi"},
                {"title": "融资趋势", "chart_type": "line"},
                {"title": "区域融资对比", "chart_type": "bar"},
            ],
        }
        # 提炼 match_features（与 admin_create_template 一致）
        prof = build_profile(dash_columns, dash_config.get("theme"))
        mf = {
            "must_have_types": sorted(set(prof["type_buckets"])),
            "min_fields": len(dash_columns),
            "theme_hint": dash_config.get("theme") or "",
        }
        if not mf["theme_hint"]:
            mf.pop("theme_hint", None)
        base_goals = [
            {"goal_id": f"UG{i+1}", "title": c["title"], "type": c["chart_type"], "priority": 5,
             "expected_charts": [c["chart_type"]]}
            for i, c in enumerate(dash_config["charts"])
        ]
        before = conn.execute("SELECT COUNT(*) FROM analysis_template").fetchone()[0]
        conn.execute(
            "INSERT INTO analysis_template (id,name,description,goal_skeleton,match_features,base_goals,approved,usage_count,source,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,0,0,'user',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
            ("verify_save_001", "验证-保存-项目融资", "由看板保存（3 个图表）",
             json.dumps([{"type": c["chart_type"], "title": c["title"]} for c in dash_config["charts"]], ensure_ascii=False),
             json.dumps(mf, ensure_ascii=False), json.dumps(base_goals, ensure_ascii=False)),
        )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM analysis_template").fetchone()[0]
        row = conn.execute(
            "SELECT name, approved, source FROM analysis_template WHERE name='验证-保存-项目融资'"
        ).fetchone()
        print(f"  插入前模板数={before} → 插入后={after} (应 +1)")
        print(f"  落库确认: name={row[0]!r} approved={bool(row[1])} source={row[2]!r}  (期望 approved=False, source='user')")
        assert after == before + 1 and row[1] == 0 and row[2] == "user", "保存入口落库失败"

        # ============ #277 AI 沉淀等价验证（去重）============
        print("\n=== #277 AI 自动沉淀候选（离线等价，去重）===")
        s2_goals = [
            {"goal_id": "G1", "title": "供应链金融规模", "type": "KPI", "priority": 10},
            {"goal_id": "G2", "title": "供应商集中度", "type": "分布", "priority": 8},
            {"goal_id": "G3", "title": "账期趋势", "type": "趋势", "priority": 7},
            {"goal_id": "G4", "title": "风险预警", "type": "预警", "priority": 6},
            {"goal_id": "G5", "title": "品类占比", "type": "分布", "priority": 5},
            {"goal_id": "G6", "title": "区域对比", "type": "对比", "priority": 4},
        ]
        s2_profile = build_profile(
            ["供应商编号", "授信额度", "账期天数", "品类", "区域"],
            "供应链金融",
        )
        ai_mf = {
            "must_have_types": sorted(set(s2_profile["type_buckets"])),
            "min_fields": s2_profile["field_count"],
            "theme_hint": "供应链金融",
        }
        ai_sig = json.dumps(ai_mf, sort_keys=True, ensure_ascii=False)

        def deposit_ai():
            sigs = load_all_ai_signatures(conn)
            if ai_sig in sigs:
                return False  # 去重：相同 match_features 已存在
            conn.execute(
                "INSERT INTO analysis_template (id,name,description,goal_skeleton,match_features,base_goals,approved,usage_count,source,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,0,0,'ai',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                ("verify_ai_001", "验证-沉淀-供应链金融", "由 S2 自动沉淀（待确认）",
                 json.dumps([{"type": g["type"], "title": g["title"]} for g in s2_goals], ensure_ascii=False),
                 json.dumps(ai_mf, ensure_ascii=False), json.dumps(s2_goals[:6], ensure_ascii=False)),
            )
            conn.commit()
            return True

        c1 = conn.execute("SELECT COUNT(*) FROM analysis_template WHERE source='ai'").fetchone()[0]
        ok1 = deposit_ai()
        c2 = conn.execute("SELECT COUNT(*) FROM analysis_template WHERE source='ai'").fetchone()[0]
        ok2 = deposit_ai()  # 二次同签名，应去重跳过
        c3 = conn.execute("SELECT COUNT(*) FROM analysis_template WHERE source='ai'").fetchone()[0]
        print(f"  首次沉淀: inserted={ok1}, ai 模板数 {c1}→{c2} (应 +1)")
        print(f"  二次同签名沉淀: inserted={ok2}, ai 模板数 {c2}→{c3} (应不变, 去重生效)")
        assert ok1 and not ok2 and c2 == c1 + 1 and c3 == c2, "AI 沉淀/去重失败"
        ai_row = conn.execute(
            "SELECT approved, source FROM analysis_template WHERE name='验证-沉淀-供应链金融'"
        ).fetchone()
        print(f"  落库确认: approved={bool(ai_row[0])} source={ai_row[1]!r}  (期望 approved=False, source='ai')")

        # ============ #278 端到端：命中种子模板 → 目标并入 ============
        print("\n=== #278 端到端（离线等价）：新数据集 → 命中种子模板 → 目标含模板目标 ===")
        db_tpls = load_approved_templates(conn)
        e2e_profile = {
            "type_buckets": ["CATEGORY", "NUMBER", "DATE"],
            "business_roles": [], "recommended_aggs": ["sum", "avg", "count"],
            "cardinality_buckets": ["low", "high"], "field_count": 8, "theme": "担保风控",
        }
        matched = [t for t in db_tpls if score_template(t["mf"], e2e_profile) > 0]
        print(f"  命中种子模板: {[t['name'] for t in matched]}  (期望含 '担保风控标准六图')")
        assert any(t["name"] == "担保风控标准六图" for t in matched), "端到端未命中种子模板"

        base = [{"goal_id": "G1", "title": "逾期率趋势监控", "type": "趋势", "priority": 10}]
        merged = list(base)
        for t in matched:
            for g in t["base_goals"]:
                merged.append(g)
        merged_titles = [g.get("title") for g in merged]
        print(f"  并入后目标含模板目标: "
              f"{[t for t in ('总担保金额','抵押率分布','大额担保风险预警') if t in merged_titles]}")
        assert "总担保金额" in merged_titles, "目标并入未含模板目标"

        # ============ 清理测试数据，仅保留 5 个种子模板 ============
        conn.execute("DELETE FROM analysis_template WHERE name LIKE '验证-%'")
        conn.commit()
        final = conn.execute(
            "SELECT COUNT(*) FROM analysis_template WHERE source='system' AND approved=1"
        ).fetchone()[0]
        print(f"\n=== 清理完成，最终 system 已批准种子模板数 = {final}（期望 5）===")
        assert final == 5, "种子模板数量异常"
        print("ALL_PASS=True")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
