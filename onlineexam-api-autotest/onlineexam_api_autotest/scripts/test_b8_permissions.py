# -*- coding: utf-8 -*-
"""B8 权限横切：按"资源 × 角色"抽查 403 / 200，防权限改动回归。

不重复契约矩阵的 661 条断言，只保留业务分组代表接口。
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.l4


@pytest.fixture(scope="module")
def role_clients(student_client, teacher_client, admin_client):
    return {"student": student_client, "teacher": teacher_client, "admin": admin_client}


CASES = [
    # 学生：配置类与治理类一律 403
    ("student", "/api/v1/users/", 403),
    ("student", "/api/v1/questions/", 403),
    ("student", "/api/v1/papers/", 403),
    ("student", "/api/v1/knowledge-points/", 403),
    ("student", "/api/v1/proctoring/exams/", 403),
    ("student", "/api/v1/grading/queue/", 403),
    ("student", "/api/v1/grading/scoreboard/", 403),
    ("student", "/api/v1/ai/providers/", 403),
    ("student", "/api/v1/system/overview/", 403),
    ("student", "/api/v1/exams/candidates/", 403),
    # 学生：自己的业务只读接口可用
    ("student", "/api/v1/exams/", 200),
    ("student", "/api/v1/attempts/", 200),
    ("student", "/api/v1/classrooms/", 200),
    # 教师：内容与教学可用，治理类 403
    ("teacher", "/api/v1/questions/", 200),
    ("teacher", "/api/v1/papers/", 200),
    ("teacher", "/api/v1/proctoring/rules/", 200),
    ("teacher", "/api/v1/ai/providers/", 200),
    ("teacher", "/api/v1/users/", 403),
    ("teacher", "/api/v1/system/overview/", 403),
    # 管理员：治理类可用
    ("admin", "/api/v1/users/", 200),
    ("admin", "/api/v1/system/overview/", 200),
]


@pytest.mark.parametrize("role,path,expected", CASES)
def test_permission_matrix(role_clients, role, path, expected):
    resp = role_clients[role].get(path)
    assert resp.status == expected, f"{role} {path} -> {resp.status} {resp.code} {resp.message}"
    if expected == 403:
        assert resp.code == 40300
    else:
        assert resp.code == 0


@pytest.mark.parametrize("role,path", [
    ("student", "/api/v1/questions/"),
    ("student", "/api/v1/papers/"),
    ("student", "/api/v1/exams/"),
])
def test_student_write_forbidden(role_clients, role, path):
    resp = role_clients[role].post(path, json={})
    assert resp.status in (403, 405), f"{role} POST {path} 未被拦截：{resp.status}"
    assert resp.status != 500
