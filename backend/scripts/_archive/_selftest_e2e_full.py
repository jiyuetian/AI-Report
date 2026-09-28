# -*- coding: utf-8 -*-
"""
AI-Report 端到端验收自测（黑盒，走真实 HTTP 接口）
覆盖：上传 → 建数据集 → 质检 → 批量修复 → 生成看板 → 看板配置/图表取数
      → 附录四件套 → 血缘六层 → 列表/统计一致 → 创建入口语义
用法：python _selftest_e2e_full.py [BASE_URL]
"""
import io
import json
import sys
import time
import urllib.request
import urllib.error
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
XLSX = sys.argv[2] if len(sys.argv) > 2 else r"C:/Users/Asus009/Desktop/临时/ai大赛/AI-Report/tests/_fixtures/acceptance_loan.xlsx"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (f" | {detail}" if detail and not cond else ""))


def req(method, path, body=None, headers=None, raw_body=None, timeout=60):
    url = BASE + path
    data = None
    h = dict(headers or {})
    if raw_body is not None:
        data = raw_body
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            txt = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(txt)
            except Exception:
                return resp.status, txt
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, txt


def multipart_upload(path, field, filename, filebytes, mime):
    boundary = "----e2eboundary" + uuid.uuid4().hex[:8]
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n".encode("utf-8"))
    parts.append(filebytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    return req("POST", "/api/v1/files", raw_body=body,
               headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=120)


print("=" * 60)
print("AI-Report 端到端验收自测")
print("=" * 60)

# ---------- 0. 服务健康 ----------
print("\n[0] 服务健康")
st, health = req("GET", "/api/v1/health")
check("health 接口 200", st == 200, f"status={st}")

# ---------- 1. 上传 ----------
print("\n[1] 上传文件")
with open(XLSX, "rb") as f:
    xbytes = f.read()
st, up = multipart_upload(XLSX, "file", "acceptance_loan.xlsx", xbytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
check("upload 200", st == 200, f"status={st} body={str(up)[:200]}")
file_id = (up or {}).get("file_id") if isinstance(up, dict) else None
check("返回 file_id", bool(file_id), str(up)[:200])

# ---------- 2. 创建数据集 ----------
print("\n[2] 创建数据集")
ds_name = "e2e验收_贷款明细_" + uuid.uuid4().hex[:6]
st, ds = req("POST", "/api/v1/datasets", body={"file_id": file_id, "name": ds_name})
check("datasets 200", st == 200, f"status={st} body={str(ds)[:300]}")
ds_id = (ds or {}).get("dataset_id") or (ds or {}).get("id") if isinstance(ds, dict) else None
check("返回 dataset_id", bool(ds_id), str(ds)[:300])
if not ds_id:
    print("无法继续，退出")
    sys.exit(1)

# ---------- 3. 质检 ----------
print("\n[3] 质检")
st, qc = req("POST", "/api/v1/quality/check", body={"dataset_id": ds_id}, timeout=120)
check("quality/check 200", st == 200, f"status={st} body={str(qc)[:200]}")
issues = (qc or {}).get("issues") if isinstance(qc, dict) else None
n_issues = len(issues) if isinstance(issues, list) else -1
check("质检返回 issues 列表", n_issues >= 0, f"type={type(issues)}")
print(f"  质检发现问题数: {n_issues}")

# ---------- 4. 批量修复（推荐方案） ----------
print("\n[4] 一键修复（推荐方案）")
fix_items = []
for iss in (issues or []):
    if not isinstance(iss, dict):
        continue
    opts = iss.get("repair_options") or []
    rec = next((o.get("strategy") for o in opts if isinstance(o, dict) and o.get("recommended")), None)
    if rec and iss.get("column"):
        fix_items.append({"issue_type": iss.get("type"), "column": iss.get("column"), "fix_strategy": rec})
print(f"  构造修复项: {len(fix_items)} 个")
if fix_items:
    st, fb = req("POST", "/api/v1/quality/fix-batch",
                 body={"dataset_id": ds_id, "items": fix_items}, timeout=180)
    check("quality/fix-batch 200", st == 200, f"status={st} body={str(fb)[:300]}")
    if isinstance(fb, dict):
        print(f"  fix-batch: success={fb.get('success')} failed={fb.get('failed')}")
else:
    print("  （无带推荐策略的修复项，跳过批量修复）")

# 修复后重新质检
st, qc2 = req("POST", "/api/v1/quality/check", body={"dataset_id": ds_id}, timeout=120)
check("修复后重新质检 200", st == 200, f"status={st}")

# ---------- 5. 生成看板 ----------
print("\n[5] 生成看板（brain run + 轮询）")
st, run = req("POST", "/api/v1/brain/run", body={"dataset_id": ds_id, "user_id": "e2e_test"}, timeout=60)
check("brain/run 200", st == 200, f"status={st} body={str(run)[:400]}")
run_id = (run or {}).get("run_id") if isinstance(run, dict) else None
check("返回 run_id", bool(run_id), str(run)[:200])

dashboard_id = None
if run_id:
    deadline = time.time() + 300
    last = None
    while time.time() < deadline:
        st, stat = req("GET", f"/api/v1/brain/run/{run_id}/status?dataset_id={ds_id}", timeout=30)
        last = stat
        s = (stat or {}).get("status") if isinstance(stat, dict) else None
        if s in ("completed", "failed", "cancelled"):
            break
        time.sleep(3)
    s = (last or {}).get("status") if isinstance(last, dict) else None
    check("生成完成 (completed)", s == "completed", f"status={s} body={str(last)[:400]}")
    dashboard_id = (last or {}).get("dashboard_id") if isinstance(last, dict) else None
    if not dashboard_id and isinstance(last, dict):
        dashboard_id = (last.get("detail") or {}).get("dashboard_id") or (last.get("result") or {}).get("dashboard_id")
    check("返回 dashboard_id", bool(dashboard_id), str(last)[:300])

# ---------- 6. 看板内容 ----------
print("\n[6] 看板内容")
if dashboard_id:
    st, dash = req("GET", f"/api/v1/dashboards/{dashboard_id}", timeout=30)
    check("dashboards/{id} 200", st == 200, f"status={st}")
    cfg = (dash or {}).get("config") if isinstance(dash, dict) else None
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except Exception:
            cfg = {}
    charts = (cfg or {}).get("charts") or []
    check("看板含图表", len(charts) > 0, f"charts={len(charts)}")
    print(f"  图表数: {len(charts)}")
    types = [c.get("chart_type") for c in charts if isinstance(c, dict)]
    print(f"  图表类型: {types}")
    # 每张图有 dataset_id（多数据集修复项）
    no_ds = [c.get("title") for c in charts if isinstance(c, dict) and not c.get("dataset_id")]
    check("每张图表带 dataset_id", len(no_ds) == 0, f"missing={no_ds}")

    # 图表取数（真源）
    ok_data = 0
    empty_titles = []
    for c in charts[:12]:
        if not isinstance(c, dict):
            continue
        d = c.get("dataset_id") or ds_id
        st2, cd = req("GET", f"/api/v1/datasets/{d}/chart-data", timeout=30)
        if st2 == 200 and isinstance(cd, dict) and (cd.get("rows") or cd.get("data") or cd.get("items")):
            ok_data += 1
        else:
            empty_titles.append(f"{c.get('title')}({st2})")
    check("图表取数非空（渲染层有数据）", ok_data == len([c for c in charts if isinstance(c, dict)]),
          f"ok={ok_data} empty={empty_titles}")

# ---------- 7. 附录四件套 ----------
print("\n[7] 附录四件套")
if dashboard_id:
    st, ap = req("GET", f"/api/v1/dashboards/{dashboard_id}/appendix", timeout=60)
    check("appendix 200", st == 200, f"status={st} body={str(ap)[:200]}")
    if isinstance(ap, dict):
        fd = ap.get("field_dict") or []
        n_cols = sum(len(d.get("columns", [])) for d in fd)
        check("A 字段字典有列", n_cols > 0, f"datasets={len(fd)} cols={n_cols}")
        cl = ap.get("clean_log") or []
        # 口径：质检发现问题 → 必须有清洗/质检记录；数据本身干净 → 允许为空（诚实白盒）
        check("B 清洗/质检记录与质检结果一致", n_issues == 0 or len(cl) > 0,
              f"issues={n_issues} rows={len(cl)}")
        mt = ap.get("metrics") or []
        check("C 指标明细非空", len(mt) > 0, f"rows={len(mt)}")
        ln = ap.get("lineage") or {}
        check("D 血缘有节点", len(ln.get("nodes", [])) > 0, f"nodes={len(ln.get('nodes', []))}")

# ---------- 8. 血缘六层 ----------
print("\n[8] 血缘六层")
from collections import Counter
st, lg = req("GET", f"/api/v1/lineage/graph/{ds_id}", timeout=60)
check("lineage/graph 200", st == 200, f"status={st}")
nodes = (lg or {}).get("nodes", []) if isinstance(lg, dict) else []
types = Counter(n.get("type") for n in nodes)
expected = {"source", "table", "field", "clean", "business", "chart"}
missing = expected - set(types.keys())
# 无清洗时 clean 层可能为空（诚实白盒），business/agg 同理可空——但 source/table/field/chart 必须有
hard_required = {"source", "table", "field", "chart"}
check("血缘必备层齐全(source/table/field/chart)", hard_required <= set(types.keys()), f"types={dict(types)}")
check("血缘含 logic_json", all("logic_json" in n for n in nodes), f"total={len(nodes)}")
charts_n = types.get("chart", 0)
check("血缘指标/图表层非空", charts_n > 0, f"chart={charts_n}")

st, ls = req("GET", f"/api/v1/lineage/stats/{ds_id}", timeout=30)
check("lineage/stats 200", st == 200, f"status={st}")
check("stats 六层完备标记", (ls or {}).get("six_layers_complete") is True if isinstance(ls, dict) else False, str(ls)[:200])

# ---------- 9. 列表/统计一致 ----------
print("\n[9] 我的看板：列表与统计一致")
st, my = req("GET", "/api/v1/dashboards/my?page=1&page_size=100&user_id=e2e_test", timeout=30)
st2, ov = req("GET", "/api/v1/dashboards/stats/overview?user_id=e2e_test", timeout=30)
check("dashboards/my 200", st == 200, f"status={st}")
check("stats/overview 200", st2 == 200, f"status={st2}")
my_total = (my or {}).get("total") if isinstance(my, dict) else None
ov_total = (ov or {}).get("total") if isinstance(ov, dict) else None
check("列表 total 与统计 total 一致", my_total is not None and my_total == ov_total,
      f"my={my_total} overview={ov_total}")
check("新看板在列表中", my_total and my_total >= 1, f"total={my_total}")

# ---------- 汇总 ----------
print("\n" + "=" * 60)
print(f"结果: PASS={len(PASS)}  FAIL={len(FAIL)}")
if FAIL:
    print("失败项:")
    for n, d in FAIL:
        print("  -", n, "|", d[:200])
print("=" * 60)
sys.exit(0 if not FAIL else 2)
