#!/usr/bin/env python
"""构造「一个班的待批卷」：清空作答记录，再用真实接口产生 N 份已交卷。

    .venv/Scripts/python.exe scripts/make_grade_sample.py --count 50

为什么需要它：判分场景要压的是「教师批一个班」，而不是「批 1600 份历史作答」。
前者 `GET /grading/queue/` 约几百毫秒，后者实测 10-12 秒——那属于容量问题，
单独作为一条发现记录，混进场景压测会把三个场景的结论搅在一起。

走真实 HTTP 接口而不是直接写库：这样产生的 attempt/answer 状态与线上一致，
判分链路拿到的数据分布也可信。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import requests

WS = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8024"
API = BASE + "/api/v1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--host", default=BASE)
    args = ap.parse_args()

    global API
    API = args.host.rstrip("/") + "/api/v1"
    for key in list(os.environ):
        if "proxy" in key.lower():
            os.environ.pop(key)

    tokens = json.loads((WS / "scripts" / ".perf_tokens.json").read_text(encoding="utf-8"))
    meta = json.loads((WS / "scripts" / ".perf_meta.json").read_text(encoding="utf-8"))
    exam_id = meta["exam_id"]
    names = meta["student_usernames"][: args.count]

    ok = fail = 0
    attempt_ids: list[int] = []
    started = time.perf_counter()
    for name in names:
        headers = {"Authorization": f"Bearer {tokens[name]['access']}"}
        sess = requests.Session()
        sess.trust_env = False
        r = sess.post(f"{API}/exams/{exam_id}/start/", headers=headers, json={"confirm": True}, timeout=60)
        if r.status_code != 200:
            fail += 1
            continue
        data = r.json().get("data") or {}
        attempt_id = (data.get("attempt") or {}).get("id")
        qids = [item["paper_question_id"] for item in data.get("questions") or []]
        items = [
            {"paper_question_id": qid, "selected_labels": random.choice(["A", "B", "C", "D"])}
            for qid in qids
        ]
        r = sess.post(
            f"{API}/attempts/{attempt_id}/submit/",
            headers=headers, json={"reason": "manual", "items": items}, timeout=60,
        )
        if r.status_code == 200 and (r.json() or {}).get("code") == 0:
            ok += 1
            attempt_ids.append(int(attempt_id))
        else:
            fail += 1

    elapsed = time.perf_counter() - started
    print(f"[grade-sample] 已交卷 {ok} 份，失败 {fail} 份，用时 {elapsed:.1f}s", flush=True)

    # 冻结名单给判分场景用：locustfile.py 读到这个文件就不再打队列接口
    out = WS / "scripts" / ".perf_grade_sample.json"
    out.write_text(
        json.dumps(
            {"exam_id": exam_id, "count": len(attempt_ids), "attempt_ids": attempt_ids,
             "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[grade-sample] 冻结名单写入 {out.name}（{len(attempt_ids)} 份）", flush=True)

    # 顺带量一下队列接口在当前规模下的耗时（容量曲线的数据点）
    teacher = tokens[meta["teacher"]]["access"]
    sess = requests.Session()
    sess.trust_env = False
    t0 = time.perf_counter()
    r = sess.get(
        f"{API}/grading/queue/", headers={"Authorization": f"Bearer {teacher}"},
        params={"exam_id": exam_id, "only_pending": "false"}, timeout=300,
    )
    cost = (time.perf_counter() - t0) * 1000
    count = (r.json().get("data") or {}).get("count") if r.status_code == 200 else "ERR"
    print(f"[grade-sample] 队列接口 {r.status_code} 耗时 {cost:.0f}ms，待批 {count} 份", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
