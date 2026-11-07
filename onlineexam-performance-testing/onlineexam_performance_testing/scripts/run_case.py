#!/usr/bin/env python
"""单个压测用例执行器：跑一次 Locust + 同步采样服务端资源 + 解析结果。

用法::

    D:/OnlineExam/.venv/Scripts/python.exe scripts/run_case.py \
        --label rs_step_050 --server runserver \
        --scenario ExamSubmitUser --users 50 --spawn 5 --duration 90

产出（默认写到 report/）::

    <label>_stats.csv / _stats_history.csv / _failures.csv / .html   原始产物
    <label>_endpoints.json                                          按接口拆分
    results.csv                                                     全局汇总（追加）

为什么自己采服务端指标：Django 侧没有 APM，不采就只能看到客户端视角的
"慢"，说不清是 CPU 打满、内存泄漏还是连接堆住了。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

WS = Path(__file__).resolve().parent.parent
LOCUST = Path("D:/OnlineExam/.venv/Scripts/locust.exe")
REPORT = WS / "report"
RESULTS = REPORT / "results.csv"


# ----------------------------------------------------------------------
# 服务端资源采样
# ----------------------------------------------------------------------
def listen_pid(port: int) -> int | None:
    """按监听端口找服务进程。比匹配命令行可靠（runserver 会 spawn 子进程）。"""
    for conn in psutil.net_connections(kind="tcp"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port:
            return conn.pid
    return None


class Sampler(threading.Thread):
    """每 2 秒记一次：进程 CPU、RSS、到被测端口的 ESTABLISHED 连接数。"""

    def __init__(self, pid: int, port: int):
        super().__init__(daemon=True)
        self.pid = pid
        self.port = port
        self.rows: list[dict] = []
        self._stop = threading.Event()

    def run(self) -> None:
        try:
            proc = psutil.Process(self.pid)
        except psutil.NoSuchProcess:
            return
        proc.cpu_percent(None)  # 第一次调用只是打点
        cores = psutil.cpu_count(logical=True) or 1
        while not self._stop.is_set():
            try:
                cpu = proc.cpu_percent(None)  # 占单核的百分比，>100 表示多线程并行
                rss = proc.memory_info().rss / 1024 / 1024
                conns = sum(
                    1
                    for c in psutil.net_connections(kind="tcp")
                    if c.raddr and c.raddr.port == self.port and c.status == psutil.CONN_ESTABLISHED
                )
                self.rows.append(
                    {"ts": time.time(), "cpu": cpu, "cpu_pct": cpu / cores, "rss_mb": round(rss, 1), "conns": conns}
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(2)

    def stop(self) -> list[dict]:
        self._stop.set()
        return self.rows


def summarize_samples(rows: list[dict]) -> dict:
    if not rows:
        return {}
    cpu = [r["cpu_pct"] for r in rows]
    rss = [r["rss_mb"] for r in rows]
    conns = [r["conns"] for r in rows]
    # 去掉启动阶段前 10% 的样本，避免预热拉低均值
    steady = rows[max(1, len(rows) // 10):]
    cpu_s = [r["cpu_pct"] for r in steady] or cpu
    return {
        "cpu_avg": round(sum(cpu_s) / len(cpu_s), 1),
        "cpu_max": round(max(cpu), 1),
        "rss_start": rss[0],
        "rss_end": rss[-1],
        "rss_peak": max(rss),
        "rss_drift_pct": round((rss[-1] - rss[0]) / rss[0] * 100, 1) if rss[0] else 0,
        "conn_peak": max(conns),
        "samples": len(rows),
    }


# ----------------------------------------------------------------------
# Locust 结果解析
# ----------------------------------------------------------------------
def read_stats(prefix: Path) -> tuple[dict, list[dict]]:
    stats_csv = Path(str(prefix) + "_stats.csv")
    if not stats_csv.exists():
        return {}, []
    with stats_csv.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    def num(row, key, cast=float, default=0):
        try:
            return cast(row.get(key) or default)
        except (TypeError, ValueError):
            return default

    agg, endpoints = {}, []
    for row in rows:
        item = {
            "type": row.get("Type", ""),
            "name": row.get("Name", ""),
            "requests": num(row, "Request Count", int),
            "failures": num(row, "Failure Count", int),
            "rps": num(row, "Requests/s"),
            "avg": num(row, "Average Response Time"),
            "p50": num(row, "50%"),
            "p95": num(row, "95%"),
            "p99": num(row, "99%"),
            "max": num(row, "Max Response Time"),
        }
        if item["type"] == "Aggregated" or item["name"] == "Aggregated":
            agg = item
        else:
            endpoints.append(item)
    endpoints.sort(key=lambda x: -x["requests"])
    return agg, endpoints


def read_failures(prefix: Path) -> list[dict]:
    path = Path(str(prefix) + "_failures.csv")
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [{"method": r.get("Method"), "name": r.get("Name"), "error": r.get("Error"), "occurrences": r.get("Occurrences")} for r in csv.DictReader(fh)]


def append_result(row: dict) -> None:
    REPORT.mkdir(parents=True, exist_ok=True)
    fields = list(row.keys())
    exists = RESULTS.exists()
    if exists:
        with RESULTS.open(encoding="utf-8", newline="") as fh:
            old = next(csv.DictReader(fh), None)
        if old and list(old.keys()) != fields:
            RESULTS.unlink()  # 列变了就重开，避免错位
            exists = False
    with RESULTS.open("a" if exists else "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="用例标识，产物文件名前缀")
    ap.add_argument("--server", default="runserver", help="服务口径：runserver / waitress")
    ap.add_argument("--scenario", default="ALL", help="Locust 用户类名；ALL 表示按权重混合")
    ap.add_argument("--users", type=int, required=True)
    ap.add_argument("--spawn", type=int, default=5, help="每秒爬升用户数；等于 users 即瞬时冲击")
    ap.add_argument("--duration", type=int, default=90, help="持续秒数")
    ap.add_argument("--host", default="http://127.0.0.1:8024")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    REPORT.mkdir(parents=True, exist_ok=True)
    port = int(args.host.rsplit(":", 1)[1].strip("/"))
    pid = listen_pid(port)
    if not pid:
        print(f"[FATAL] {args.host} 上没有监听进程，先起服务", file=sys.stderr)
        return 2

    prefix = REPORT / args.label
    cmd = [
        str(LOCUST), "-f", str(WS / "locustfile.py"),
        "--headless", "-u", str(args.users), "-r", str(args.spawn), "-t", f"{args.duration}s",
        "--only-summary", "--host", args.host,
        "--csv", str(prefix), "--html", str(prefix) + ".html",
    ]
    if args.scenario != "ALL":
        cmd.append(args.scenario)

    print(f"[run] {args.label} server={args.server} scenario={args.scenario} "
          f"u={args.users} r={args.spawn} t={args.duration}s pid={pid}", flush=True)
    sampler = Sampler(pid, port)
    sampler.start()
    started = time.time()
    # 本机压本机必须绕开系统代理：requests 会读取 HTTP(S)_PROXY，
    # 一旦走了代理，压测就变成了"测代理"，响应时间与失败率全不可信。
    child_env = {
        k: v for k, v in os.environ.items()
        if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}
    }
    child_env["no_proxy"] = child_env["NO_PROXY"] = "127.0.0.1,localhost"
    proc = subprocess.run(
        cmd, cwd=str(WS), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=child_env,
    )
    elapsed = time.time() - started
    samples = sampler.stop()
    sampler.join(timeout=3)

    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:], file=sys.stderr)

    agg, endpoints = read_stats(prefix)
    fails = read_failures(prefix)
    res = summarize_samples(samples)
    total = agg.get("requests", 0)
    fail = agg.get("failures", 0)
    row = {
        "label": args.label,
        "server": args.server,
        "scenario": args.scenario,
        "users": args.users,
        "spawn": args.spawn,
        "duration": args.duration,
        "elapsed": round(elapsed, 1),
        "requests": total,
        "failures": fail,
        "fail_rate_pct": round(fail / total * 100, 2) if total else 0,
        "rps": agg.get("rps", 0),
        "avg_ms": agg.get("avg", 0),
        "p50_ms": agg.get("p50", 0),
        "p95_ms": agg.get("p95", 0),
        "p99_ms": agg.get("p99", 0),
        "max_ms": agg.get("max", 0),
        **res,
        "note": args.note,
    }
    append_result(row)
    (REPORT / f"{args.label}_endpoints.json").write_text(
        json.dumps({"summary": row, "endpoints": endpoints, "failures": fails}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"[done] {args.label} req={total} fail={fail} rps={row['rps']} "
        f"p50={row['p50_ms']} p95={row['p95_ms']} p99={row['p99_ms']} "
        f"cpu={res.get('cpu_avg')}% rss={res.get('rss_start')}->{res.get('rss_end')}MB "
        f"conns_peak={res.get('conn_peak')}",
        flush=True,
    )
    if fails:
        for f in fails[:5]:
            print(f"       [fail] {f['method']} {f['name']} x{f['occurrences']}: {str(f['error'])[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
