"""调试用后端启动器（不改动 run_backend.py，另建新文件）。
新增能力（用于定位「进程 exit=-1 且无 traceback」的硬退出）：
  1. faulthandler 落盘：C 级崩溃（段错误/栈溢出）会写出 Python 调用栈
  2. sys.excepthook / threading.excepthook / asyncio 全局异常处理：捕获所有未处理异常
  3. atexit：记录正常退出路径
  4. 每 5s 心跳，便于判断进程是卡死还是已退出
"""
import os
import sys
import time
import atexit
import threading
import traceback

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

LOG_PATH = os.path.join(os.path.dirname(BACKEND_DIR), 'backend_debug.log')

import faulthandler  # noqa: E402

_fh = open(LOG_PATH, 'a', encoding='utf-8', buffering=1)
faulthandler.enable(file=_fh, all_threads=True)


def _w(msg):
    try:
        _fh.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        _fh.flush()
    except Exception:
        pass


def _hook(exc_type, exc, tb):
    _w("!!! sys.excepthook 捕获未处理异常")
    _w("".join(traceback.format_exception(exc_type, exc, tb)))


sys.excepthook = _hook


def _thread_hook(args):
    _w(f"!!! 线程异常 {args.exc_type} {args.exc_value}")
    _w("".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


threading.excepthook = _thread_hook


@atexit.register
def _bye():
    _w("=== atexit：进程正常退出路径 ===")


def _heartbeat():
    n = 0
    while True:
        time.sleep(5)
        n += 5
        _w(f"heartbeat alive {n}s")


threading.Thread(target=_heartbeat, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    import asyncio

    _w("=== run_backend_dbg 启动 ===")

    def _loop_handler(loop, context):
        _w(f"!!! asyncio 未处理异常: {context.get('message')} "
           f"exc={context.get('exception')!r}")
        _w(context.get('message', ''))
        if context.get('exception'):
            _w("".join(traceback.format_exception(
                type(context['exception']), context['exception'],
                context['exception'].__traceback__)))

    try:
        config = uvicorn.Config("app.main:app", host="127.0.0.1", port=8000, log_level="info")
        server = uvicorn.Server(config)
        # 注册 asyncio 全局异常处理
        orig_run = server.run

        async def _wrapped_run(*a, **kw):
            try:
                asyncio.get_running_loop().set_exception_handler(_loop_handler)
            except Exception:
                pass
            return await orig_run(*a, **kw)

        server.run = _wrapped_run
        asyncio.run(server.serve())
    except Exception:
        _w("!!! uvicorn 主流程异常：")
        _w(traceback.format_exc())
        raise
    _w("=== uvicorn serve() 返回，进程即将退出 ===")
