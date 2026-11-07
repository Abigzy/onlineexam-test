# -*- coding: utf-8 -*-
"""B2 用户管理：建号、学号派发、角色变更、护栏、重置密码、列表过滤。"""
from __future__ import annotations

import time

import pytest

from common.assert_tools import CommonAssert

pytestmark = pytest.mark.l1

# 用户名/邮箱是唯一约束，数据不会随测试结束回滚。
# 加一个运行期后缀，保证同一套件可反复执行；同一 run 内同 key 仍相同，不影响「重名」用例。
RUN_TAG = str(time.time_ns() % 1000000)


def user_payload(fx, key, role="teacher", **over):
    payload = {
        "username": f"{fx['prefix']}_{key}_{RUN_TAG}",
        "password": "Exam@123456",
        "email": f"{fx['prefix']}_{key}_{RUN_TAG}@example.com",
        "real_name": f"自动化{key}",
        "role": role,
    }
    payload.update(over)
    return payload


def test_create_teacher_gets_employee_no(admin_user_api, fx):
    resp = admin_user_api.create(**user_payload(fx, "t1"))
    CommonAssert.assert_ok(resp, 201)
    assert resp.data["student_no"], "教师应自动派工号"


def test_create_student_requires_grade_year(admin_user_api, fx):
    resp = admin_user_api.create(**user_payload(fx, "s_nograde", role="student"))
    CommonAssert.assert_error(resp, 400, 10014)


def test_create_student_assigns_student_no(admin_user_api, fx):

    payload = user_payload(fx, "s1", role="student", grade_year="2026")
    resp = admin_user_api.create(**payload)
    CommonAssert.assert_ok(resp, 201)
    assert resp.data["student_no"].startswith("2026")


def test_create_student_no_mismatch_grade(admin_user_api, fx):
    payload = user_payload(fx, "s2", role="student", grade_year="2026",
                           student_no="2025001")
    resp = admin_user_api.create(**payload)
    CommonAssert.assert_error(resp, 400, 10015)


def test_create_user_short_password(admin_user_api, fx):
    resp = admin_user_api.create(**user_payload(fx, "t2", password="12345"))
    CommonAssert.assert_error(resp, 400, 10006)


def test_create_duplicate_username(admin_user_api, fx):
    resp = admin_user_api.create(**user_payload(fx, "t1"))
    CommonAssert.assert_error(resp, 400)


def test_patch_role(admin_user_api, fx):
    created = admin_user_api.create(**user_payload(fx, "s3", role="student",
                                                   grade_year="2026"))
    CommonAssert.assert_ok(created, 201)
    uid = created.data["id"]
    resp = admin_user_api.update(uid, role="teacher")
    CommonAssert.assert_ok(resp)
    assert admin_user_api.detail(uid).data["role"] == "teacher"


def test_cannot_delete_self(admin_user_api, admin_client):
    me = admin_client.get("/api/v1/auth/me/").data
    resp = admin_user_api.remove(me["id"])
    CommonAssert.assert_error(resp, 400, 10007)


def test_cannot_disable_self(admin_user_api, admin_client):
    me = admin_client.get("/api/v1/auth/me/").data
    resp = admin_user_api.toggle_active(me["id"])
    CommonAssert.assert_error(resp, 400, 10010)


def test_reset_password_returns_once(admin_user_api, fx):
    created = admin_user_api.create(**user_payload(fx, "t3"))
    CommonAssert.assert_ok(created, 201)
    resp = admin_user_api.reset_password(created.data["id"])
    CommonAssert.assert_ok(resp)
    assert len(resp.data["password"]) >= 12
    assert resp.data["password"] not in resp.message


def test_reset_password_rejects_weak(admin_user_api, fx):
    created = admin_user_api.create(**user_payload(fx, "t4"))
    CommonAssert.assert_ok(created, 201)
    resp = admin_user_api.reset_password(created.data["id"], new_password="123456")
    CommonAssert.assert_error(resp, 400, 10011)


def test_students_and_teachers_lists(admin_user_api):
    students = admin_user_api.students(page_size=5)
    teachers = admin_user_api.teachers(page_size=5)
    CommonAssert.assert_ok(students)
    CommonAssert.assert_ok(teachers)
    assert all(r["role"] == "student" for r in students.data["results"])
    assert all(r["role"] == "teacher" for r in teachers.data["results"])
