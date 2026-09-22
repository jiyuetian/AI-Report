"""开发用后端启动器：自行切换到 backend 目录再起 uvicorn，避免 bash shim 在中文路径下 cd 失败。

B5 单实例约束（路演防护）：
- pidfile 检测：已有同进程存活则拒绝重复启动，避免两个后端进程抢 DuckDB 单文件锁。
- 端口占用检测：端口被占但 pidfile 失效（如被强杀）同样拒绝，兜底防双进程。
"""
import os
import sys
import socket
import atexit

# 切换到本文件所在目录（= backend 根），保证 ./data/aibi.db 等相对路径正确
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# 后端需经活代理访问外网 LLM。工具 shell 环境锁定了不稳定的 59106 代理，
# 故在 import 任何网络库之前强制注入活代理；可用 LLM_PROXY 环境变量覆盖
# （该键为自定义键，不被工具 shell 锁定），便于路演换网络时配置。
_PROXY = os.environ.get("LLM_PROXY") or "http://127.0.0.1:7897"
os.environ["HTTPS_PROXY"] = _PROXY
os.environ["HTTP_PROXY"] = _PROXY

import uvicorn

HOST = "127.0.0.1"
PORT = 8000
PIDFILE = os.path.join(BACKEND_DIR, ".backend.pid")


def _port_in_use(host: str, port: int) -> bool:
    """检测端口是否已被占用（另一后端进程在跑 → B5 双进程防护）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def _read_pid(pidfile: str):
    try:
        with open(pidfile, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _pid_alive(pid) -> bool:
    if pid is None:
        return False
    try:
        # Windows 下 signal 0 仅探测进程是否存在，不发送信号
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _cleanup_pidfile():
    try:
        if os.path.exists(PIDFILE):
            os.remove(PIDFILE)
    except Exception:
        pass


def _validate_duckdb(duck_path: str) -> bool:
    """启动前校验业务数据仓库（DuckDB）：文件不存在 → fail-fast 拒绝启动。

    背景：DuckDB 对不存在的路径会【静默新建空库】且无任何报错，症状是所有看板
    显示「该图表无可绘制数据」，排查成本极高。故启动时必须把"连错库/库缺失"
    这类问题拦在起服务之前。
    """
    if not os.path.exists(duck_path):
        print(f"[DUCKDB-FAIL] 业务数据仓库不存在：{duck_path}")
        print("[DUCKDB-FAIL] 拒绝启动：否则 DuckDB 会在该路径静默新建空库，所有看板将显示「该图表无可绘制数据」。")
        print("[DUCKDB-FAIL] 处理：①确认 DUCKDB_PATH/.env 指向正确仓库 ②从备份恢复 data/duckdb/aibi.db "
              "③确属全新环境请手动创建库后再启动。")
        return False
    try:
        import duckdb
        con = duckdb.connect(duck_path, read_only=True)
        n = con.execute("select count(*) from duckdb_tables() where table_name like 'ds_%'").fetchone()[0]
        total = con.execute("select count(*) from duckdb_tables()").fetchone()[0]
        con.close()
        if n == 0:
            print(f"[DUCKDB-WARN] 库文件存在但业务表 ds_* 数为 0（总表 {total}）：{duck_path}")
            print("[DUCKDB-WARN] 极可能是错库/空库；若确属全新空环境可忽略。")
        else:
            print(f"[DUCKDB-OK] 业务数据仓库就绪：{duck_path}（ds_* 表 {n} 张 / 总表 {total}）")
    except Exception as e:
        # 只读打开失败（如被别的进程独占）只告警不阻断，避免误伤正常启动
        print(f"[DUCKDB-WARN] 无法只读打开仓库做完整性校验（不阻断启动）：{e}")
    return True


def main():
    # 0.3 环境隔离：启动即明确打印后端绑定的库，杜绝"默认指向错误库"类路由 bug。
    # DUCKDB_PATH 指向业务数据（图表数值来源）；DATABASE_URL 指向元数据（用户/看板/版本）。
    from app.core.config import settings, _DEFAULT_DUCKDB_PATH
    _duck = settings.DUCKDB_PATH          # 业务数据仓库（已由 config 解析为绝对路径）
    _meta = os.environ.get("DATABASE_URL") or settings.SQLITE_DATABASE_URL  # 元数据库

    # 只在「显式指定了非规范仓库」时告警。历史坑：此处曾建议 export 到 qa_aibi.db，
    # 导致有人照做后新数据集进旧库、老看板读不到表（P0-2 双库错配）。
    # 注意：基准必须是 config 的规范默认 _DEFAULT_DUCKDB_PATH，不能用 settings.DUCKDB_PATH
    # —— 后者会被同名环境变量覆盖，导致"真的指到旧库"时反而比不出来、告警失效。
    _explicit = os.environ.get("DUCKDB_PATH")
    if _explicit:
        _explicit_abs = _explicit if os.path.isabs(_explicit) else os.path.normpath(
            os.path.join(BACKEND_DIR, _explicit))
        if os.path.normpath(_explicit_abs) != os.path.normpath(_DEFAULT_DUCKDB_PATH):
            print(f"[0.3-WARN] DUCKDB_PATH 显式指向非默认仓库：{_explicit_abs}")
            print(f"[0.3-WARN] 业务数据仓库默认为 {_DEFAULT_DUCKDB_PATH}；"
                  "除非你明确知道在做分库，否则请勿改（历史坑：指到 qa_aibi.db 会导致老看板图表全空）。")
    print(f"[0.3] 后端绑定 -> DuckDB(业务数据)={_duck}  MetaDB(元数据)={_meta}")

    # 启动校验 fail-fast：库缺失直接拒绝启动，避免静默建空库
    if not _validate_duckdb(_duck):
        sys.exit(1)

    # B5-1：pidfile 检测——若已有同进程存活，拒绝重复启动
    old_pid = _read_pid(PIDFILE)
    if old_pid and _pid_alive(old_pid):
        print(f"[B5] 已有后端进程在运行 (pid={old_pid})，拒绝重复启动以避免双进程抢 DuckDB 文件。")
        print(f"[B5] 如需重启，请先结束该进程（任务管理器结束 pid={old_pid}），或删除 {PIDFILE}")
        sys.exit(1)

    # B5-2：端口占用检测——端口被占但 pidfile 不存在/失效（如被强杀），同样拒绝
    if _port_in_use(HOST, PORT):
        print(f"[B5] 端口 {PORT} 已被占用（可能存在未记录的后端进程）。拒绝启动以免双进程。")
        print(f"[B5] 请先确认并结束占用 {PORT} 的进程，再重试。")
        sys.exit(1)

    # 写 pidfile，进程退出时自动清理
    with open(PIDFILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    atexit.register(_cleanup_pidfile)

    print(f"[B5] 启动后端 pid={os.getpid()} → http://{HOST}:{PORT}")
    uvicorn.run("app.main:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
