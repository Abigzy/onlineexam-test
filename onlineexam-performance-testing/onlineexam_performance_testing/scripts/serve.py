#!/usr/bin/env python
"""起压测用的应用服务器（三种口径，用于对照）。

    # 口径 1：Django 开发服务器（默认多线程）—— 历史基线的口径
    .venv/Scripts/python.exe scripts/serve.py --server runserver

    # 口径 2：开发服务器但强制单线程 —— 用来量化"串行处理"到底多贵
    .venv/Scripts/python.exe scripts/serve.py --server runserver --nothreading

    # 口径 3：waitress（生产级 WSGI，8 线程）—— 最接近部署的一组
    .venv/Scripts/python.exe scripts/serve.py --server waitress --threads 8

设计说明：
  * 不修改被测项目的任何文件，settings 用本工程根目录的 ``perf_settings.py``；
  * 起服务前强制校验库名，**指到演示库就直接退出**（压测写坏演示数据是不可逆事故）；
  * AI 强制 mock，防止判分链路意外调大模型产生费用。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
# 被测系统根目录：默认 D:/OnlineExam，可用环境变量 OE_PROJECT 覆盖
PROJECT = Path(os.environ.get("OE_PROJECT", "D:/OnlineExam"))
EXPECTED_DB = "online_exam_perf"


def bootstrap() -> None:
    """把路径与环境变量准备好，再交给 Django。"""
    sys.path.insert(0, str(PROJECT))
    sys.path.insert(0, str(WS))
    os.environ["DJANGO_SETTINGS_MODULE"] = "perf_settings"
    os.environ.setdefault("DB_NAME", EXPECTED_DB)
    os.environ["AI_PROVIDER"] = "mock"  # 双保险：脚本里判分也固定 with_ai=false
    os.environ["DB_SKIP_VERSION_CHECK"] = "True"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", choices=["runserver", "waitress"], default="runserver")
    ap.add_argument("--port", type=int, default=8024)
    ap.add_argument("--threads", type=int, default=8, help="waitress 线程数")
    ap.add_argument("--nothreading", action="store_true", help="runserver 强制单线程（对照用）")
    ap.add_argument("--conn-max-age", type=int, default=0, help="数据库连接复用秒数（0=每请求断开）")
    args = ap.parse_args()

    os.environ["PERF_CONN_MAX_AGE"] = str(args.conn_max_age)

    # 顺序很重要：bootstrap() 会补上 DB_NAME 默认值，必须在它之后再校验，
    # 否则没手动传环境变量时会误判成「库名不对」直接退出。
    bootstrap()

    if os.environ.get("DB_NAME") != EXPECTED_DB:
        print(f"[FATAL] 库名必须是 {EXPECTED_DB}，当前 {os.environ.get('DB_NAME')!r}", file=sys.stderr)
        return 2

    import django

    django.setup()
    from django.conf import settings

    actual = settings.DATABASES["default"]["NAME"]
    if actual != EXPECTED_DB:
        print(f"[FATAL] settings 解析出的库是 {actual!r}，不是 {EXPECTED_DB}", file=sys.stderr)
        return 2

    mode = args.server if not (args.server == "runserver" and args.nothreading) else "runserver-nothreading"
    print(
        f"[serve] mode={mode} port={args.port} db={actual} debug={settings.DEBUG} "
        f"conn_max_age={settings.DATABASES['default'].get('CONN_MAX_AGE')} "
        f"ai={os.environ.get('AI_PROVIDER')}",
        flush=True,
    )

    if args.server == "runserver":
        from django.core.management import call_command

        argv = [f"127.0.0.1:{args.port}", "--noreload"]
        if args.nothreading:
            argv.append("--nothreading")
        call_command("runserver", *argv)
        return 0

    from django.core.wsgi import get_wsgi_application
    from waitress import serve

    serve(
        get_wsgi_application(),
        host="127.0.0.1",
        port=args.port,
        threads=args.threads,
        channel_timeout=120,
        ident="OnlineExam-perf",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
