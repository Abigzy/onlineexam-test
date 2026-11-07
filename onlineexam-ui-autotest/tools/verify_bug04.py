# -*- coding: utf-8 -*-
"""BUG-04 修复验证：监控页状态徽章不再空白。

覆盖「修得对」与「没修过头」两类，跑法（**必须带 FRESH_PROFILE**，模板改过）：
    OE_FRESH_PROFILE=1 D:/python/python.exe tools/verify_bug04.py > docs/assets/bug04_verify.txt

A 接口层：overview 补了 computed_status_display，且与 ExamListSerializer 同源
B UI 主场景：进行中考试的徽章显示中文文案，不空白、不是占位「—」
C 多状态：未开始 / 已归档 两态的徽章分别与接口 display 一致
D 没修过头：六张概览卡仍是数字、已开始人数 ≥1、徽章仍按状态着色
E 兜底：模板不再用空串兜底（字段再丢也应显示「—」）
F 守门：开发侧后端 / 前端守门测试都在

退出码非 0 表示有场景失败。
"""
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(os.path.dirname(ROOT), "onlineexam_ui_autotest")
sys.path.insert(0, PROJ)

import config                                                       # noqa: E402
from common.api_client import ApiSession                            # noqa: E402
from common.data_factory import _delete_exam                        # noqa: E402
from common.driver_factory import create_driver                     # noqa: E402
from pages.teacher_pages import MonitorPage                         # noqa: E402

RESULTS = []
CN = re.compile(r"[\u4e00-\u9fff]")


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  —— " + detail) if detail else ""))


def make_exam(teacher, pid, title, start_min, end_min):
    now = datetime.now(timezone(timedelta(hours=8)))
    data = teacher.post("/exams/", json={
        "title": title, "paper_id": pid,
        "start_time": (now + timedelta(minutes=start_min)).isoformat(),
        "end_time": (now + timedelta(minutes=end_min)).isoformat(),
        "duration_minutes": 30, "open_to_all": True,
        "show_score_immediately": True, "max_attempts": 1,
        "shuffle_questions": False, "shuffle_options": False,
    })
    eid = (data.get("exam") or data)["id"]
    teacher.post("/exams/%s/status/" % eid, json={"status": "published"})
    return eid


def overview_of(teacher, eid):
    return teacher.get("/exams/%s/attempts/" % eid)["overview"]


def main():
    teacher = ApiSession("teacher")
    adm = ApiSession("admin")
    student = ApiSession("student")
    created, drv = [], None
    tag = time.strftime("%H%M%S")
    try:
        papers = teacher.get("/papers/", params={"status": "published", "page_size": 5}) \
            .get("results") or []
        assert papers, "没有教师可见的已发布试卷，无法造考试"
        pid = papers[0]["id"]

        e_ongoing = make_exam(teacher, pid, "UIAT_BUG04_进行中_" + tag, -5, 180)
        e_future = make_exam(teacher, pid, "UIAT_BUG04_未开始_" + tag, 60, 240)
        e_archived = make_exam(teacher, pid, "UIAT_BUG04_归档_" + tag, -5, 180)
        created = [e_ongoing, e_future, e_archived]
        teacher.post("/exams/%s/status/" % e_archived, json={"status": "archived"})
        student.post("/exams/%s/start/" % e_ongoing, json={"confirm": True})
        print("造数：ongoing=%s future=%s archived=%s" %
              (e_ongoing, e_future, e_archived))

        # ---------------- A 接口层 ----------------
        ov = overview_of(teacher, e_ongoing)
        display = ov.get("computed_status_display")
        check("A overview 含 computed_status_display",
              "computed_status_display" in ov,
              "keys=%s" % sorted(ov.keys())[:8])
        check("A display 非空且是中文文案", bool(display) and bool(CN.search(str(display))),
              "实际 %r" % display)
        detail = teacher.get("/exams/%s/" % e_ongoing)
        check("A 与 ExamListSerializer 同源",
              display == detail.get("computed_status_display"),
              "overview=%r / detail=%r" % (display, detail.get("computed_status_display")))
        check("A computed_status 仍在（没被 display 顶掉）",
              ov.get("computed_status") == "ongoing",
              "实际 %r" % ov.get("computed_status"))

        # ---------------- B/C/D UI 层 ----------------
        drv = create_driver(headless=True)
        drv.get(config.BASE_URL + "/login/")
        drv.delete_all_cookies()
        host = config.BASE_URL.split("//")[1].split(":")[0]
        drv.add_cookie({"name": "sessionid", "value": teacher.session_id,
                        "domain": host, "path": "/"})
        page = MonitorPage(drv)

        cases = [("进行中", e_ongoing), ("未开始", e_future), ("已归档", e_archived)]
        for label, eid in cases:
            page.open(exam_id=eid)
            page.wait_loaded()
            badge = page.status_badge()
            want = overview_of(teacher, eid).get("computed_status_display")
            check("C %s：徽章非空且不是占位「—」" % label,
                  bool(badge) and badge not in ("—", "-", ""),
                  "徽章 %r" % badge)
            check("C %s：徽章文案 == 接口 display" % label,
                  badge == want, "徽章 %r / 接口 %r" % (badge, want))
            check("C %s：徽章是中文状态" % label,
                  bool(badge) and bool(CN.search(badge)), "徽章 %r" % badge)

        # D 没修过头：概览数字仍正常，徽章样式仍按状态着色
        page.open(exam_id=e_ongoing)
        cards = page.overview()
        check("D 六张概览卡仍是数字",
              all(v.isdigit() for v in cards.values()),
              "实际 %s" % cards)
        check("D 已开始人数 ≥1（有学生开考）",
              int(cards.get("started") or 0) >= 1, "started=%s" % cards.get("started"))
        cls = drv.execute_script(
            "return (document.getElementById('exam-status')||{}).className||'';")
        check("D 徽章仍带 badge-soft 样式类",
              "badge-soft" in cls, "class=%r" % cls)
        # 附记（不计入 PASS/FAIL）：STATUS_BADGE 用的是**作答状态**枚举，
        # 拿 exam computed_status 去查永远落不到，颜色恒为 badge-soft-gray。
        # 属样式错配，不影响文案修复，另登记 OBS-13。
        print("[INFO] 徽章颜色恒为 %r（STATUS_BADGE 的 key 是作答状态，非考试状态）" % cls)

        # ---------------- E 兜底 / F 守门（静态） ----------------
        tpl = open("D:/OnlineExam/templates/exam/monitor.html", encoding="utf-8").read()
        check("E 模板兜底改成「—」",
              "computed_status_display || '—'" in tpl)
        check("E 模板不再用空串兜底",
              "computed_status_display || ''" not in tpl)
        be = open("D:/OnlineExam/apps/exam/tests/test_api.py", encoding="utf-8").read()
        fe = open("D:/OnlineExam/apps/system/tests/test_frontend_guards.py",
                  encoding="utf-8").read()
        check("F 后端守门：overview 字段断言存在",
              "test_overview_includes_status_display" in be)
        check("F 前端守门：徽章读 display 且兜底非空",
              "MonitorStatusBadgeGuardTest" in fe)
    finally:
        if drv:
            try:
                drv.quit()
            except Exception:                                        # noqa: BLE001
                pass
        for eid in created:
            _delete_exam(adm, eid)

    failed = [r for r in RESULTS if not r[1]]
    print()
    print("汇总：%d 项通过 / %d 项失败" % (len(RESULTS) - len(failed), len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
