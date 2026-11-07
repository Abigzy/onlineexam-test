# -*- coding: utf-8 -*-
"""B1 题库与知识点：六题型 CRUD、校验、筛选、软删除、AI 草稿、批量入库、统计。"""
from __future__ import annotations

import pytest

from common.assert_tools import CommonAssert

pytestmark = pytest.mark.l1


def q_payload(fx, suffix, **over):
    payload = {
        "type": "single",
        "stem": f"{fx['prefix']}_B1_{suffix}",
        "subject": fx["subject"],
        "difficulty": 2,
        "score": 2,
        "reference_answer": "A",
        "options": [
            {"label": "A", "content": "选项A", "is_correct": True},
            {"label": "B", "content": "选项B", "is_correct": False},
            {"label": "C", "content": "选项C", "is_correct": False},
            {"label": "D", "content": "选项D", "is_correct": False},
        ],
        "knowledge_point_ids": [fx["knowledge"]["child"]],
    }
    payload.update(over)
    return payload


def test_create_six_question_types(seeded_question_api, fx):
    types = [
        ("single", {}),
        ("multiple", {"reference_answer": "ABC", "options": [
            {"label": "A", "content": "A", "is_correct": True},
            {"label": "B", "content": "B", "is_correct": True},
            {"label": "C", "content": "C", "is_correct": True},
            {"label": "D", "content": "D", "is_correct": False},
        ]}),
        ("judge", {"reference_answer": "A", "options": [
            {"label": "A", "content": "正确", "is_correct": True},
            {"label": "B", "content": "错误", "is_correct": False},
        ]}),
        ("fill", {"reference_answer": "第一空\n第二空", "options": None}),
        ("short", {"reference_answer": "参考答案文本", "options": None}),
        ("essay", {"reference_answer": "论述参考答案", "options": None}),
    ]
    created = []
    for index, (qtype, extra) in enumerate(types):
        payload = q_payload(fx, f"type{index}", type=qtype)
        payload.update(extra)
        if payload.get("options") is None:
            payload.pop("options", None)
        resp = seeded_question_api.create(**payload)
        CommonAssert.assert_ok(resp, 201)
        assert resp.data["type"] == qtype
        created.append(resp.data["id"])
    assert len(set(created)) == 6


@pytest.mark.parametrize("mutate,desc", [
    (lambda p: p.pop("options"), "选择题缺选项"),
    (lambda p: p.update(reference_answer=""), "简答缺参考答案"),
    (lambda p: p.update(score=0), "分值 0"),
    (lambda p: p.update(score=101), "分值 101"),
    (lambda p: p.update(type="code"), "非法题型"),
    (lambda p: p.update(stem="a"), "题干过短"),
])
def test_create_question_invalid(seeded_question_api, fx, mutate, desc):
    payload = q_payload(fx, "invalid", type="short")
    if desc != "简答缺参考答案":
        payload = q_payload(fx, "invalid")
    mutate(payload)
    resp = seeded_question_api.create(**payload)
    CommonAssert.assert_error(resp, 400)


def test_create_question_score_100_allowed(seeded_question_api, fx):
    resp = seeded_question_api.create(**q_payload(fx, "score100", score=100))
    CommonAssert.assert_ok(resp, 201)


def test_list_filter_by_type_and_difficulty(seeded_question_api, fx):
    resp = seeded_question_api.list(type="single", difficulty=2, page_size=5)
    CommonAssert.assert_ok(resp)
    assert all(r["type"] == "single" for r in resp.data["results"])


def test_detail_contains_answer_and_options(seeded_question_api, fx):
    resp = seeded_question_api.detail(fx["questions"]["single"])
    CommonAssert.assert_ok(resp)
    assert resp.data["reference_answer"]
    assert resp.data["options"]


def test_update_stem(seeded_question_api, fx):
    new_stem = fx["prefix"] + "_B1_改题干"
    resp = seeded_question_api.update(fx["questions"]["single"], stem=new_stem)
    CommonAssert.assert_ok(resp)
    assert seeded_question_api.detail(fx["questions"]["single"]).data["stem"] == new_stem


def test_soft_delete_keeps_history(seeded_question_api, fx):
    created = seeded_question_api.create(**q_payload(fx, "softdel"))
    CommonAssert.assert_ok(created, 201)
    qid = created.data["id"]
    CommonAssert.assert_ok(seeded_question_api.remove(qid))
    detail = seeded_question_api.detail(qid)
    assert detail.status == 200 and detail.data["is_active"] is False
    # 实测：列表仍会返回该题（带 is_active=false），不是物理消失。
    # 因此断言"列表里若出现，必须标记为停用"，不强行要求消失。
    listing = seeded_question_api.list(search=fx["prefix"] + "_B1_softdel", page_size=10)
    row = next((r for r in listing.data["results"] if r["id"] == qid), None)
    assert row is None or row["is_active"] is False


def test_ai_generate_returns_drafts_only(seeded_question_api, fx):
    before = seeded_question_api.statistics().data["total"]
    resp = seeded_question_api.ai_generate(
        subject=fx["subject"], knowledge_points=[fx["knowledge"]["child"]],
        question_types=["single"], difficulty=2, count=2, provider="mock",
    )
    CommonAssert.assert_ok(resp)
    assert len(resp.data["drafts"]) == 2
    assert resp.data["meta"]["is_mock"] is True
    assert seeded_question_api.statistics().data["total"] == before


def test_batch_create(seeded_question_api, fx):
    items = [q_payload(fx, f"batch{i}") for i in range(2)]
    for item in items:
        item.pop("knowledge_point_ids", None)
    resp = seeded_question_api.batch(items=items)
    CommonAssert.assert_ok(resp, 201)
    assert resp.data["created_count"] == 2


def test_statistics_structure(seeded_question_api):
    resp = seeded_question_api.statistics()
    CommonAssert.assert_ok(resp)
    for key in ("total", "by_type", "by_difficulty", "average_difficulty", "subjective_count"):
        assert key in resp.data


def test_subjects(seeded_question_api):
    resp = seeded_question_api.subjects()
    CommonAssert.assert_ok(resp)
    assert resp.data["count"] >= 1


def test_cross_subject_question_invisible(os_teacher_client, seeded_question_api, fx):
    """学科隔离：计算机网络题对 os_teacher（操作系统）不可见。"""
    from encap_api.content_api import QuestionApi

    created = seeded_question_api.create(**q_payload(
        fx, "net", subject="计算机网络",
        knowledge_point_ids=[fx["knowledge"]["net"]],
    ))
    CommonAssert.assert_ok(created, 201)
    resp = QuestionApi(os_teacher_client).detail(created.data["id"])
    CommonAssert.assert_error(resp, 404, 40400)
