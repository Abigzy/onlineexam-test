# -*- coding: utf-8 -*-
"""一次性探针：验证「用表单会话调 API 造数」这条路走不走得通（
跑完即删，结论写进步骤 5 的 data_factory。"""
import json
import os
import re
from datetime import datetime, timedelta, timezone as tz

for k in [k for k in os.environ if "proxy" in k.lower()]:
    os.environ.pop(k, None)

import requests

BASE = "http://127.0.0.1:8931"
API = BASE + "/api/v1"


def login(u, p):
    s = requests.Session()
    s.trust_env = False
    r = s.get(BASE + "/login/", timeout=20)
    tok = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text).group(1)
    r = s.post(BASE + "/login/",
               data={"csrfmiddlewaretoken": tok, "username": u, "password": p, "next": ""},
               headers={"Referer": BASE + "/login/"}, allow_redirects=False, timeout=20)
    assert r.status_code == 302, r.status_code
    # SessionAuthentication 对非安全方法强制 CSRF：带上 cookie 里的 token + Referer
    token2 = s.cookies.get("csrftoken")
    s.headers.update({"X-CSRFToken": token2 or "", "Referer": BASE + "/"})
    return s


def call(s, method, path, **kw):
    kw.setdefault("timeout", 60)
    r = s.request(method, API + path, **kw)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:200]}
    print("%-6s %-46s HTTP %s code=%s msg=%s" % (
        method, path, r.status_code, body.get("code"), str(body.get("message"))[:40]))
    return r, body


adm = login("admin", "Exam@123456")
call(adm, "GET", "/exams/?page_size=1")

now = datetime.now(tz(timedelta(hours=8)))
payload_paper = {
    "title": "UIAT_探针卷",
    "total_count": 6,
    "target_difficulty": 2.0,
    "duration_minutes": 30,
    "subject": "",
    "seed": 20261104,
}
r, b = call(adm, "POST", "/papers/random-compose/", json=payload_paper)
print("  body:", json.dumps(b, ensure_ascii=False)[:400])
d = b.get("data") or {}
paper_id = (d.get("paper") or {}).get("id") or d.get("id")

if paper_id:
    call(adm, "POST", "/papers/%s/status/" % paper_id, json={"status": "published"})
    payload_exam = {
        "title": "UIAT_探针考试",
        "paper_id": paper_id,
        "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "duration_minutes": 30,
        "open_to_all": True,
        "show_score_immediately": True,
        "max_attempts": 2,
    }
    r, b = call(adm, "POST", "/exams/", json=payload_exam)
    print("  body:", json.dumps(b, ensure_ascii=False)[:400])
    d2 = b.get("data") or {}
    exam_id = (d2.get("exam") or {}).get("id") or d2.get("id")
    if exam_id:
        call(adm, "POST", "/exams/%s/status/" % exam_id, json={"status": "published"})
        stu = login("student", "Exam@123456")
        _, lb = call(stu, "GET", "/exams/?page_size=50")
        rows = (lb.get("data") or {}).get("results") or (lb.get("data") or [])
        seen = [x.get("title") for x in rows] if isinstance(rows, list) else []
        print("  学生可见考试含新考试:", "UIAT_探针考试" in str(seen))
        _, sb = call(stu, "POST", "/exams/%s/start/" % exam_id, json={})
        detail = (sb.get("data") or {})
        print("  attempt:", detail.get("attempt", {}).get("id") if isinstance(detail.get("attempt"), dict) else detail.get("id"))
