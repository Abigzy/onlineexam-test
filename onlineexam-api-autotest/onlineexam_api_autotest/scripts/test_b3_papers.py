# -*- coding: utf-8 -*-
"""B3 试卷与组卷：卷头、加题/调分/排序/移出、状态机、克隆、分析、随机组卷、家底统计。"""
from __future__ import annotations

import pytest

from common.assert_tools import CommonAssert

pytestmark = pytest.mark.l1


def create_paper(api, fx, key, **over):
    payload = {
        "title": f"{fx['prefix']}_B3_{key}",
        "subject": fx["subject"],
        "duration_minutes": 30,
        "pass_score": 15,
    }
    payload.update(over)
    return api.create(**payload)


def preview_questions(api, pid):
    resp = api.preview(pid)
    CommonAssert.assert_ok(resp)
    return [q for sec in resp.data["sections"] for q in sec["questions"]]


def test_create_paper_defaults(seeded_paper_api, fx):
    resp = create_paper(seeded_paper_api, fx, "default")
    CommonAssert.assert_ok(resp, 201)
    assert resp.data["status"] == "draft"
    assert resp.data["question_count"] == 0
    assert resp.data["duration_minutes"] == 30


@pytest.mark.parametrize("duration", [0, 601])
def test_create_paper_duration_bounds(seeded_paper_api, fx, duration):
    resp = create_paper(seeded_paper_api, fx, f"dur{duration}", duration_minutes=duration)
    CommonAssert.assert_error(resp, 400)


def test_create_paper_duration_600_allowed(seeded_paper_api, fx):
    resp = create_paper(seeded_paper_api, fx, "dur600", duration_minutes=600)
    CommonAssert.assert_ok(resp, 201)


def test_add_questions_and_total(seeded_paper_api, fx):
    paper = create_paper(seeded_paper_api, fx, "add")
    pid = paper.data["id"]
    resp = seeded_paper_api.add_questions(
        pid, [fx["questions"]["single"], fx["questions"]["multiple"]],
    )
    CommonAssert.assert_ok(resp)
    assert resp.data["added_count"] == 2
    assert float(resp.data["total_score"]) == 6.0


def test_add_duplicate_question_skipped(seeded_paper_api, fx):
    paper = create_paper(seeded_paper_api, fx, "dup")
    pid = paper.data["id"]
    seeded_paper_api.add_questions(pid, [fx["questions"]["single"]])
    resp = seeded_paper_api.add_questions(pid, [fx["questions"]["single"]])
    CommonAssert.assert_ok(resp)
    assert resp.data["added_count"] == 0
    assert resp.data["duplicated_count"] == 1


def test_add_inactive_question_ignored(seeded_paper_api, fx):
    paper = create_paper(seeded_paper_api, fx, "inactive")
    pid = paper.data["id"]
    resp = seeded_paper_api.add_questions(pid, [fx["questions"]["inactive"]])
    CommonAssert.assert_ok(resp)
    # 视图层先用 is_active=True 过滤，停用题根本进不到 service，
    # 所以 invalid_count 是 0；关键是"没加进去"。
    assert resp.data["added_count"] == 0
    assert resp.data["question_count"] == 0


def test_set_score_100_and_101(seeded_paper_api, fx):
    paper = create_paper(seeded_paper_api, fx, "score")
    pid = paper.data["id"]
    seeded_paper_api.add_questions(pid, [fx["questions"]["single"]])
    pq = preview_questions(seeded_paper_api, pid)[0]["id"]

    ok = seeded_paper_api.set_scores(pid, [{"id": pq, "score": 100}])
    CommonAssert.assert_ok(ok)
    assert float(ok.data["total_score"]) == 100.0

    bad = seeded_paper_api.set_scores(pid, [{"id": pq, "score": 101}])
    CommonAssert.assert_error(bad, 400)


def test_reorder_and_preview_order(seeded_paper_api, fx):
    paper = create_paper(seeded_paper_api, fx, "reorder")
    pid = paper.data["id"]
    seeded_paper_api.add_questions(pid, [fx["questions"]["single"], fx["questions"]["multiple"]])
    ids = [q["id"] for q in preview_questions(seeded_paper_api, pid)]
    reversed_ids = list(reversed(ids))

    resp = seeded_paper_api.reorder(pid, reversed_ids)
    CommonAssert.assert_ok(resp)
    # preview 按大题分组返回，不能直接用扁平顺序比较；改比每道题的 order 序号
    after = {q["id"]: q["order"] for q in preview_questions(seeded_paper_api, pid)}
    assert [k for k, _ in sorted(after.items(), key=lambda kv: kv[1])] == reversed_ids


def test_remove_questions_reduces_total(seeded_paper_api, fx):
    paper = create_paper(seeded_paper_api, fx, "remove")
    pid = paper.data["id"]
    seeded_paper_api.add_questions(pid, [fx["questions"]["single"], fx["questions"]["multiple"]])
    pq = preview_questions(seeded_paper_api, pid)[0]["id"]
    resp = seeded_paper_api.remove_questions(pid, [pq])
    CommonAssert.assert_ok(resp)
    assert resp.data["removed_count"] == 1
    assert resp.data["question_count"] == 1


def test_publish_rejects_pass_score_over_total(seeded_paper_api, fx):
    paper = create_paper(seeded_paper_api, fx, "passover", pass_score=60)
    pid = paper.data["id"]
    seeded_paper_api.add_questions(pid, [fx["questions"]["judge"]])  # 2 分
    resp = seeded_paper_api.status(pid, "published")
    CommonAssert.assert_error(resp, 400, 13007)


def test_archive_hides_from_default_list(seeded_paper_api, fx):
    paper = create_paper(seeded_paper_api, fx, "archive", pass_score=1)
    pid = paper.data["id"]
    seeded_paper_api.add_questions(pid, [fx["questions"]["judge"]])
    CommonAssert.assert_ok(seeded_paper_api.status(pid, "published"))
    CommonAssert.assert_ok(seeded_paper_api.status(pid, "archived"))

    default = seeded_paper_api.list(page_size=50)
    archived = seeded_paper_api.list(status="archived", page_size=50)
    assert pid not in [r["id"] for r in default.data["results"]]
    assert pid in [r["id"] for r in archived.data["results"]]


def test_clone_copies_questions(seeded_paper_api, fx):
    source = seeded_paper_api.detail(fx["papers"]["draft"]).data
    resp = seeded_paper_api.clone(source["id"], fx["prefix"] + "_B3_clone")
    CommonAssert.assert_ok(resp, 201)
    assert resp.data["question_count"] == source["question_count"]
    assert resp.data["status"] == "draft"


def test_analysis_structure(seeded_paper_api, fx):
    resp = seeded_paper_api.analysis(fx["papers"]["draft"])
    CommonAssert.assert_ok(resp)
    assert resp.data, "组卷分析不应为空"


def test_random_compose_dry_run_no_side_effect(seeded_paper_api, fx):
    before = seeded_paper_api.statistics().data["total"]
    resp = seeded_paper_api.random_compose(
        subject=fx["subject"], total_count=3, dry_run=True,
    )
    CommonAssert.assert_ok(resp)
    assert "feasible" in resp.data
    after = seeded_paper_api.statistics().data["total"]
    assert after == before, "dry_run 不应落库"


def test_random_compose_same_seed(seeded_paper_api, fx):
    payload = dict(subject=fx["subject"], total_count=3, dry_run=True, seed=2026)
    first = seeded_paper_api.random_compose(**payload)
    second = seeded_paper_api.random_compose(**payload)
    CommonAssert.assert_ok(first)
    CommonAssert.assert_ok(second)
    def stable(payload):
        return {k: v for k, v in payload.items() if "elapsed" not in k}

    assert stable(first.data) == stable(second.data), "同 seed 结果应一致"


def test_random_compose_no_stock(seeded_paper_api, seeded_knowledge_api, fx):
    """用一个完全没有题目的知识点组卷 → 13010。"""
    import time
    empty_kp = seeded_knowledge_api.create(
        name=f"{fx['prefix']}_B3_空知识点_{time.time_ns() % 100000}", subject=fx["subject"],
    )
    CommonAssert.assert_ok(empty_kp, 201)
    resp = seeded_paper_api.random_compose(
        knowledge_point_ids=[empty_kp.data["id"]], total_count=3, dry_run=True,
    )
    CommonAssert.assert_error(resp, 400, 13010)


def test_pool_and_statistics(seeded_paper_api):
    pool = seeded_paper_api.pool()
    stats = seeded_paper_api.statistics()
    CommonAssert.assert_ok(pool)
    CommonAssert.assert_ok(stats)
    assert "total" in stats.data
