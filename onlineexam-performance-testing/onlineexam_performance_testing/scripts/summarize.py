#!/usr/bin/env python
"""把 report/results.csv 汇总成 Markdown 表格（写报告时直接粘）。

    D:/OnlineExam/.venv/Scripts/python.exe scripts/summarize.py > report/summary.md

同名 label 出现多次时以最后一行为准（中途重跑过同一个用例）。
"""

from __future__ import annotations

import csv
from collections import OrderedDict
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
RESULTS = WS / "report" / "results.csv"

ORDER = ["runserver", "waitress", "waitress-conn60"]
TITLES = {
    "runserver": "runserver（开发服务器，单进程多线程，CONN_MAX_AGE=0）",
    "waitress": "waitress（8 线程，CONN_MAX_AGE=0）",
    "waitress-conn60": "waitress + 连接复用（8 线程，CONN_MAX_AGE=60）",
}


def load() -> "OrderedDict[str, dict]":
    rows: OrderedDict[str, dict] = OrderedDict()
    with RESULTS.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows[row["label"]] = row  # 后者覆盖前者
    return rows


def fmt(v, digits=1):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if digits == 0:
        return str(int(f))
    return f"{f:.{digits}f}"


def main() -> int:
    rows = load()
    for server in ORDER:
        subset = [r for r in rows.values() if r["server"] == server]
        if not subset:
            continue
        print(f"\n### {TITLES.get(server, server)}\n")
        print("| 用例 | 并发 | 请求数 | 失败 | 失败率 | RPS | P50(ms) | P95(ms) | P99(ms) | CPU% | RSS(MB) | 连接峰值 |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in subset:
            print(
                f"| `{r['label']}` | {r['users']} | {r['requests']} | {r['failures']} | "
                f"{fmt(r['fail_rate_pct'], 2)}% | {fmt(r['rps'], 2)} | {fmt(r['p50_ms'], 0)} | "
                f"{fmt(r['p95_ms'], 0)} | {fmt(r['p99_ms'], 0)} | {fmt(r['cpu_avg'])} | "
                f"{fmt(r['rss_start'])}→{fmt(r['rss_end'])} | {r['conn_peak']} |"
            )

    # 阶梯曲线：同一并发下三种口径的 RPS / P95 对比
    print("\n### 阶梯对照（交卷场景，RPS / P95）\n")
    print("| 并发 | runserver RPS | runserver P95 | waitress RPS | waitress P95 | 连接复用 RPS | 连接复用 P95 |")
    print("|---|---|---|---|---|---|---|")
    for users, tag in [(10, "step010"), (20, "step020"), (50, "step050"), (100, "step100")]:
        cells = []
        for server in ORDER:
            r = rows.get(f"{ {'runserver':'rs','waitress':'wt','waitress-conn60':'opt'}[server] }_{tag}")
            cells.append(f"{fmt(r['rps'], 2)}" if r else "-")
            cells.append(f"{fmt(r['p95_ms'], 0)}" if r else "-")
        print(f"| {users} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
