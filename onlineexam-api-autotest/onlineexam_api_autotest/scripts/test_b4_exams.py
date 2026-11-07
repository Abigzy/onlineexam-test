# -*- coding: utf-8 -*-
"""B4 考试配置：建考校验、删除护栏、统计看板、候选人、学生可见性。"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from common.assert_tools import CommonAssert
from encap_api.exam_api import ExamApi

pytestmark = pytest.mark.l1

FMT = "%Y-%m-%d %H:%M:%S"


def window():
    now = datetime.now()
    return (now - timedelta(minutes=5)).strftime(FMT), (now + timedelta(minutes=60)).strftime(FMT)


def exam_payload(fx, key, **over):
    start, end = window()
    payload = {
        "paper_id": fx["papers"]["published"],
        "title": f"{fx['prefix']}_B4_{key}",
        "start_time": start,
        "end_time": end,
        "duration_minutes": 20,
        "max_attempts": 1,
    }
    payload.update(over)
    return payload


def test_create_exam_draft(seeded_exam_api, fx):
    resp = seeded_exam_api.create(**exam_payload(fx, "draft"))
    CommonAssert.assert_ok(resp, 201)
    assert resp.data["status"] == "draft"
    assert resp.data["paper"]["id"] == fx["papers"]["published"]


def test_create_exam_without_paper(seeded_exam_api, fx):
    payload = exam_payload(fx, "nopaper")
    payload.pop("paper_id")
    resp = seeded_exam_api.create(**payload)
    CommonAssert.assert_error(resp, 400)


def test_create_exam_invalid_window(seeded_exam_api, fx):
    start, end = window()
    resp = seeded_exam_api.create(**exam_payload(
        fx, "window", start_time=end, end_time=start,
    ))
    CommonAssert.assert_error(resp, 400)


def test_create_exam_participant_not_student(seeded_exam_api, fx):
    resp = seeded_exam_api.create(**exam_payload(
        fx, "badpart", participant_ids=[fx["teacher"]["id"]],
    ))
    CommonAssert.assert_error(resp, 400)


def test_publish_exam_with_unknown_paper(seeded_exam_api, fx):
    payload = exam_payload(fx, "badpaper")
    payload["paper_id"] = 99999999
    resp = seeded_exam_api.create(**payload)
    CommonAssert.assert_error(resp, 400)


def test_delete_exam_without_attempts(seeded_exam_api, fx):
    created = seeded_exam_api.create(**exam_payload(fx, "deletable"))
    CommonAssert.assert_ok(created, 201)
    eid = created.data["id"]
    CommonAssert.assert_ok(seeded_exam_api.remove(eid))
    assert seeded_exam_api.detail(eid).status == 404


def test_delete_exam_with_attempts_rejected(seeded_exam_api, student_a_exam_api, fx):
    """自己造一场有作答的考试再删，避免依赖其它用例的执行顺序。"""
    created = seeded_exam_api.create(**exam_payload(
        fx, "withattempts", participant_ids=[fx["students"]["a"]["id"]],
    ))
    CommonAssert.assert_ok(created, 201)
    eid = created.data["id"]
    CommonAssert.assert_ok(seeded_exam_api.status(eid, "published"))
    started = student_a_exam_api.start(eid)
    CommonAssert.assert_ok(started)

    resp = seeded_exam_api.remove(eid)
    CommonAssert.assert_error(resp, 400)
    assert "不能删除" in resp.message
    assert seeded_exam_api.detail(eid).status == 200


def test_overview_structure(seeded_exam_api, fx):
    resp = seeded_exam_api.overview(fx["exams"]["normal"])
    CommonAssert.assert_ok(resp)
    assert resp.data["applicants"] >= 1
    # 不同版本字段名可能是 started / attempt_total，至少要有作答计数
    assert any(k in resp.data for k in ("started", "attempt_total"))


def test_attempt_table_filter(seeded_exam_api, fx):
    resp = seeded_exam_api.attempts(fx["exams"]["normal"])
    CommonAssert.assert_ok(resp)
    assert "results" in resp.data
    assert all("can_view_analytics" in row for row in resp.data["results"])


def test_candidates_structure(seeded_exam_api):
    resp = seeded_exam_api.candidates()
    CommonAssert.assert_ok(resp)
    assert "classrooms" in resp.data


def test_statistics(seeded_exam_api):
    resp = seeded_exam_api.statistics()
    CommonAssert.assert_ok(resp)
    assert resp.data


def test_student_exam_list_excludes_draft(seeded_exam_api, student_a_exam_api, fx):
    created = seeded_exam_api.create(**exam_payload(fx, "hidden_draft"))
    CommonAssert.assert_ok(created, 201)
    listing = student_a_exam_api.list(page_size=50)
    CommonAssert.assert_ok(listing)
    assert created.data["id"] not in [r["id"] for r in listing.data["results"]]
