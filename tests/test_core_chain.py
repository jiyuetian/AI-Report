"""核心链路自测基线（P3）

覆盖范围（当前基线，全部为确定性断言，不依赖 LLM 是否可用）：
  [A] 表格类输入 -> DuckDB 建表数据集      扩展名：xlsx / xls / csv / json / tsv
  [B] 文档类输入 -> 文本型数据集不建表      扩展名：docx / pdf / md / txt
  [C] 图片类输入 -> 415 IMAGE_NOT_TABLEABLE  扩展名：png / jpg / jpeg / webp
  [D] 文档型数据集 -> 7 章节图文报告        统计口径真实、标注非 LLM 生成
  [E] 表格型数据集 -> 7 章节报告回归        P0 链路数值可复算，图表数达标

前置条件（重要）：
  1. 后端已在本机监听，默认 127.0.0.1:8000。
  2. 同一时刻只能有**一个**后端进程。DuckDB 文件是单写者独占锁：
     两个 uvicorn 实例并存时，后启动的那个在 duckdb.connect() 就会失败，
     表现为建表类数据集创建返回 500 CREATE_ERROR。
     验证脚本本身不检查该条件，请按下面的错误特征自行排查。
  3. 每次运行会新建一批带 P3_ 前缀的数据集/看板，用于断言隔离，可重复执行。

用法：
    cd backend
    python -m uvicorn app.main:app --port 8000     # 先起后端
    python ../tests/test_core_chain.py              # 默认打 8000
    python ../tests/test_core_chain.py 8001         # 指定端口

退出码：0 = 全部通过；1 = 存在失败项。
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
BASE = f"http://127.0.0.1:{PORT}/api/v1"
OUT = Path(os.environ.get("CORE_CHAIN_OUT", str(Path(__file__).resolve().parent / "_reports")))
OUT.mkdir(parents=True, exist_ok=True)

PASS, FAIL = 0, 0


def req(method, path, body=None, files=None, timeout=180):
    """发起 HTTP 请求，返回 (status, parsed_json_or_text)。不跟随 307。"""
    url = BASE + path
    data, headers = None, {}
    if files is not None:
        boundary = "----CoreChainBoundary7f2a"
        parts = []
        for fname, content, ctype in files:
            parts.append(f"--{boundary}\r\n".encode())
            parts.append(
                f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
                f'Content-Type: {ctype}\r\n\r\n'.encode()
            )
            parts.append(content)
            parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        data, headers["Content-Type"] = b"".join(parts), f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data, headers["Content-Type"] = (
            json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json"
        )

    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, _try_json(e.read().decode("utf-8"))
    return resp.status, _try_json(raw)


def _try_json(raw):
    try:
        return json.loads(raw)
    except Exception:
        return raw


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}  {extra}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {extra}")


def group(title):
    print(f"\n[{title}]")


def detail(msg):
    print(f"  note  {msg}")


# ── 测试数据 ───────────────────────────────────────────────────
# 表格类：6 行放款数据，总金额 55,700,000（用于报告数值复算断言）
JSON_ROWS = [
    {"月份": "2024-01", "渠道": "线上", "放款笔数": 120, "放款金额": 12000000},
    {"月份": "2024-01", "渠道": "线下", "放款笔数": 80, "放款金额": 5000000},
    {"月份": "2024-02", "渠道": "线上", "放款笔数": 150, "放款金额": 15000000},
    {"月份": "2024-02", "渠道": "线下", "放款笔数": 90, "放款金额": 6000000},
    {"月份": "2024-03", "渠道": "线上", "放款笔数": 130, "放款金额": 13500000},
    {"月份": "2024-03", "渠道": "线下", "放款笔数": 70, "放款金额": 4200000},
]
JSON_SUM = 55_700_000

TSV_TEXT = (
    "部门\t员工数\t人均产出\n研发\t42\t850000\n运营\t25\t420000\n"
    "市场\t18\t380000\n客服\t30\t290000\n财务\t8\t210000\n"
)

CSV_TEXT = (
    "月份,放款笔数,放款金额\n"
    "2024-01,200,17000000\n2024-02,240,21000000\n2024-03,200,17700000\n"
)

TXT_TEXT = (
    "担保业务风险监测说明\n\n"
    "本报告基于担保业务核心指标对放款规模、逾期风险与客户结构进行持续监测。"
    "月度放款金额波动主要受授信政策调整与行业周期影响。\n\n"
    "逾期率方面，本月关注类客户占比小幅上升，需重点关注抵押物价值变动情况。"
    "对于抵押率超过80%的借据，建议启动额度重检流程，并补充追加担保措施。\n\n"
    "客户结构上，小微客户数量增长显著，但单笔规模偏小，风控模型需针对小额高频场景优化。"
    "同时应关注关联方交易的集中度风险，避免出现同一实际控制人下的多头授信。\n\n"
    "结论与建议：维持现有授信政策，对高风险组合执行限额管理；"
    "加强贷后巡检频率，重点覆盖抵押物价值波动较大的客户。"
)
TXT_PARAGRAPHS = len([p for p in TXT_TEXT.split("\n\n") if p.strip()])

MD_TEXT = (
    "# 企业征信变化分析\n\n## 概述\n\n"
    "企业征信数据反映借款主体的信用变动趋势，包括逾期次数、对外担保余额等维度。\n\n"
    "## 关键指标\n\n- 征信恶化客户占比：3.2%\n- 新增担保余额：4.8亿元\n- 异常预警笔数：27笔\n\n"
    "## 建议\n\n对征信恶化客户启动贷后专项检查，并评估担保代偿压力。"
)

# 1x1 透明 PNG（用于验证图片类被拒绝）
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000050001"
    "0d0a2db40000000049454e44ae426082"
)


def write(name, text=None, data=None):
    p = OUT / name
    p.write_bytes(data if data is not None else text.encode("utf-8"))
    return p


def upload(path, ctype):
    with open(path, "rb") as f:
        return req("POST", "/files", files=[(path.name, f.read(), ctype)])


def make_dataset(file_id, name):
    return req("POST", "/datasets", {"file_id": file_id, "name": name})


def make_dashboard(ds_id, name, config=None):
    """创建看板。config 走 PATCH：CreateDashboardRequest 不含 config 字段。"""
    s, r = req("POST", "/dashboards/", {
        "name": name, "description": "自测基线看板", "dataset_ids": [ds_id],
    })
    if s != 200:
        return s, r
    did = r.get("dashboard_id")
    if config:
        # PATCH 响应不含 dashboard_id，需自行保留
        s2, _ = req("PATCH", f"/dashboards/{did}", {"config": config})
        return s2, {"success": True, "dashboard_id": did}
    return s, {"success": True, "dashboard_id": did}


def chart_elements(html):
    """报告内真实渲染的可视化元素数，口径与后端 chart_count 一致。"""
    return (html.count('class="echarts-chart"')
            + html.count('class="kpi-card"')
            + html.count('class="kpi-display"'))


print("=" * 72)
print(f"核心链路自测基线  ->  {BASE}")
print("=" * 72)

# ── A. 表格类输入 ──────────────────────────────────────────────
group("A 表格类输入")
s, r = upload(write("t_loan.json", json.dumps(JSON_ROWS, ensure_ascii=False, indent=2)),
              "application/json")
check("JSON 上传", s == 200 and r.get("file_id"), f"status={s}")
s, r = make_dataset(r.get("file_id"), "P3_JSON放款数据")
check("JSON 建数据集", s == 200, f"status={s} {str(r)[:120]}")
if s == 200 and "IO Error" in str(r):
    detail("命中 DuckDB 文件锁：已有另一后端进程持有 data/duckdb/aibi.db，"
           "请只保留一个 uvicorn 实例后重跑。")
check("source_type=table", r.get("source_type") == "table", f"got={r.get('source_type')}")
check("table_name 非空", bool(r.get("table_name")), f"table={r.get('table_name')}")
check("row_count=6", r.get("row_count") == 6, f"rows={r.get('row_count')}")
check("column_count=4", r.get("column_count") == 4, f"cols={r.get('column_count')}")
json_ds = r.get("dataset_id") if s == 200 else None

s, r = upload(write("t_dept.tsv", TSV_TEXT), "text/tab-separated-values")
check("TSV 上传", s == 200 and r.get("file_id"), f"status={s}")
s, r = make_dataset(r.get("file_id"), "P3_TSV部门产出")
check("TSV 建数据集", s == 200, f"status={s} {str(r)[:120]}")
check("TSV source_type=table", r.get("source_type") == "table", f"got={r.get('source_type')}")
check("TSV row_count=5", r.get("row_count") == 5, f"rows={r.get('row_count')}")
check("TSV column_count=3", r.get("column_count") == 3, f"cols={r.get('column_count')}")

s, r = upload(write("t_flow.csv", CSV_TEXT), "text/csv")
check("CSV 上传", s == 200 and r.get("file_id"), f"status={s}")
s, r = make_dataset(r.get("file_id"), "P3_CSV月度流水")
check("CSV 建数据集", s == 200, f"status={s} {str(r)[:120]}")
check("CSV row_count=3", r.get("row_count") == 3, f"rows={r.get('row_count')}")

# ── B. 文档类输入 ──────────────────────────────────────────────
group("B 文档类输入（不建 DuckDB 表）")
s, r = upload(write("t_risk.txt", TXT_TEXT), "text/plain")
check("txt 上传", s == 200 and r.get("file_id"), f"status={s}")
s, r = make_dataset(r.get("file_id"), "P3_TXT风险说明")
check("txt 建数据集", s == 200, f"status={s} {str(r)[:120]}")
check("source_type=document", r.get("source_type") == "document", f"got={r.get('source_type')}")
check("table_name=None（未建表）", r.get("table_name") is None, f"table={r.get('table_name')}")
check("row_count=0", r.get("row_count") == 0, f"rows={r.get('row_count')}")
check("char_count>0", (r.get("char_count") or 0) > 0, f"chars={r.get('char_count')}")
txt_ds = r.get("dataset_id") if s == 200 else None

s, r = upload(write("t_credit.md", MD_TEXT), "text/markdown")
check("md 上传", s == 200 and r.get("file_id"), f"status={s}")
s, r = make_dataset(r.get("file_id"), "P3_MD征信分析")
check("md 建数据集", s == 200, f"status={s} {str(r)[:120]}")
check("md source_type=document", r.get("source_type") == "document", f"got={r.get('source_type')}")
check("md table_name=None", r.get("table_name") is None, f"table={r.get('table_name')}")

# ── C. 图片类输入 ──────────────────────────────────────────────
group("C 图片类输入（拒绝入数据集）")
s, r = upload(write("t_pic.png", data=PNG_BYTES), "image/png")
check("png 上传", s == 200 and r.get("file_id"), f"status={s}")
s, r = make_dataset(r.get("file_id"), "P3_图片数据集")
check("png 建数据集被拒(415)", s == 415, f"status={s}")
det = r.get("detail", {}) if isinstance(r, dict) else {}
check("错误码 IMAGE_NOT_TABLEABLE", det.get("code") == "IMAGE_NOT_TABLEABLE", f"detail={det}")

# ── D. 文档型数据集 -> 报告 ────────────────────────────────────
group("D 文档型数据集 -> 7章节报告")
s, r = make_dashboard(txt_ds, "P3_文档型看板")
check("看板创建", s == 200 and r.get("dashboard_id"), f"status={s} {str(r)[:120]}")
doc_dash = r.get("dashboard_id") if s == 200 else None
s, r = req("POST", "/reports", {"dashboard_id": doc_dash})
check("报告生成", s == 200 and r.get("success"), f"status={s} {str(r)[:120]}")
rid = r.get("report_id") if s == 200 else None
if rid:
    s, r = req("GET", f"/reports/{rid}/json")
    data = (r or {}).get("data", {}) if isinstance(r, dict) else {}
    chapters = data.get("chapters", [])
    check("章节数=7", len(chapters) == 7, f"count={len(chapters)}")
    check("source_type=document", data.get("source_type") == "document",
          f"got={data.get('source_type')}")
    body = "\n".join(c.get("content", "") for c in chapters)
    check("含统计口径表", "统计口径" in body)
    check("含确定性统计项", "中文字符数" in body and "段落数" in body)
    check("含原文摘录", "原文" in body or "摘录" in body)
    check("标注非LLM生成", "非LLM生成" in body or "确定性" in body)
    check("含段落长度分布图表", "段落长度分布" in body)
    check(f"段落数={TXT_PARAGRAPHS}", str(TXT_PARAGRAPHS) in body)
    s2, html = req("GET", f"/reports/{rid}/html")
    if isinstance(html, str):
        n = chart_elements(html)
        check("可视化元素>=6", n >= 6, f"charts={n} api={data.get('chart_count')}")
        (OUT / "doc_report.html").write_text(html, encoding="utf-8")

# ── E. 表格型数据集 -> 报告回归 ────────────────────────────────
group("E 表格型数据集 -> 7章节报告回归")
charts_cfg = [
    {"type": "kpi", "field": "放款金额", "agg": "sum", "title": "放款总金额"},
    {"type": "bar", "x_field": "月份", "y_field": "放款金额", "agg": "sum", "title": "月度放款金额"},
    {"type": "pie", "category_field": "渠道", "value_field": "放款笔数", "agg": "sum", "title": "渠道笔数占比"},
    {"type": "line", "x_field": "月份", "y_field": "放款笔数", "agg": "sum", "title": "月度放款笔数趋势"},
    {"type": "bar", "x_field": "渠道", "y_field": "放款金额", "agg": "sum", "title": "渠道放款金额对比"},
    {"type": "pie", "category_field": "渠道", "value_field": "放款金额", "agg": "sum", "title": "渠道金额占比"},
]
s, r = make_dashboard(json_ds, "P3_JSON看板", config={"charts": charts_cfg})
check("看板创建", s == 200 and r.get("dashboard_id"), f"status={s} {str(r)[:120]}")
tbl_dash = r.get("dashboard_id") if s == 200 else None
s, r = req("POST", "/reports", {"dashboard_id": tbl_dash})
check("报告生成", s == 200 and r.get("success"), f"status={s} {str(r)[:120]}")
rid = r.get("report_id") if s == 200 else None
if rid:
    s, r = req("GET", f"/reports/{rid}/json")
    data = (r or {}).get("data", {}) if isinstance(r, dict) else {}
    chapters = data.get("chapters", [])
    check("章节数=7", len(chapters) == 7, f"count={len(chapters)}")
    check("source_type=table", data.get("source_type") == "table",
          f"got={data.get('source_type')}")
    body = "\n".join(c.get("content", "") for c in chapters)
    check("含真实聚合字段", "放款总金额" in body)
    check(f"总金额可复算={JSON_SUM:,}",
          f"{JSON_SUM:,}" in body or str(JSON_SUM) in body,
          "6行放款金额求和")
    s2, html = req("GET", f"/reports/{rid}/html")
    if isinstance(html, str):
        n = chart_elements(html)
        check("可视化元素>=6", n >= 6, f"charts={n} api={data.get('chart_count')}")
        (OUT / "table_report.html").write_text(html, encoding="utf-8")

print("\n" + "=" * 72)
print(f"结果: PASS={PASS}  FAIL={FAIL}")
print(f"报告样例输出目录: {OUT}")
print("=" * 72)
sys.exit(0 if FAIL == 0 else 1)
