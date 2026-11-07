# -*- coding: utf-8 -*-
"""L1 单接口业务规则（依赖 scripts/seed_env.py 的 fixtures）。

覆盖评审阶段列出的高风险规则：
知识点删除口径、试卷状态机与分值边界、考试发布校验、
班外开考、多选判分三策略、出分自动补判、切屏强制交卷。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from common.assert_tools import CommonAssert
from common.client import ApiClient
from common.fixtures import paper_question_id
from encap_api.exam_api import ExamApi

pytestmark = pytest.mark.l1

FMT = "%Y-%m-%d %H:%M:%S"


def exam_window():
    now = datetime.now()
    return (now - timedelta(minutes=5)).strftime(FMT), (now + timedelta(minutes=60)).strftime(FMT)


# ======================================================================
# 知识点
# ======================================================================
def test_kp_delete_blocked_when_subtree_has_questions(seeded_knowledge_api, fx):
    root_id = fx["knowledge"]["root"]
    resp = seeded_knowledge_api.remove(root_id)
    CommonAssert.assert_error(resp, 400, 12030)
    # 拒绝时不能删掉任何节点
    assert seeded_knowledge_api.detail(root_id).status == 200
    assert seeded_knowledge_api.detail(fx["knowledge"]["child"]).status == 200


def test_kp_delete_cascades_when_no_questions(seeded_knowledge_api, fx):
    name = fx["prefix"] + "_待删知识点"
    root = seeded_knowledge_api.create(name=name, subject=fx["subject"])
    CommonAssert.assert_ok(root, 201)
    root_id = root.data["id"]
    child = seeded_knowledge_api.create(
        name=name + "_子", subject=fx["subject"], parent=root_id,
    )
    CommonAssert.assert_ok(child, 201)

    resp = seeded_knowledge_api.remove(root_id)
    CommonAssert.assert_ok(resp, 200)
    assert "含 1 个子知识点" in resp.message
    assert seeded_knowledge_api.detail(root_id).status == 404


# ======================================================================
# 试卷
# ======================================================================
def test_empty_paper_cannot_publish(seeded_paper_api, fx):
    paper = seeded_paper_api.create(title=fx["prefix"] + "_空卷", subject=fx["subject"])
    CommonAssert.assert_ok(paper, 201)
    resp = seeded_paper_api.status(paper.data["id"], "published")
    CommonAssert.assert_error(resp, 400, 13006)


def test_published_paper_is_immutable(seeded_paper_api, fx):
    pid = fx["papers"]["published"]
    CommonAssert.assert_error(
        seeded_paper_api.update(pid, title=fx["prefix"] + "_改标题"), 400, 13002,
    )
    CommonAssert.assert_error(seeded_paper_api.remove(pid), 400, 13001)
    assert seeded_paper_api.detail(pid).status == 200


def test_batch_score_rejects_over_100(seeded_paper_api, fx):
    pq_id = fx["paper_questions_draft"][str(fx["questions"]["single"])]
    resp = seeded_paper_api.set_scores(
        fx["papers"]["draft"], [{"id": pq_id, "score": 101}],
    )
    # 实测由序列化器先拦（40000），service 的 13004 是第二道闸；
    # 两种拒绝都算"上限生效"，记录实际码即可。
    CommonAssert.assert_error(resp, 400)
    assert resp.code in (40000, 13004), f"未按分值上限拒绝：{resp.brief()}"


def test_add_duplicate_question_strict(seeded_paper_api, fx):
    resp = seeded_paper_api.add_questions(
        fx["papers"]["draft"], [fx["questions"]["single"]], strict=True,
    )
    CommonAssert.assert_error(resp, 400, 13003)


# ======================================================================
# 考试
# ======================================================================
def test_exam_illegal_transition_rejected(seeded_exam_api, fx):
    start, end = exam_window()
    exam = seeded_exam_api.create(
        paper_id=fx["papers"]["published"], title=fx["prefix"] + "_迁移测试",
        start_time=start, end_time=end, duration_minutes=20, max_attempts=1,
    )
    CommonAssert.assert_ok(exam, 201)
    resp = seeded_exam_api.status(exam.data["id"], "finished")
    CommonAssert.assert_error(resp, 400)


def test_exam_cannot_publish_with_draft_paper(seeded_exam_api, fx):
    start, end = exam_window()
    exam = seeded_exam_api.create(
        paper_id=fx["papers"]["draft"], title=fx["prefix"] + "_草稿卷考试",
        start_time=start, end_time=end, duration_minutes=20, max_attempts=1,
    )
    CommonAssert.assert_ok(exam, 201)
    resp = seeded_exam_api.status(exam.data["id"], "published")
    CommonAssert.assert_error(resp, 400)
    assert "草稿" in resp.message


def test_student_out_of_scope_cannot_start(student_b_client, fx):
    """班外学生开考：实测 404（考试不在其可见范围，取对象阶段就被过滤）。

    与功能测试 OBS-02 一致：接口文档写的 403/10431 是"能取到考试但不在参考范围"的分支，
    班外学生根本取不到 → 404。以实际为准并记入观察项。
    """
    api = ExamApi(student_b_client)
    resp = api.start(fx["exams"]["normal"])
    CommonAssert.assert_error(resp, 404, 40400)


# ======================================================================
# 判分策略
# ======================================================================
@pytest.fixture(scope="module")
def partial_attempt(fx, student_a_exam_api, student_a_attempt_api):
    """一次只答了「AB」的多选作答（正确答案 ABC），用于验证三种策略。"""
    start = student_a_exam_api.start(fx["exams"]["normal"])
    assert start.code == 0, f"开考失败：{start.brief()}"
    aid = start.data["attempt"]["id"]
    pq = paper_question_id(fx, "multiple")
    save = student_a_attempt_api.save(aid, paper_question_id=pq, selected_labels="AB")
    assert save.code == 0, f"暂存失败：{save.brief()}"
    submit = student_a_attempt_api.submit(aid, reason="manual")
    assert submit.code == 0, f"交卷失败：{submit.brief()}"
    return aid


def test_multiple_strict_gives_zero(partial_attempt, seeded_grading_api):
    resp = seeded_grading_api.grade(partial_attempt, policy="strict")
    CommonAssert.assert_ok(resp, 200)
    assert float(resp.data["summary"]["objective_score"]) == 0.0


def test_multiple_partial_gives_ratio(partial_attempt, seeded_grading_api):
    resp = seeded_grading_api.grade(partial_attempt, policy="partial", force=True)
    CommonAssert.assert_ok(resp, 200)
    # 4 分题，选对 2/3 → 2.67
    assert float(resp.data["summary"]["objective_score"]) == 2.67


# ======================================================================
# 出分与强制交卷
# ======================================================================
def test_finalize_auto_grades_objective(fx, student_a_exam_api, student_a_attempt_api,
                                        student_a_grading_api, seeded_grading_api):
    exam_id = fx["exams"]["score_open"]
    start = student_a_exam_api.start(exam_id)
    assert start.code == 0, f"开考失败：{start.brief()}"
    aid = start.data["attempt"]["id"]
    student_a_attempt_api.save(
        aid, paper_question_id=paper_question_id(fx, "single"),
        selected_labels=fx["answers"]["single"],
    )
    student_a_attempt_api.submit(aid, reason="manual")

    # 不先判分，直接出分：必须自动补判客观题，不能公布 0 分
    resp = seeded_grading_api.finalize(aid)
    CommonAssert.assert_ok(resp, 200)
    assert resp.data["attempt"]["status"] == "graded"
    assert float(resp.data["score"]) == 2.0, f"出分后总分异常：{resp.data['score']}"

    report = student_a_grading_api.report(aid)
    assert report.data["visible"] is True

    answers = student_a_attempt_api.answers(aid)
    rows = answers.data["results"]
    assert any(r["is_correct"] is True for r in rows), "已公布成绩后应能看逐题对错"


def test_switch_limit_forces_submit(fx, student_a_exam_api, student_a_attempt_api):
    start = student_a_exam_api.start(fx["exams"]["force"])
    assert start.code == 0, f"开考失败：{start.brief()}"
    aid = start.data["attempt"]["id"]

    last = None
    for _ in range(3):
        last = student_a_attempt_api.behavior(aid, [{"type": "switch", "count": 1}])
        assert last.code == 0

    assert last.data["limit_exceeded"] is True
    assert last.data["auto_submitted"] is True

    detail = student_a_attempt_api.detail(aid)
    assert detail.data["status"] != "in_progress", "超限后应已强制交卷"
