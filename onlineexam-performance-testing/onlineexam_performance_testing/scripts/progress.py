#!/usr/bin/env python
"""查看进度：哪些用例已跑完、哪些还没跑。

    D:/OnlineExam/.venv/Scripts/python.exe scripts/progress.py

读 ``report/results.csv``（run_case.py 每跑完一个用例追加一行），
对照 ``scripts/run_suite.py::CASES`` 的矩阵，输出 done / pending。
中断后先跑这个，就知道下一步该跑哪条。
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
RESULTS = WS / "report" / "results.csv"

sys.path.insert(0, str(WS / "scripts"))
from run_suite import CASES  # noqa: E402

SERVERS = ["runserver", "waitress", "waitress-conn60"]
PREFIX = {"runserver": "rs", "waitress": "wt", "waitress-conn60": "opt"}
# 调优组只跑验收线附近与四场景，低并发阶梯有意省略（结论由前两轮给出）
SKIP = {"waitress-conn60": {"baseline", "step010", "step020"}}


def load_rows() -> dict[str, dict]:
    if not RESULTS.exists():
        return {}
    with RESULTS.open(encoding="utf-8", newline="") as fh:
        return {row["label"]: row for row in csv.DictReader(fh)}


def main() -> int:
    rows = load_rows()
    total = done = skipped = 0
    for server in SERVERS:
        print(f"\n== {server} 轮")
        print(f"{'用例':<26}{'并发':>5}{'时长':>6}  {'状态':<8}{'请求':>6}{'失败':>5}{'P95':>8}{'RPS':>7}")
        for cls, users, spawn, dur, tag, note in CASES:
            label = f"{PREFIX[server]}_{tag}"
            row = rows.get(label)
            if row:
                total += 1
                done += 1
                print(
                    f"{label:<26}{users:>5}{dur:>5}s  {'done':<8}"
                    f"{int(row['requests']):>6}{int(row['failures']):>5}"
                    f"{float(row['p95_ms']):>8.0f}{float(row['rps']):>7.1f}"
                )
            elif tag in SKIP.get(server, set()):
                skipped += 1
                print(f"{label:<26}{users:>5}{dur:>5}s  {'skip':<8}{'-':>6}{'-':>5}{'-':>8}{'-':>7}")
            else:
                total += 1
                print(f"{label:<26}{users:>5}{dur:>5}s  {'pending':<8}{'-':>6}{'-':>5}{'-':>8}{'-':>7}")
    print(f"\n进度：{done}/{total} 个用例完成" + (f"（另有 {skipped} 个按设计跳过）" if skipped else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
