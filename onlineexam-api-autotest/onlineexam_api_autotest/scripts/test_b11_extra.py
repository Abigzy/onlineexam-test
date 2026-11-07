# -*- coding: utf-8 -*-
"""B11 细节补齐：组卷严格模式与 AI 组卷、采纳 AI 建议分、趋势预测、
监考可疑过滤、班级表单校验。

这些是第二批里因「需构造数据」而跳过的用例，现在用独立考试实例构造。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from common.assert_tools import CommonAssert
from encap_api.admin_api import ClassroomApi
from encap_api.content_api import PaperApi
from encap_api.grading_api import GradingApi
from encap_api.insight_api import AnalyticsApi, ProctoringApi

pytestmark = pytest.mark.l1

FMT = "%Y-%m-%d %H:%M:%S"


def _window(minutes: int = 90):
    now = datetime.now()
    return (now - timedelta(minutes=5)).strftime(FMT), (now + timedelta(minutes=minutes)).strftime(FMT)


def _exam_payload(fx, key, **over):
    start, end = _window()
    payload = {
        "paper_id": fx["papers"]["published"],
        "title": f"{fx['prefix']}_B11_{key}",
        "start_time": start,
        "end_time": end,
        "duration_minutes": 60,
        "max_attempts": 10,
        "participant_ids": [fx["students"]["a"]["id"]],
    }
    payload.update(over)
    return payload


def _published_exam(teacher_api, fx, key, **over) -> int:
    created = teacher_api.create(**_exam_payload(fx, key, **over))
    CommonAssert.assert_ok(created, 201)
    eid = created.data["id"]
    CommonAssert.assert_ok(teacher_api.status(eid, "published"))
    return eid


# ======================================================================
# 一、组卷：严格模式 / AI 组卷（PAPER-08 / PAPER-28）
# ======================================================================
def test_add_duplicate_question_strict_rejected(seeded_paper_api, fx):
    """strict=true 时重复加题 → 400/13003；非严格模式只跳过（B3 已覆盖）。"""
    created = seeded_paper_api.create(
        title=f"{fx['prefix']}_B11_strict", subject=fx["subject"],
        duration_minutes=30, pass_score=1,
    )
    CommonAssert.assert_ok(created, 201)
    pid = created.data["id"]
    CommonAssert.assert_ok(seeded_paper_api.add_questions(pid, [fx["questions"]["single"]]))

    resp = seeded_paper_api.add_questions(pid, [fx["questions"]["single"]], strict=True)
    CommonAssert.assert_error(resp, 400, 13003)
    # 卷内仍只有 1 题，总分没翻倍
    detail = seeded_paper_api.detail(pid)
    assert detail.data["question_count"] == 1


def test_ai_compose_dry_run(seeded_paper_api, fx):
    """AI 组卷试算：返回可行性结论，不落库。"""
    before = seeded_paper_api.statistics().data["total"]
    resp = seeded_paper_api.ai_compose(
        subject=fx["subject"],
        blueprint=[{"type": "single", "count": 2, "score": 2}],
        target_difficulty=2,
        dry_run=True,
    )
    CommonAssert.assert_ok(resp)
    assert "feasible" in resp.data
    assert seeded_paper_api.statistics().data["total"] == before, "dry_run 不应落库"


def test_ai_compose_blueprint_duplicate_type_rejected(seeded_paper_api, fx):
    """蓝图里同一题型出现两次 → 400，提示只能出现一次。"""
    resp = seeded_paper_api.ai_compose(
        subject=fx["subject"],
        blueprint=[{"type": "single", "count": 2, "score": 2},
                   {"type": "single", "count": 3, "score": 2}],
        dry_run=True,
    )
    CommonAssert.assert_error(resp, 400, 40000)


# ======================================================================
# 二、判分：采纳 AI 建议分（GRAD-13）
# ======================================================================
def _subjective_attempt(seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx, key):
    """造一份含主观题作答的已交卷作答，返回 attempt_id。"""
    eid = _published_exam(seeded_exam_api, fx, key, show_score_immediately=True)
    resp = student_a_exam_api.start(eid)
    CommonAssert.assert_ok(resp)
    aid = resp.data["attempt"]["id"]
    text = fx["answers"]["fill"]
    items = [{"paper_question_id": pq, "answer_text": text}
             for question_id, pq in fx["paper_questions"].items()
             if int(question_id) in (fx["questions"]["short"], fx["questions"]["essay"])]
    CommonAssert.assert_ok(student_a_attempt_api.save_answers(aid, items))
    CommonAssert.assert_ok(student_a_attempt_api.submit(aid))
    return aid


def test_review_accept_ai_score(seeded_exam_api, student_a_exam_api, student_a_attempt_api,
                               seeded_grading_api, seeded_teacher_client, fx):
    """accept_ai=true 采纳 AI 建议分：answer.score 等于 ai_score，且写入复核记录。

    注意：学生视角的 ai_score 受可见性门禁（未出分时为 null），
    所以这里用教师身份读明细。
    """
    from encap_api.exam_api import AttemptApi

    aid = _subjective_attempt(seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx, "accept_ai")
    graded = seeded_grading_api.grade(aid, with_ai=True, provider="mock")
    CommonAssert.assert_ok(graded)

    rows = AttemptApi(seeded_teacher_client).answers(aid).data["results"]
    target = next((r for r in rows if r.get("ai_score") is not None), None)
    assert target is not None, "AI 批改后应有 ai_score"

    resp = seeded_grading_api.review(target["id"], accept_ai=True)
    CommonAssert.assert_ok(resp)
    # 返回 {feedback, answer, grading}；采纳后 answer.score 应等于 AI 建议分
    assert float(resp.data["answer"]["score"]) == float(target["ai_score"])
    # ReviewAction：accept 直接采纳 / adjust 在建议分上调整 / override 完全自评
    assert resp.data["feedback"]["action"] in ("accept", "adjust", "override")
    assert resp.data["feedback"]["action"] == "accept", "accept_ai=true 应记为「直接采纳」"
    assert resp.data["feedback"]["ai_score"] is not None

    feedback = seeded_grading_api.feedback_list(attempt_id=aid)
    CommonAssert.assert_ok(feedback)
    assert feedback.data["count"] >= 1


# ======================================================================
# 三、学情：趋势点数与预测（AN-09 / AN-10）
# ======================================================================
def test_trend_without_enough_points_has_no_prediction(student_b_client, fx):
    """无作答历史的学生：points 为空，不给预测值（不臆造结论）。"""
    api = AnalyticsApi(student_b_client)
    resp = api.trend(fx["students"]["b"]["id"])
    CommonAssert.assert_ok(resp)
    assert resp.data["points"] == []
    assert resp.data["fit"]["enough_points"] is False
    assert resp.data["fit"]["predict_next"] is None
    assert resp.data["summary"]["predict_percent"] is None


def test_trend_predicts_after_three_points(seeded_exam_api, student_a_exam_api,
                                           student_a_attempt_api, seeded_grading_api,
                                           student_a_client, fx):
    """3 次已出分作答后给出趋势预测：方向在枚举内、预测值非空。"""
    eid = _published_exam(seeded_exam_api, fx, "trend", show_score_immediately=True)
    for _ in range(3):
        started = student_a_exam_api.start(eid)
        CommonAssert.assert_ok(started)
        aid = started.data["attempt"]["id"]
        pq = fx["paper_questions"][str(fx["questions"]["single"])]
        CommonAssert.assert_ok(student_a_attempt_api.save_answers(
            aid, [{"paper_question_id": pq, "selected_labels": fx["answers"]["single"]}],
        ))
        CommonAssert.assert_ok(student_a_attempt_api.submit(aid))
        CommonAssert.assert_ok(seeded_grading_api.grade(aid))
        CommonAssert.assert_ok(seeded_grading_api.finalize(aid))

    resp = AnalyticsApi(student_a_client).trend(fx["students"]["a"]["id"])
    CommonAssert.assert_ok(resp)
    assert len(resp.data["points"]) >= 3
    fit = resp.data["fit"]
    assert fit["enough_points"] is True
    assert fit["direction"] in ("up", "down", "flat")
    assert fit["predict_next"] is not None
    assert resp.data["summary"]["predict_percent"] is not None


# ======================================================================
# 四、监考：可疑过滤（PRO-04）
# ======================================================================
def _suspicious_exam(seeded_exam_api, student_a_exam_api, student_a_attempt_api,
                     student_b_exam_api, fx) -> int:
    """造两类考生：A 高风险（密集切屏+粘贴+退全屏），B 正常（无埋点）。

    必须有正常行才能验证 only_suspicious 的过滤效果，否则是空转。
    """
    eid = _published_exam(
        seeded_exam_api, fx, "risk", max_switch_count=99,
        participant_ids=[fx["students"]["a"]["id"], fx["students"]["b"]["id"]],
    )
    started = student_a_exam_api.start(eid)
    CommonAssert.assert_ok(started)
    aid = started.data["attempt"]["id"]
    for event_type, count in (("switch", 10), ("paste", 5), ("fullscreen_exit", 3)):
        CommonAssert.assert_ok(student_a_attempt_api.behavior(aid, [{"type": event_type, "count": count}]))
    CommonAssert.assert_ok(student_b_exam_api.start(eid))
    return eid


def test_proctoring_only_suspicious_filter(seeded_exam_api, student_a_exam_api,
                                           student_a_attempt_api, student_b_exam_api,
                                           seeded_teacher_client, fx):
    """only_suspicious=true 只返回可疑行，且 overview 的统计不被过滤影响。"""
    eid = _suspicious_exam(seeded_exam_api, student_a_exam_api, student_a_attempt_api,
                           student_b_exam_api, fx)
    api = ProctoringApi(seeded_teacher_client)

    full = api.report(eid)
    CommonAssert.assert_ok(full)
    assert full.data["overview"]["suspicious_count"] >= 1, "构造的高风险考生应被标记"
    assert any(row["is_suspicious"] for row in full.data["rows"])

    filtered = api.report(eid, only_suspicious=True)
    CommonAssert.assert_ok(filtered)
    assert all(row["is_suspicious"] for row in filtered.data["rows"])
    assert len(filtered.data["rows"]) < len(full.data["rows"])
    assert filtered.data["overview"] == full.data["overview"], "overview 不应被行过滤改变"


def test_proctoring_risk_signals_explainable(seeded_exam_api, student_a_exam_api,
                                             student_a_attempt_api, student_b_exam_api,
                                             seeded_teacher_client, fx):
    """风险分必须可解释：命中规则有中文名与原因，不是黑盒数字。"""
    eid = _suspicious_exam(seeded_exam_api, student_a_exam_api, student_a_attempt_api,
                           student_b_exam_api, fx)
    resp = ProctoringApi(seeded_teacher_client).report(eid)
    CommonAssert.assert_ok(resp)
    row = next(r for r in resp.data["rows"] if r["is_suspicious"])
    assert row["risk_score"] > 0
    assert row["signal_names"] and row["reasons"]
    assert row["risk_level"] in ("normal", "low", "medium", "high", "severe")


# ======================================================================
# 五、班级：表单校验（CLS-03 / 04 / 06 / 08 / 09）
# ======================================================================
@pytest.fixture(scope="module")
def admin_classroom(seeded_teacher_client, fx):
    api = ClassroomApi(seeded_teacher_client)
    created = api.create(name=f"{fx['prefix']}_B11_行政班", grade_year="2026", class_type="admin")
    CommonAssert.assert_ok(created, 201)
    return created.data["id"]


def test_admin_class_cannot_link_admin_class(seeded_teacher_client, admin_classroom, fx):
    """行政班不能挂靠另一个行政班 → 400，且指明 admin_class_id 字段。"""
    api = ClassroomApi(seeded_teacher_client)
    resp = api.create(name=f"{fx['prefix']}_B11_错挂", class_type="admin",
                      admin_class_id=admin_classroom)
    CommonAssert.assert_error(resp, 400, 40000)
    assert "admin_class_id" in (resp.data or {})


def test_classroom_blank_name_rejected(seeded_teacher_client, fx):
    """班级名称为空白 → 400。"""
    api = ClassroomApi(seeded_teacher_client)
    resp = api.create(name="   ", class_type="admin")
    CommonAssert.assert_error(resp, 400)


def test_add_students_requires_one_mode(seeded_teacher_client, admin_classroom):
    """三种加人方式都不传 → 400 并列出可选参数。"""
    api = ClassroomApi(seeded_teacher_client)
    resp = api.add_students(admin_classroom)
    CommonAssert.assert_error(resp, 400)
    assert "from_classroom_id" in resp.message or "student" in resp.message


def test_add_students_by_student_no_reports_missing(seeded_teacher_client, admin_classroom, fx):
    """按学号加人：有效学号入班，无效学号进 missing，不整批失败。"""
    api = ClassroomApi(seeded_teacher_client)
    resp = api.add_students(admin_classroom, student_nos=[
        fx["students"]["b"]["student_no"], "NOT_EXIST_9527",
    ])
    CommonAssert.assert_ok(resp)
    assert fx["students"]["b"]["student_no"] in resp.data["added"]
    assert "NOT_EXIST_9527" in resp.data["missing"]


def test_subject_class_cannot_import_from_subject_class(seeded_teacher_client, admin_classroom, fx):
    """学科班整班导入只能来自行政班：从学科班导入 → 400。"""
    api = ClassroomApi(seeded_teacher_client)
    subject_class = api.create(
        name=f"{fx['prefix']}_B11_学科班", class_type="subject",
        subject=fx["subject"], admin_class_id=admin_classroom,
    )
    CommonAssert.assert_ok(subject_class, 201)
    cid = subject_class.data["id"]
    resp = api.add_students(cid, from_classroom_id=cid)
    CommonAssert.assert_error(resp, 400, message="行政班")
