# -*- coding: utf-8 -*-
"""B5 判分与成绩：客观判分、AI 批改、多选策略、复核审计、出分护栏、成绩单与统计。"""
from __future__ import annotations

import pytest

from common.assert_tools import CommonAssert
from common.fixtures import paper_question_id

pytestmark = pytest.mark.l1


def make_attempt(exam_api, attempt_api, fx, answers: dict) -> int:
    """按 {题目key: {selected_labels/answer_text}} 作答并交卷，返回 attempt_id。"""
    start = exam_api.start(fx["exams"]["normal"])
    assert start.code == 0, f"开考失败：{start.brief()}"
    aid = start.data["attempt"]["id"]
    for key, payload in answers.items():
        resp = attempt_api.save(aid, paper_question_id=paper_question_id(fx, key), **payload)
        assert resp.code == 0, f"暂存 {key} 失败：{resp.brief()}"
    submit = attempt_api.submit(aid, reason="manual")
    assert submit.code == 0, f"交卷失败：{submit.brief()}"
    return aid


@pytest.fixture(scope="module")
def single_attempt(fx, student_a_exam_api, student_a_attempt_api):
    return make_attempt(
        student_a_exam_api, student_a_attempt_api, fx,
        {"single": {"selected_labels": "A"}},
    )


@pytest.fixture(scope="module")
def subjective_attempt(fx, student_a_exam_api, student_a_attempt_api):
    return make_attempt(
        student_a_exam_api, student_a_attempt_api, fx,
        {"short": {"answer_text": "进程是资源分配单位，线程是调度单位。"}},
    )


def test_grade_objective_only(single_attempt, seeded_grading_api):
    resp = seeded_grading_api.grade(single_attempt)
    CommonAssert.assert_ok(resp)
    assert float(resp.data["summary"]["objective_score"]) == 2.0
    assert float(resp.data["summary"]["subjective_score"]) == 0.0
    assert resp.data["status"] != "graded"


def test_grade_single_wrong_gets_zero(fx, student_a_exam_api, student_a_attempt_api,
                                      seeded_grading_api):
    aid = make_attempt(student_a_exam_api, student_a_attempt_api, fx,
                       {"single": {"selected_labels": "B"}})
    resp = seeded_grading_api.grade(aid)
    CommonAssert.assert_ok(resp)
    assert float(resp.data["summary"]["objective_score"]) == 0.0


def test_grade_multiple_penalty_with_wrong_choice(
        fx, student_a_exam_api, student_a_attempt_api, seeded_grading_api):
    """答案 ABC，作答 ABD：净得分 2-1=1，4×1/3≈1.33。"""
    aid = make_attempt(student_a_exam_api, student_a_attempt_api, fx,
                       {"multiple": {"selected_labels": "ABD"}})
    resp = seeded_grading_api.grade(aid, policy="penalty")
    CommonAssert.assert_ok(resp)
    assert float(resp.data["summary"]["objective_score"]) == 1.33


def test_grade_fill_partial(fx, student_a_exam_api, student_a_attempt_api,
                            seeded_grading_api):
    """填空两空只答对一空 → 一半分。"""
    aid = make_attempt(student_a_exam_api, student_a_attempt_api, fx,
                       {"fill": {"answer_text": "后进先出\n错误答案"}})
    resp = seeded_grading_api.grade(aid)
    CommonAssert.assert_ok(resp)
    assert float(resp.data["summary"]["objective_score"]) == 2.0


def test_grade_with_ai_mock(subjective_attempt, seeded_grading_api):
    resp = seeded_grading_api.grade(subjective_attempt, with_ai=True, provider="mock")
    CommonAssert.assert_ok(resp)
    subjective = resp.data.get("subjective") or {}
    assert subjective.get("graded", 0) >= 1 or subjective.get("degraded") is True


def test_repeat_grade_idempotent(single_attempt, seeded_grading_api):
    first = seeded_grading_api.grade(single_attempt)
    second = seeded_grading_api.grade(single_attempt, force=True)
    CommonAssert.assert_ok(first)
    CommonAssert.assert_ok(second)
    assert float(first.data["summary"]["objective_score"]) == \
        float(second.data["summary"]["objective_score"])


def test_review_writes_feedback(subjective_attempt, student_a_attempt_api,
                                seeded_grading_api):
    seeded_grading_api.grade(subjective_attempt, with_ai=True, provider="mock")
    rows = student_a_attempt_api.answers(subjective_attempt).data["results"]
    target = next(r for r in rows if r.get("answer_text"))
    resp = seeded_grading_api.review(target["id"], score=8, comment="at_B5 复核")
    CommonAssert.assert_ok(resp)
    assert float(resp.data["answer"]["score"]) == 8.0
    assert resp.data["feedback"]["id"]



def test_review_score_out_of_range(subjective_attempt, student_a_attempt_api,
                                   seeded_grading_api):
    rows = student_a_attempt_api.answers(subjective_attempt).data["results"]
    target = next(r for r in rows if r.get("answer_text"))
    resp = seeded_grading_api.review(target["id"], score=999)
    CommonAssert.assert_error(resp, 400)


def test_finalize_in_progress_rejected(fx, student_a_exam_api, seeded_grading_api):
    start = student_a_exam_api.start(fx["exams"]["normal"])
    CommonAssert.assert_ok(start)
    aid = start.data["attempt"]["id"]
    resp = seeded_grading_api.finalize(aid)
    CommonAssert.assert_error(resp, 400)


def test_scoreboard(seeded_grading_api, fx):
    resp = seeded_grading_api.scoreboard(exam_id=fx["exams"]["normal"])
    CommonAssert.assert_ok(resp)
    assert "results" in resp.data
    assert 0 <= float(resp.data.get("pass_rate", 0)) <= 1


def test_wrong_book_student_scope(student_a_grading_api):
    resp = student_a_grading_api.wrong_book()
    CommonAssert.assert_ok(resp)
    assert resp.data["student"]["id"]


def test_calibration(seeded_grading_api):
    resp = seeded_grading_api.calibration()
    CommonAssert.assert_ok(resp)
    assert resp.data


def test_queue_requires_exam(seeded_grading_api, fx):
    CommonAssert.assert_error(seeded_grading_api.queue(), 400)
    ok = seeded_grading_api.queue(exam_id=fx["exams"]["normal"])
    CommonAssert.assert_ok(ok)
    assert "results" in ok.data


def test_feedback_list_filter(seeded_grading_api, subjective_attempt):
    resp = seeded_grading_api.feedback_list(attempt_id=subjective_attempt)
    CommonAssert.assert_ok(resp)
    assert resp.data["count"] >= 1
