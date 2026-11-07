# -*- coding: utf-8 -*-
"""L0-B 业务链路冒烟 + 关键安全断言（依赖 scripts/seed_env.py 的 fixtures）。

覆盖：开考 → 卷面 → 暂存 → 心跳 → 行为上报 → 交卷 → 判分 → 出分。
一条链路只跑一次，各断言分散到独立用例，失败时能直接看出断在哪一步。
"""
from __future__ import annotations

import pytest

from common.assertor import assert_no_answer_fields, assert_score_fields_blank
from common.fixtures import paper_question_id

pytestmark = [pytest.mark.l0, pytest.mark.l2]


@pytest.fixture(scope="module")
def chain(fx, student_a_exam_api, student_a_attempt_api,
          student_a_grading_api, grading_api):
    exam_id = fx["exams"]["normal"]
    start = student_a_exam_api.start(exam_id)
    assert start.status == 200 and start.code == 0, f"开考失败：{start.brief()}"
    attempt_id = start.data["attempt"]["id"]

    paper = student_a_attempt_api.paper(attempt_id)
    single_pq = paper_question_id(fx, "single")
    save = student_a_attempt_api.save(
        attempt_id, paper_question_id=single_pq, selected_labels=fx["answers"]["single"],
    )
    answers_before = student_a_attempt_api.answers(attempt_id)
    heartbeat = student_a_attempt_api.heartbeat(attempt_id, client_remaining=99999)
    behavior = student_a_attempt_api.behavior(
        attempt_id, [{"type": "switch", "count": 1}],
    )
    submit = student_a_attempt_api.submit(attempt_id, reason="manual")
    answers_submitted = student_a_attempt_api.answers(attempt_id)
    grade = grading_api.grade(attempt_id, policy="strict")
    answers_graded = student_a_attempt_api.answers(attempt_id)
    finalize = grading_api.finalize(attempt_id)
    answers_finalized = student_a_attempt_api.answers(attempt_id)
    report = student_a_grading_api.report(attempt_id)

    return {
        "exam_id": exam_id, "attempt_id": attempt_id,
        "start": start, "paper": paper, "save": save,
        "answers_before": answers_before, "heartbeat": heartbeat,
        "behavior": behavior, "submit": submit,
        "answers_submitted": answers_submitted, "grade": grade,
        "answers_graded": answers_graded, "finalize": finalize,
        "answers_finalized": answers_finalized,
        "report": report, "single_pq": single_pq,
    }


def test_start_returns_attempt_and_paper(chain, fx):
    data = chain["start"].data
    assert data["attempt"]["id"] == chain["attempt_id"]
    assert len(data["questions"]) == 6, f"卷面题数不符：{len(data['questions'])}"
    assert data["remaining_seconds"] <= 20 * 60
    assert data["config"]["show_score_immediately"] is False


def test_start_payload_has_no_answers(chain):
    assert_no_answer_fields(chain["start"].body)


def test_paper_resume_has_no_answers(chain):
    assert chain["paper"].status == 200
    assert_no_answer_fields(chain["paper"].body)
    assert len(chain["paper"].data["questions"]) == 6


def test_save_answer_persisted(chain, fx):
    assert chain["save"].status == 200 and chain["save"].code == 0
    rows = chain["answers_before"].data["results"]
    target = [r for r in rows if r["paper_question_id"] == chain["single_pq"]]
    assert target and target[0]["is_answered"] is True
    assert target[0]["selected_labels"] == fx["answers"]["single"]


def test_heartbeat_uses_server_time(chain):
    data = chain["heartbeat"].data
    assert 0 <= data["remaining_seconds"] <= 20 * 60
    assert data["clock_drift_seconds"] and data["clock_drift_seconds"] > 0
    assert data["should_submit"] is False


def test_behavior_counted(chain):
    data = chain["behavior"].data
    assert data["switch_count"] >= 1


def test_submit_marks_submitted(chain):
    data = chain["submit"].data
    assert data["status"] == "submitted"
    assert data["answered_count"] >= 1


def test_grade_objective_only(chain):
    summary = chain["grade"].data["summary"]
    assert float(summary["objective_score"]) == 2.0, f"客观分不符：{summary}"
    assert float(summary["subjective_score"]) == 0.0


def test_score_hidden_before_publish(chain):
    """E1 未开启「立即公布」：判分后学生仍看不到逐题对错与得分。"""
    assert chain["answers_graded"].status == 200
    assert_score_fields_blank(chain["answers_graded"].data["results"])


def test_finalize_marks_graded(chain):
    assert chain["finalize"].status == 200
    assert chain["finalize"].code == 0
    assert chain["finalize"].data["attempt"]["status"] == "graded"


def test_report_and_answers_visibility_consistent(chain):
    """BUG-01 回归：同一份作答，成绩单与作答明细的可见性必须一致。

    修复后口径统一为 `ExamAttempt.score_visible()`：GRADED 恒可见。
    因此 finalize 后成绩单 visible=true，作答明细也应给出逐题对错与得分。
    """
    visible = chain["report"].data["visible"]
    rows = chain["answers_finalized"].data["results"]
    answered = [r for r in rows if r["is_answered"]]
    assert visible is True, "GRADED 后成绩单应可见"
    assert answered, "应至少有一道已作答题"
    assert all(r["is_correct"] is not None for r in answered), (
        f"成绩单已公开，作答明细仍隐藏对错：{[r['is_correct'] for r in answered]}"
    )
    assert float(chain["report"].data["score"]) == 2.0


def test_student_cannot_read_others_attempt(chain, student_b_client):
    resp = student_b_client.get(f"/api/v1/attempts/{chain['attempt_id']}/answers/")
    assert resp.status == 404 and resp.code == 40400, f"越权读取未被拦截：{resp.brief()}"

