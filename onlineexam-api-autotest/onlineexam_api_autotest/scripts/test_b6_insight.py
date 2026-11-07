# -*- coding: utf-8 -*-
"""B6 学情 / 推荐 / 监考 / 班级：结构与边界、缓存、确定性、越权与班级权限。"""
from __future__ import annotations

import pytest

from common.assert_tools import CommonAssert
from encap_api.admin_api import ClassroomApi
from encap_api.insight_api import ProctoringApi, RecommendApi

pytestmark = pytest.mark.l1


# ======================================================================
# 学情
# ======================================================================
def test_analytics_exam_list(analytics_api):
    resp = analytics_api.exams()
    CommonAssert.assert_ok(resp)
    assert "results" in resp.data


def test_analytics_exam_report(analytics_api, fx):
    resp = analytics_api.exam_report(fx["exams"]["normal"])
    CommonAssert.assert_ok(resp)
    assert resp.data


def test_analytics_classroom_id_invalid(analytics_api, fx):
    """非法 classroom_id：实测由 QuerySerializer 拦成 400/40000（不是 500，也不是文档写的 404）。"""
    resp = analytics_api.exam_report(fx["exams"]["normal"], classroom_id="abc")
    CommonAssert.assert_error(resp, 400, 40000)


def test_analytics_question_report(analytics_api, fx):
    resp = analytics_api.exam_questions(fx["exams"]["normal"])
    CommonAssert.assert_ok(resp)
    assert resp.data


def test_student_mastery_self(student_a_grading_api, student_a_id):
    from encap_api.insight_api import AnalyticsApi

    api = AnalyticsApi(student_a_grading_api.client)
    resp = api.mastery(student_a_id)
    CommonAssert.assert_ok(resp)
    assert "items" in resp.data


def test_student_trend_self(student_a_grading_api, student_a_id):
    from encap_api.insight_api import AnalyticsApi

    api = AnalyticsApi(student_a_grading_api.client)
    resp = api.trend(student_a_id)
    CommonAssert.assert_ok(resp)


def test_student_report_self(student_a_grading_api, student_a_id):
    from encap_api.insight_api import AnalyticsApi

    api = AnalyticsApi(student_a_grading_api.client)
    resp = api.report(student_a_id)
    CommonAssert.assert_ok(resp)


def test_diagnosis_cache(student_a_grading_api, student_a_id):
    from encap_api.insight_api import AnalyticsApi

    api = AnalyticsApi(student_a_grading_api.client)
    first = api.diagnosis(student_a_id, subject="操作系统", provider="mock")
    CommonAssert.assert_ok(first)
    second = api.diagnosis(student_a_id, subject="操作系统", provider="mock")
    CommonAssert.assert_ok(second)
    assert second.data.get("cached") is True
    forced = api.diagnosis(student_a_id, subject="操作系统", provider="mock", force=True)
    assert forced.data.get("cached") is False


# ======================================================================
# 推荐
# ======================================================================
def test_recommend_deterministic(student_a_client, student_a_id):
    api = RecommendApi(student_a_client)
    first = api.practice(student_a_id)
    second = api.practice(student_a_id)
    CommonAssert.assert_ok(first)
    CommonAssert.assert_ok(second)
    assert [i["question"]["id"] for i in first.data["items"]] == \
        [i["question"]["id"] for i in second.data["items"]]
    assert first.data["ai"] is None


def test_recommend_size_bound(student_a_client, student_a_id):
    api = RecommendApi(student_a_client)
    CommonAssert.assert_ok(api.practice(student_a_id, size=20))
    CommonAssert.assert_error(api.practice(student_a_id, size=21), 400)


def test_recommend_offset_changes_batch(student_a_client, student_a_id):
    api = RecommendApi(student_a_client)
    first = api.practice(student_a_id, size=3, offset=0)
    second = api.practice(student_a_id, size=3, offset=3)
    CommonAssert.assert_ok(first)
    CommonAssert.assert_ok(second)
    ids1 = [i["question"]["id"] for i in first.data["items"]]
    ids2 = [i["question"]["id"] for i in second.data["items"]]
    if len(ids1) == 3 and len(ids2) == 3:
        assert not set(ids1) & set(ids2)


def test_recommend_cold_start(student_b_client, fx):
    api = RecommendApi(student_b_client)
    resp = api.practice(fx["students"]["b"]["id"])
    CommonAssert.assert_ok(resp)
    assert isinstance(resp.data["items"], list)


# ======================================================================
# 监考
# ======================================================================
def test_proctoring_rules(proctoring_api):
    resp = proctoring_api.rules()
    CommonAssert.assert_ok(resp)
    rules = resp.data.get("rules") if isinstance(resp.data, dict) else resp.data
    assert len(rules) == 9


def test_proctoring_exams_and_report(proctoring_api, fx):
    CommonAssert.assert_ok(proctoring_api.exams())
    report = proctoring_api.report(fx["exams"]["normal"])
    CommonAssert.assert_ok(report)
    assert "rows" in report.data or "results" in report.data


def test_proctoring_top_n_invalid(proctoring_api, fx):
    resp = proctoring_api.report(fx["exams"]["normal"], top_n="abc")
    CommonAssert.assert_error(resp, 400)


def test_proctoring_evidence(student_a_attempt_api, proctoring_api):
    rows = student_a_attempt_api.list(page_size=1).data["results"]
    if not rows:
        pytest.skip("暂无作答")
    resp = proctoring_api.evidence(rows[0]["id"])
    CommonAssert.assert_ok(resp)


# ======================================================================
# 班级
# ======================================================================
@pytest.fixture(scope="module")
def classroom(seeded_teacher_client, fx):
    api = ClassroomApi(seeded_teacher_client)
    created = api.create(name=f"{fx['prefix']}_B6_班级", grade_year="2026",
                         class_type="admin")
    assert created.code == 0, f"建班失败：{created.brief()}"
    cid = created.data["id"]
    added = api.add_students(cid, student_ids=[fx["students"]["a"]["id"]])
    assert added.code == 0, f"加学生失败：{added.brief()}"
    return cid


def test_classroom_create_and_members(classroom, seeded_teacher_client, fx):
    api = ClassroomApi(seeded_teacher_client)
    members = api.members(classroom)
    CommonAssert.assert_ok(members)
    assert fx["students"]["a"]["id"] in [m["id"] for m in members.data["results"]]


def test_classroom_options(seeded_teacher_client):
    resp = ClassroomApi(seeded_teacher_client).options()
    CommonAssert.assert_ok(resp)
    assert "results" in resp.data


def test_classroom_non_owner_cannot_update(os_teacher_client, classroom):
    api = ClassroomApi(os_teacher_client)
    resp = api.update(classroom, name="at_hack")
    CommonAssert.assert_error(resp, 403, 14003)


def test_classroom_archive(seeded_teacher_client, fx):
    api = ClassroomApi(seeded_teacher_client)
    created = api.create(name=f"{fx['prefix']}_B6_待归档", class_type="admin")
    CommonAssert.assert_ok(created, 201)
    cid = created.data["id"]
    CommonAssert.assert_ok(api.remove(cid))
    default = api.list(page_size=50)
    assert cid not in [c["id"] for c in default.data["results"]]
    # 实测：归档后对外等同删除——默认列表不含，详情也是 404（DB 里只是 is_active=false）
    assert api.detail(cid).status == 404
