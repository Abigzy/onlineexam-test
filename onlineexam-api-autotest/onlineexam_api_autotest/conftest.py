# -*- coding: utf-8 -*-
"""pytest 公共 fixture：匿名/各角色客户端 + 常用 ID。

注意：token 按 session 缓存，整个测试会话每个账号只登录一次，
避免撞上 auth 限流（30/min）。
"""
from __future__ import annotations

import pytest

from common.auth import TokenPool
from common.client import ApiClient
from encap_api.admin_api import AiApi, ClassroomApi, SystemApi
from encap_api.auth_user_api import AuthApi, UserApi
from encap_api.content_api import KnowledgeApi, PaperApi, QuestionApi
from encap_api.exam_api import AttemptApi, ExamApi
from encap_api.grading_api import GradingApi
from encap_api.insight_api import AnalyticsApi, ProctoringApi, RecommendApi


@pytest.fixture(scope="session")
def pool() -> TokenPool:
    return TokenPool()


@pytest.fixture(scope="session")
def anon() -> ApiClient:
    return ApiClient(label="anon")


@pytest.fixture(scope="session")
def admin_client(pool):
    return pool.get("admin")


@pytest.fixture(scope="session")
def teacher_client(pool):
    return pool.get("teacher")


@pytest.fixture(scope="session")
def os_teacher_client(pool):
    return pool.get("os_teacher")


@pytest.fixture(scope="session")
def student_client(pool):
    return pool.get("student")


@pytest.fixture(scope="session")
def student2_client(pool):
    return pool.get("student2")


# ---------------- 接口对象 ----------------
@pytest.fixture(scope="session")
def auth_api(anon):
    return AuthApi(anon)


@pytest.fixture(scope="session")
def admin_user_api(admin_client):
    return UserApi(admin_client)


@pytest.fixture(scope="session")
def teacher_user_api(teacher_client):
    return UserApi(teacher_client)


@pytest.fixture(scope="session")
def student_auth_api(student_client):
    return AuthApi(student_client)


@pytest.fixture(scope="session")
def knowledge_api(teacher_client):
    return KnowledgeApi(teacher_client)


@pytest.fixture(scope="session")
def question_api(teacher_client):
    return QuestionApi(teacher_client)


@pytest.fixture(scope="session")
def paper_api(teacher_client):
    return PaperApi(teacher_client)


@pytest.fixture(scope="session")
def exam_api(teacher_client):
    return ExamApi(teacher_client)


@pytest.fixture(scope="session")
def student_exam_api(student_client):
    return ExamApi(student_client)


@pytest.fixture(scope="session")
def attempt_api(student_client):
    return AttemptApi(student_client)


@pytest.fixture(scope="session")
def grading_api(teacher_client):
    return GradingApi(teacher_client)


@pytest.fixture(scope="session")
def analytics_api(teacher_client):
    return AnalyticsApi(teacher_client)


@pytest.fixture(scope="session")
def student_analytics_api(student_client):
    return AnalyticsApi(student_client)


@pytest.fixture(scope="session")
def recommend_api(student_client):
    return RecommendApi(student_client)


@pytest.fixture(scope="session")
def proctoring_api(teacher_client):
    return ProctoringApi(teacher_client)


@pytest.fixture(scope="session")
def classroom_api(teacher_client):
    return ClassroomApi(teacher_client)


@pytest.fixture(scope="session")
def ai_api(teacher_client):
    return AiApi(teacher_client)


@pytest.fixture(scope="session")
def system_api(admin_client):
    return SystemApi(admin_client)


# ---------------- 常用 ID ----------------
@pytest.fixture(scope="session")
def student_id(student_auth_api) -> int:
    resp = student_auth_api.me()
    assert resp.code == 0, f"取学生信息失败：{resp.brief()}"
    return resp.data["id"]


@pytest.fixture(scope="session")
def student2_id(admin_user_api) -> int:
    resp = admin_user_api.list(search="s_002")
    assert resp.code == 0 and resp.data["count"] >= 1, f"找不到学生 s_002：{resp.brief()}"
    return resp.data["results"][0]["id"]


@pytest.fixture(scope="session")
def visible_exam_id(student_exam_api) -> int:
    """学生可见的已发布考试；没有就跳过依赖它的用例（不算失败）。"""
    resp = student_exam_api.list(page_size=10)
    assert resp.code == 0, f"学生考试列表失败：{resp.brief()}"
    rows = resp.data["results"]
    if not rows:
        pytest.skip("演示数据中没有学生可见的考试，跳过依赖用例")
    return rows[0]["id"]


# ---------------- 造数 fixtures（scripts/seed_env.py 产出） ----------------
@pytest.fixture(scope="session")
def fx():
    from common.fixtures import load_fixtures

    try:
        return load_fixtures()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))


def _login_as(username: str, password: str, label: str) -> ApiClient:
    """登录（走 token 缓存，避免 30/min 限流）。"""
    from common.auth import login_user

    return login_user(username, password, label=label)


@pytest.fixture(scope="session")
def student_a_client(fx):
    acc = fx["students"]["a"]
    return _login_as(acc["username"], acc["password"], "student_a")


@pytest.fixture(scope="session")
def student_b_client(fx):
    acc = fx["students"]["b"]
    return _login_as(acc["username"], acc["password"], "student_b")


@pytest.fixture(scope="session")
def student_a_exam_api(student_a_client):
    return ExamApi(student_a_client)


@pytest.fixture(scope="session")
def student_a_attempt_api(student_a_client):
    return AttemptApi(student_a_client)


@pytest.fixture(scope="session")
def student_a_grading_api(student_a_client):
    return GradingApi(student_a_client)


@pytest.fixture(scope="session")
def seeded_teacher_client(fx):
    acc = fx["teacher"]
    return _login_as(acc["username"], acc["password"], "seeded_teacher")


@pytest.fixture(scope="session")
def seeded_paper_api(seeded_teacher_client):
    return PaperApi(seeded_teacher_client)


@pytest.fixture(scope="session")
def seeded_knowledge_api(seeded_teacher_client):
    return KnowledgeApi(seeded_teacher_client)


@pytest.fixture(scope="session")
def seeded_exam_api(seeded_teacher_client):
    return ExamApi(seeded_teacher_client)


@pytest.fixture(scope="session")
def seeded_grading_api(seeded_teacher_client):
    return GradingApi(seeded_teacher_client)


@pytest.fixture(scope="session")
def seeded_question_api(seeded_teacher_client):
    return QuestionApi(seeded_teacher_client)


@pytest.fixture(scope="session")
def student_a_id(fx):
    return fx["students"]["a"]["id"]


@pytest.fixture(scope="session")
def student_b_exam_api(student_b_client):
    return ExamApi(student_b_client)


@pytest.fixture(scope="session")
def student_b_attempt_api(student_b_client):
    return AttemptApi(student_b_client)
