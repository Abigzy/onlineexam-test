# -*- coding: utf-8 -*-
"""L0 冒烟：环境可用性 + 主链路"能通" + 安全红线抽查。

特点：全部只读，不造数据、不改库，可在任意演示库上重复执行。
业务链路的冒烟（建卷→建考→作答→判分）在 L0-B，需先由 scripts/seed_env.py 造数。
"""
from __future__ import annotations

import pytest

from common import config
from common.assertor import (
    assert_no_answer_fields,
    assert_ok,
    assert_pagination_a,
    assert_pagination_b,
    assert_error,
)
from common.client import ApiClient
from encap_api.auth_user_api import AuthApi

pytestmark = pytest.mark.l0

ACCOUNT_ALIASES = ["admin", "teacher", "os_teacher", "student", "student2"]


# ======================================================================
# 1. 环境与统一契约
# ======================================================================
def test_health_public(anon):
    resp = anon.get("/api/health/")
    assert_ok(resp)
    assert resp.data["database"] == "up", f"数据库不可用：{resp.brief()}"
    assert resp.data["engine"] == "mysql", f"期望 mysql，实际 {resp.data.get('engine')}"


def test_requires_token(anon):
    resp = anon.get("/api/v1/questions/")
    assert_error(resp, 401, 40100)


def test_bad_token_rejected(anon):
    bad = ApiClient(token="abc.def.ghi", label="bad-token")
    resp = bad.get("/api/v1/auth/me/")
    assert_error(resp, 401, 40100)


def test_envelope_has_exactly_three_keys(student_auth_api):
    resp = student_auth_api.me()
    assert_ok(resp)
    assert set(resp.body) == {"code", "message", "data"}, f"信封字段异常：{resp.body.keys()}"
    assert resp.body["message"], "message 不应为空"


@pytest.mark.parametrize("alias", ACCOUNT_ALIASES)
def test_accounts_can_login(alias):
    """账号池可用性：登录成功且拿到 access / refresh / user。"""
    acc = config.account(alias)
    client = ApiClient(label=f"{alias}:check")
    resp = AuthApi(client).login(acc["username"], acc["password"])
    assert_ok(resp, 200)
    data = resp.data
    assert data.get("access") and data.get("refresh"), f"{alias} 未返回双 token"
    assert data["user"]["role"] == acc["role"], f"{alias} 角色不符：{data['user']['role']}"


# ======================================================================
# 2. 列表与分页（两种形态）
# ======================================================================
def test_users_pagination_shape_a(admin_user_api):
    resp = admin_user_api.list(page=1, page_size=2)
    assert_ok(resp)
    data = assert_pagination_a(resp, page_size=2)
    assert data["count"] >= 2, "演示库应至少有 2 个用户"


def test_classrooms_pagination_shape_b(classroom_api):
    resp = classroom_api.list()
    assert_ok(resp)
    assert_pagination_b(resp)


def test_questions_pagination(question_api):
    resp = question_api.list(page=1, page_size=5)
    assert_ok(resp)
    assert_pagination_a(resp, page_size=5)


def test_papers_pagination(paper_api):
    resp = paper_api.list(page=1, page_size=5)
    assert_ok(resp)
    assert_pagination_a(resp, page_size=5)


def test_attempts_pagination(attempt_api):
    resp = attempt_api.list(page=1, page_size=5)
    assert_ok(resp)
    assert_pagination_a(resp, page_size=5)


# ======================================================================
# 3. 角色边界（代表用例，不重复 661 条契约矩阵）
# ======================================================================
def test_teacher_cannot_manage_users(teacher_user_api):
    resp = teacher_user_api.list()
    assert_error(resp, 403, 40300)


def test_student_cannot_read_question_bank(student_client):
    """学生访问题库必须 403（答案防泄漏的第一道门）。"""
    resp = student_client.get("/api/v1/questions/")
    assert_error(resp, 403, 40300)


def test_student_cannot_read_proctoring(student_client):
    resp = student_client.get("/api/v1/proctoring/exams/")
    assert_error(resp, 403, 40300)


def test_teacher_can_read_proctoring_rules(proctoring_api):
    resp = proctoring_api.rules()
    assert_ok(resp)
    assert resp.data, "规则目录不应为空"


# ======================================================================
# 4. 考试与作答（只读）
# ======================================================================
def test_student_exam_list_only_published(student_exam_api):
    resp = student_exam_api.list(page_size=20)
    assert_ok(resp)
    data = assert_pagination_a(resp)
    bad = [row for row in data["results"] if row["status"] in ("draft", "archived")]
    assert not bad, f"学生看到了草稿/归档考试：{[r['id'] for r in bad]}"


def test_student_exam_detail_has_no_paper(student_exam_api, visible_exam_id):
    resp = student_exam_api.detail(visible_exam_id)
    assert_ok(resp)
    assert "paper" not in resp.data, "学生详情不应包含试卷内容"
    for key in ("questions", "sections"):
        assert key not in resp.data, f"学生详情不应包含 {key}"
    assert_no_answer_fields(resp.body)


def test_student_answers_no_answer_fields(attempt_api):
    listing = attempt_api.list(page_size=5)
    assert_ok(listing)
    rows = listing.data["results"]
    if not rows:
        pytest.skip("该学生暂无作答记录，跳过答案字段抽查")
    detail = attempt_api.answers(rows[0]["id"])
    assert_ok(detail)
    assert_no_answer_fields(detail.body)


def test_admin_sees_at_least_as_many_attempts(admin_client, attempt_api):
    student_resp = attempt_api.list(page_size=1)
    admin_resp = admin_client.get("/api/v1/attempts/?page_size=1")
    assert_ok(student_resp)
    assert_ok(admin_resp)
    assert admin_resp.data["count"] >= student_resp.data["count"], "教师/管理员应能看到全部作答"


# ======================================================================
# 5. 学情 / 推荐 / 判分的只读边界
# ======================================================================
def test_student_cannot_read_others_analytics(student_analytics_api, student2_id):
    resp = student_analytics_api.mastery(student2_id)
    assert_error(resp, 404, 40400)


def test_student_can_read_own_analytics(student_analytics_api, student_id):
    resp = student_analytics_api.report(student_id)
    assert_ok(resp)


def test_recommend_practice_readable(recommend_api, student_id):
    resp = recommend_api.practice(student_id)
    assert_ok(resp)
    assert "items" in resp.data and "summary" in resp.data, f"推荐返回结构异常：{resp.brief()}"
    assert resp.data.get("ai") is None, "GET 推荐不应调用大模型（ai 必须为 null）"


def test_wrong_book_teacher_requires_student(grading_api):
    resp = grading_api.wrong_book()
    assert_error(resp, 400)


def test_system_overview_admin_only(system_api, teacher_client):
    assert_ok(system_api.overview())
    resp = teacher_client.get("/api/v1/system/overview/")
    assert_error(resp, 403, 40300)
