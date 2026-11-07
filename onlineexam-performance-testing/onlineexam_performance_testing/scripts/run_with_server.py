#!/usr/bin/env python
"""起服务 → 跑用例 → 关服务，一条命令完成（适合沙箱/CI 里没有后台进程管理的情况）。

    # 调优组：waitress + 连接复用，只跑混合场景
    .venv/Scripts/python.exe scripts/run_with_server.py \
        --mode waitress --threads 8 --conn-max-age 60 \
        --suite waitress-conn60 --only mix50

    # runserver 口径重跑判分与混合
    .venv/Scripts/python.exe scripts/run_with_server.py \
        --mode runserver --suite runserver --only grade10,mix50

参数分两段：`--mode/--threads/--conn-max-age` 给服务器，其余透传给 `run_suite.py`。
服务进程退出/被 kill 后端口立刻释放，下一轮不会串味。
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
# 被测系统根目录：默认 D:/OnlineExam，可用环境变量 OE_PROJECT 覆盖
PROJECT = Path(os.environ.get("OE_PROJECT", "D:/OnlineExam"))
PY = PROJECT / ".venv" / "Scripts" / "python.exe"
HOST = "127.0.0.1"
PORT = 8024


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((HOST, port)) == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["runserver", "waitress"], default="waitress")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--conn-max-age", type=int, default=0)
    ap.add_argument("--nothreading", action="store_true")
    ap.add_argument("--suite", required=True, help="写进结果的服务器口径标签，如 waitress-conn60")
    ap.add_argument("--only", default="")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--label-suffix", default="")
    args = ap.parse_args()

    if port_open(PORT):
        print(f"[FATAL] {PORT} 已被占用，先关掉旧服务", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env.update(DB_NAME="online_exam_perf", AI_PROVIDER="mock", PERF_CONN_MAX_AGE=str(args.conn_max_age))
    serve_cmd = [
        str(PY), "-u", str(WS / "scripts" / "serve.py"),
        "--server", args.mode, "--port", str(PORT),
        "--threads", str(args.threads), "--conn-max-age", str(args.conn_max_age),
    ]
    if args.nothreading:
        serve_cmd.append("--nothreading")

    log = (WS / "report" / f"server_{args.suite}.log").open("w", encoding="utf-8")
    print(f"[serve] {args.mode} threads={args.threads} conn_max_age={args.conn_max_age}", flush=True)
    proc = subprocess.Popen(serve_cmd, cwd=str(WS), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 90
        while time.time() < deadline:
            if proc.poll() is not None:
                print("[FATAL] 服务启动失败，见 report/server_*.log", file=sys.stderr)
                return 2
            if port_open(PORT):
                break
            time.sleep(1)
        else:
            print("[FATAL] 等待端口超时", file=sys.stderr)
            return 2
        print(f"[serve] 已监听 {PORT}", flush=True)

        suite_cmd = [
            str(PY), str(WS / "scripts" / "run_suite.py"),
            "--server", args.suite, "--host", f"http://{HOST}:{PORT}",
        ]
        if args.only:
            suite_cmd += ["--only", args.only]
        if args.resume:
            suite_cmd.append("--resume")
        if args.label_suffix:
            suite_cmd += ["--label-suffix", args.label_suffix]
        return subprocess.run(suite_cmd, cwd=str(WS), env=env).returncode
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        print("[serve] 已停止", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
