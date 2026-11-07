#!/usr/bin/env python
"""按方案跑完整测试矩阵（对同一个正在运行的服务端逐档加压）。

用法::

    # 服务端已起在 8024，先跑 runserver 轮
    .venv/Scripts/python.exe scripts/run_suite.py --server runserver
    # 换 waitress 起服务后跑对照轮
    .venv/Scripts/python.exe scripts/run_suite.py --server waitress

设计取舍：每档之间不重建库。重建会让"第 5 档"和"第 1 档"面对不同数据量，
反而失去可比性；本套件用固定的 `users` 递增观察趋势，累积效应留给 soak 阶段专门暴露。
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
# 被测系统根目录：默认 D:/OnlineExam，可用环境变量 OE_PROJECT 覆盖
PROJECT = Path(os.environ.get("OE_PROJECT", "D:/OnlineExam"))
PY = PROJECT / ".venv" / "Scripts" / "python.exe"

# (场景类, 并发, 爬升, 秒, 标签后缀, 说明)
CASES = [
    ("ExamStartBurstUser", 1, 1, 60, "baseline", "单用户基线：各接口裸耗时"),
    ("ExamSubmitUser", 10, 5, 90, "step010", "阶梯 10 并发（交卷）"),
    ("ExamSubmitUser", 20, 5, 90, "step020", "阶梯 20 并发（交卷）"),
    ("ExamSubmitUser", 50, 5, 90, "step050", "阶梯 50 并发（交卷）"),
    ("ExamSubmitUser", 100, 10, 90, "step100", "阶梯 100 并发（交卷）"),
    ("ExamSubmitUser", 50, 50, 120, "submit50", "场景 A 交卷洪峰：50 人瞬时同时交卷"),
    ("ExamStartBurstUser", 50, 50, 120, "start50", "场景 B 开考读峰：50 人瞬时拉卷"),
    ("ExamGradingUser", 10, 10, 90, "grade10", "场景 C 教师批量判分"),
    ("ALL", 50, 10, 120, "mix50", "混合场景：交卷/读峰/判分按 3:3:1 权重"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, help="服务口径标签，写进结果，如 runserver / waitress")
    ap.add_argument("--host", default="http://127.0.0.1:8024")
    ap.add_argument("--only", default="", help="只跑标签含该子串的用例，逗号分隔")
    ap.add_argument("--resume", action="store_true", help="跳过 report/results.csv 里已有结果的用例")
    ap.add_argument("--label-suffix", default="", help="给标签加后缀，避免覆盖同名结果（如 _t16）")
    args = ap.parse_args()

    picked = CASES
    if args.only:
        needles = [x.strip() for x in args.only.split(",") if x.strip()]
        picked = [c for c in CASES if any(n in c[4] for n in needles)]

    prefix = {"runserver": "rs", "waitress": "wt", "waitress-conn60": "opt"}.get(
        args.server, args.server[:2]
    )

    done_labels: set[str] = set()
    results = WS / "report" / "results.csv"
    if args.resume and results.exists():
        with results.open(encoding="utf-8", newline="") as fh:
            done_labels = {row["label"] for row in csv.DictReader(fh)}

    print(f"== {args.server} 轮：{len(picked)} 个用例，目标 {args.host}", flush=True)
    for cls, users, spawn, dur, tag, note in picked:
        label = f"{prefix}_{tag}{args.label_suffix}"
        if label in done_labels:
            print(f"[skip] {label} 已有结果", flush=True)
            continue
        cmd = [
            str(PY), str(WS / "scripts" / "run_case.py"),
            "--label", label, "--server", args.server, "--scenario", cls,
            "--users", str(users), "--spawn", str(spawn), "--duration", str(dur),
            "--host", args.host, "--note", note,
        ]
        rc = subprocess.run(cmd, cwd=str(WS)).returncode
        if rc != 0:
            print(f"[warn] {label} 返回 {rc}，继续下一档", flush=True)
    print("== 本轮结束", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
