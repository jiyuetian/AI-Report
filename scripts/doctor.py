# -*- coding: utf-8 -*-
"""
AI-Report 环境自检（doctor）—— night42 Task C3

检查项（逐项打印 OK/FAIL + 修复建议）：
  1. Python 版本（必须 3.12；本机默认 3.10 会误报编译/运行错误）
  2. 后端依赖（fastapi/sqlalchemy/uvicorn/duckdb/openpyxl/python-docx）
  3. DuckDB 业务库存在性
  4. 端口 8000 / 5173 占用情况
  5. 后端健康（/api/v1/health）—— 仅在后端已启动时检查
  6. /downloads 静态路由可达性 —— 仅后端已启动时检查

用法：
  cd <repo>
  py -3.12 scripts/doctor.py
退出码：0=全部通过（或仅"需运行后端"的项跳过）；1=存在硬失败。
"""
import os
import sys
import socket

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BACKEND = os.path.join(REPO, "backend")
DATA_DUCK = os.path.join(BACKEND, "data", "duckdb", "aibi.db")

REQUIRED_PY = (3, 12)
BACKEND_DEPS = ["fastapi", "sqlalchemy", "uvicorn", "duckdb", "openpyxl", "docx"]


def _py_version():
    return sys.version_info[:2]


def _port_open(host, port, timeout=1.0):
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


def _http_get(url, timeout=3.0):
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "doctor"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return None, str(e)


def main():
    fails = 0
    print("=" * 60)
    print(" AI-Report 环境自检（doctor）")
    print("=" * 60)

    # 1. Python 版本
    major, minor = _py_version()
    if (major, minor) >= REQUIRED_PY:
        print("[OK]   Python 版本 %d.%d（要求 >= %d.%d）" % (major, minor, REQUIRED_PY[0], REQUIRED_PY[1]))
    else:
        fails += 1
        print("[FAIL] Python 版本 %d.%d；本仓后端依赖需 3.12，当前默认 3.10 会误报。" % (major, minor))
        print("       修复：用 `py -3.12` 启动；确保 Python 3.12 已安装且在 PATH。")

    # 2. 后端依赖
    missing = []
    for mod in BACKEND_DEPS:
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if not missing:
        print("[OK]   后端依赖齐全：%s" % ", ".join(BACKEND_DEPS))
    else:
        fails += 1
        print("[FAIL] 缺失依赖：%s" % ", ".join(missing))
        print("       修复：cd backend && py -3.12 -m pip install -r requirements.txt")

    # 3. DuckDB 业务库
    if os.path.exists(DATA_DUCK):
        print("[OK]   DuckDB 业务库存在：%s" % DATA_DUCK)
    else:
        print("[WARN] DuckDB 业务库缺失：%s" % DATA_DUCK)
        print("       说明：首次启动后端会自动建库（可能无样例数据）；如需样例先跑 scripts/make_demo_db.py。")

    # 4. 端口占用
    for port in (8000, 5173):
        if _port_open("127.0.0.1", port):
            print("[WARN] 端口 %d 已被占用（可能上一次服务未关闭）。" % port)
            print("       修复：关闭占用进程（结束 uvicorn / vite / npm 窗口）后再启动。")
        else:
            print("[OK]   端口 %d 空闲" % port)

    # 5. 后端健康（仅当 8000 在监听时）
    if _port_open("127.0.0.1", 8000):
        status, body = _http_get("http://127.0.0.1:8000/api/v1/health")
        if status == 200:
            print("[OK]   后端 /api/v1/health 返回 200")
        else:
            fails += 1
            print("[FAIL] 后端 /api/v1/health 异常：status=%s body=%s" % (status, body[:200]))
            print("       修复：查看 backend/server.log，常见为依赖缺失或 DuckDB 锁。")
        # 6. /downloads 路由
        st2, _ = _http_get("http://127.0.0.1:8000/downloads/")
        # /downloads 对缺失文件一般 404，但路由必须存在（非 500/连接拒绝）
        if st2 in (200, 404):
            print("[OK]   后端 /downloads 静态路由可达（status=%s）" % st2)
        elif st2 is None:
            print("[WARN] /downloads 不可达（后端未完全就绪？）")
        else:
            fails += 1
            print("[FAIL] 后端 /downloads 返回异常 status=%s" % st2)
    else:
        print("[SKIP] 后端未运行，跳过 /health 与 /downloads 检查（先启动 dev_up.ps1）。")

    print("=" * 60)
    if fails == 0:
        print(" 结论：环境就绪 ✓（仅'需运行后端'项跳过不计失败）")
        return 0
    print(" 结论：存在 %d 项硬失败，请按上面修复建议处理。" % fails)
    return 1


if __name__ == "__main__":
    sys.exit(main())
