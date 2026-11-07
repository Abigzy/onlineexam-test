# -*- coding: utf-8 -*-
"""BUG-01 修复验证（4 个场景，含"不误伤"回归）。

场景：
    A 被引用 + 草稿      -> 期望 4xx + code=13008 + 文案含「引用」（修复前是 500/50000）
    B 被引用 + 已发布    -> 期望 4xx + code=13001（原有行为不变）
    C 无引用 + 草稿      -> 期望删除成功（不能被修过头误伤）
    D 无引用 + 已发布    -> 先退草稿再删，期望成功

用法：python tools/verify_bug01.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(os.path.dirname(ROOT), "onlineexam_ui_autotest")
sys.path.insert(0, PROJ)

import config                                                              # noqa: E402  (clear proxy)
from common.api_client import ApiSession                                   # noqa: E402
from common.data_factory import _delete_exam                               # noqa: E402

TZ = timezone(timedelta(hours=8))
adm = ApiSession(config.ACCOUNTS["admin"])
results = []


def make_paper(title, count=2):
    data = adm.post("/papers/random-compose/",
                    json={"title": title, "total_count": count,
                          "target_difficulty": 2.0, "duration_minutes": 10})
    return (data.get("paper") or data)["id"]


def make_exam(paper_id, title):
    now = datetime.now(TZ)
    data = adm.post("/exams/", json={
        "title": title, "paper_id": paper_id,
        "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=1)).isoformat(),
        "duration_minutes": 10, "open_to_all": True})
    return (data.get("exam") or data)["id"]


def delete_paper(pid):
    """直接打 DELETE，不经过 ApiSession 的断言语义，拿原始状态码与 code。"""
    r = adm.session.delete(config.API_URL + "/papers/%s/" % pid, timeout=30)
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body.get("code"), str(body.get("message", ""))


def record(name, ok, detail):
    results.append((name, ok, detail))
    print("[%s] %-40s %s" % ("PASS" if ok else "FAIL", name, detail))


tag = config.tag("BUG01VERIFY")
# ---------------- A：被引用 + 草稿
pid = make_paper(tag + "_A")
adm.post("/papers/%s/status/" % pid, json={"status": "published"})
eid = make_exam(pid, tag + "_A")
adm.post("/papers/%s/status/" % pid, json={"status": "draft"})
status, code, msg = delete_paper(pid)
record("A 被引用+草稿 -> 4xx 业务错误",
       400 <= status < 500 and code == 13008 and "引用" in msg,
       "HTTP %s code=%s msg=%s" % (status, code, msg[:60]))
_delete_exam(adm, eid)

# ---------------- B：被引用 + 已发布
pid_b = make_paper(tag + "_B")
adm.post("/papers/%s/status/" % pid_b, json={"status": "published"})
eid_b = make_exam(pid_b, tag + "_B")
status, code, msg = delete_paper(pid_b)
record("B 被引用+已发布 -> 13001 不变",
       400 <= status < 500 and code == 13001,
       "HTTP %s code=%s msg=%s" % (status, code, msg[:50]))
_delete_exam(adm, eid_b)

# ---------------- C：无引用 + 草稿（不能被误伤）
pid_c = make_paper(tag + "_C")
status, code, msg = delete_paper(pid_c)
record("C 无引用+草稿 -> 删除成功",
       status in (200, 204), "HTTP %s code=%s" % (status, code))

# ---------------- D：无引用 + 已发布
pid_d = make_paper(tag + "_D")
adm.post("/papers/%s/status/" % pid_d, json={"status": "published"})
adm.post("/papers/%s/status/" % pid_d, json={"status": "draft"})
status, code, msg = delete_paper(pid_d)
record("D 无引用+退草稿 -> 删除成功",
       status in (200, 204), "HTTP %s code=%s" % (status, code))

print("-" * 70)
bad = [r for r in results if not r[1]]
print("场景 %d 个，通过 %d 个，失败 %d 个" % (len(results), len(results) - len(bad), len(bad)))
sys.exit(1 if bad else 0)
