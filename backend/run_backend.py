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


def main():
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
