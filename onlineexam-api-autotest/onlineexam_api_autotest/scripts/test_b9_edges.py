# -*- coding: utf-8 -*-
"""B9 边界专项：分页边界、批量上限、状态迁移、时间边界、次数上限。

与 B1–B8 的区别：本文件专门覆盖「靠构造才能触发」的边界。
时间类用例通过改库把 ``deadline_at`` 推到过去，避免 sleep 等待。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from common.assert_tools import CommonAssert
from common.db_tools import DbTools

pytestmark = pytest.mark.l1

FMT = "%Y-%m-%d %H:%M:%S"


def _window(minutes: int = 90):
    now = datetime.now()
    return (now - timedelta(minutes=5)).strftime(FMT), (now + timedelta(minutes=minutes)).strftime(FMT)


def _exam_payload(fx, key, **over):
    start, end = _window()
    payload = {
        "paper_id": fx["papers"]["published"],
        "title": f"{fx['prefix']}_B9_{key}",
        "start_time": start,
        "end_time": end,
        "duration_minutes": 30,
        "max_attempts": 2,
        "participant_ids": [fx["students"]["a"]["id"]],
    }
    payload.update(over)
    return payload


def _published_exam(teacher_api, fx, key, **over) -> int:
    created = teacher_api.create(**_exam_payload(fx, key, **over))
    CommonAssert.assert_ok(created, 201)
    eid = created.data["id"]
    CommonAssert.assert_ok(teacher_api.status(eid, "published"))
    return eid


def _start(student_exam_api, eid: int) -> int:
    resp = student_exam_api.start(eid)
    CommonAssert.assert_ok(resp)
    return resp.data["attempt"]["id"]


def _expire(aid: int) -> None:
    """把 deadline_at 推到 3 分钟前（超过 30s 宽限）。

    注意：库里存的是 UTC 朴素时间，必须用 UTC 计算，否则会推到未来。
    """
    past = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=3)).strftime(FMT)
    DbTools.db_uid("UPDATE exam_attempt SET deadline_at=%s WHERE id=%s", (past, aid))


# ======================================================================
# 一、分页边界（GEN-11）
# ======================================================================
def test_page_size_zero_falls_back_to_default(seeded_question_api):
    """page_size=0 不报错，回落到默认页长（实测 10 条）。"""
    default = seeded_question_api.list()
    CommonAssert.assert_ok(default)
    resp = seeded_question_api.list(page_size=0)
    CommonAssert.assert_ok(resp)
    assert len(resp.data["results"]) == len(default.data["results"])


def test_page_size_over_max_is_capped(seeded_question_api):
    """page_size 超上限按 100 截断；响应里的 page_size 是**实际生效值**，不算静默。

    接口文档 §1.4 已写明这条边界，前端拿响应 page_size 与请求值比对即可发现被压过。
    """
    resp = seeded_question_api.list(page_size=1000)
    CommonAssert.assert_ok(resp)
    assert resp.data["page_size"] == 100, "响应应回显实际生效的页长"
    assert len(resp.data["results"]) <= 100
    assert resp.data["count"] >= len(resp.data["results"])


@pytest.mark.parametrize("page", [0, -1, "abc"])
def test_invalid_page_param_returns_400(seeded_question_api, page):
    """page 取值非法（0 / 负数 / 非数字）是**参数错误** → 400/40000，不是 404。

    路径错与参数错要能分开：DRF 默认把 InvalidPage 归成 404，本项目在
    `StandardPagination.paginate_queryset` 里改成了 400。
    """
    resp = seeded_question_api.list(page=page)
    CommonAssert.assert_error(resp, 400, 40000)


def test_page_out_of_range_returns_404(seeded_question_api):
    """格式正确但页码超出总页数 → 404/40400（这一页确实不存在）。"""
    resp = seeded_question_api.list(page=9999)
    CommonAssert.assert_error(resp, 404, 40400)


def test_page_beyond_last_is_404_not_empty(seeded_question_api):
    """超过最后一页同样 404（DRF 分页器行为），前端需按 404 处理而不是当空列表。"""
    total = seeded_question_api.list().data["count"]
    resp = seeded_question_api.list(page=total + 100)
    CommonAssert.assert_error(resp, 404, 40400)


# ======================================================================
# 二、批量上限（ATT-07 / ATT-08）
# ======================================================================
def test_batch_save_empty_rejected(seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx):
    """空列表被拒。"""
    eid = _published_exam(seeded_exam_api, fx, "batch_empty")
    aid = _start(student_a_exam_api, eid)
    resp = student_a_attempt_api.save_answers(aid, [])
    CommonAssert.assert_error(resp, 400, 40000)


def _full_paper_items(fx) -> list:
    """整卷 6 题，按题型给合法作答（选择题给选项、主观题给文本）。"""
    labels = {
        "single": fx["answers"]["single"],
        "multiple": fx["answers"]["multiple"],
        "judge": fx["answers"]["judge"],
    }
    text = fx["answers"]["fill"]
    items = []
    for key, question_id in fx["questions"].items():
        pq = fx["paper_questions"].get(str(question_id))
        if pq is None:
            continue
        if key in labels:
            items.append({"paper_question_id": pq, "selected_labels": labels[key]})
        else:
            items.append({"paper_question_id": pq, "answer_text": text})
    return items


def test_batch_save_all_questions(seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx):
    """整卷一次性暂存：saved 等于条目数，明细全部标记已作答。"""
    eid = _published_exam(seeded_exam_api, fx, "batch_all")
    aid = _start(student_a_exam_api, eid)
    items = _full_paper_items(fx)
    resp = student_a_attempt_api.save_answers(aid, items)
    CommonAssert.assert_ok(resp)
    assert resp.data["saved"] == len(items)
    rows = student_a_attempt_api.answers(aid).data["results"]
    answered = [row for row in rows if row["is_answered"]]
    assert len(answered) == len(items)


def test_batch_save_duplicate_items_not_500(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """BUG-02 回归：同一题在 items 里出现两次，服务端去重（后写覆盖），不再 500。

    修复前：撞唯一键 `uniq_answer_attempt_question` → 500/50000，整批答案全丢。
    修复后：200，saved=1，以最后一条为准；其它题不受影响。
    """
    eid = _published_exam(seeded_exam_api, fx, "batch_dup")
    aid = _start(student_a_exam_api, eid)
    pq = list(fx["paper_questions"].values())[0]
    resp = student_a_attempt_api.save_answers(aid, [
        {"paper_question_id": pq, "selected_labels": "A"},
        {"paper_question_id": pq, "selected_labels": "B"},
    ])
    CommonAssert.assert_ok(resp)
    assert resp.data["saved"] == 1, "重复项应合并为 1 条"
    assert resp.data["ignored"] == 0

    rows = student_a_attempt_api.answers(aid).data["results"]
    saved = {row["paper_question_id"]: row for row in rows if row["is_answered"]}
    assert saved[pq]["selected_labels"] == "B", "去重口径应为「后写覆盖」"


def test_batch_save_duplicate_keeps_other_answers(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """重复项与正常项混在同一批：正常项不能被连累丢失。"""
    eid = _published_exam(seeded_exam_api, fx, "batch_dup_mix")
    aid = _start(student_a_exam_api, eid)
    single = fx["paper_questions"][str(fx["questions"]["single"])]
    judge = fx["paper_questions"][str(fx["questions"]["judge"])]
    resp = student_a_attempt_api.save_answers(aid, [
        {"paper_question_id": single, "selected_labels": "A"},
        {"paper_question_id": single, "selected_labels": "B"},
        {"paper_question_id": judge, "selected_labels": "A"},
    ])
    CommonAssert.assert_ok(resp)
    assert resp.data["saved"] == 2
    rows = student_a_attempt_api.answers(aid).data["results"]
    answered = {row["paper_question_id"] for row in rows if row["is_answered"]}
    assert answered == {single, judge}


def test_batch_save_unknown_question_ignored(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """非本卷题目被计入 ignored，合法项照常保存（不再整批失败）。"""
    eid = _published_exam(seeded_exam_api, fx, "batch_unknown")
    aid = _start(student_a_exam_api, eid)
    pq = list(fx["paper_questions"].values())[0]
    resp = student_a_attempt_api.save_answers(aid, [
        {"paper_question_id": 99999999, "selected_labels": "A"},
        {"paper_question_id": pq, "selected_labels": "A"},
    ])
    CommonAssert.assert_ok(resp)
    assert resp.data["ignored"] == 1
    assert resp.data["saved"] == 1


def test_batch_save_over_500_rejected(seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx):
    """501 条被拒，且一条都不落库。"""
    eid = _published_exam(seeded_exam_api, fx, "batch501")
    aid = _start(student_a_exam_api, eid)
    pq = list(fx["paper_questions"].values())[0]
    bad = student_a_attempt_api.save_answers(
        aid, [{"paper_question_id": pq, "selected_labels": "A"}] * 501,
    )
    CommonAssert.assert_error(bad, 400, 40000)
    rows = student_a_attempt_api.answers(aid).data["results"]
    assert all(row["is_answered"] is False for row in rows), "被拒后不应写入任何答案"


# ======================================================================
# 三、状态迁移（EXAM-09 / EXAM-10）
# ======================================================================
def test_exam_can_switch_to_ongoing(seeded_exam_api, fx):
    """D-09 定论：发布 → 进行中 是允许的（实测 200，status=ongoing）。"""
    eid = _published_exam(seeded_exam_api, fx, "ongoing")
    resp = seeded_exam_api.status(eid, "ongoing")
    CommonAssert.assert_ok(resp)
    assert resp.data["status"] == "ongoing"


def test_exam_illegal_transition_draft_to_finished(seeded_exam_api, fx):
    """草稿直接结束 → 400，提示「不允许从」。"""
    created = seeded_exam_api.create(**_exam_payload(fx, "illegal"))
    CommonAssert.assert_ok(created, 201)
    resp = seeded_exam_api.status(created.data["id"], "finished")
    CommonAssert.assert_error(resp, 400, message="不允许从")


# ======================================================================
# 四、次数上限（ATT-28）
# ======================================================================
def test_start_rejected_after_attempts_exhausted(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """max_attempts=1：交卷后再开考 → 400「最多作答 1 次，你已用完」，且不新增作答。"""
    eid = _published_exam(seeded_exam_api, fx, "once", max_attempts=1)
    aid = _start(student_a_exam_api, eid)
    CommonAssert.assert_ok(student_a_attempt_api.submit(aid))

    again = student_a_exam_api.start(eid)
    CommonAssert.assert_error(again, 400, message="你已用完")
    assert len(seeded_exam_api.attempts(eid).data["results"]) == 1


# ======================================================================
# 五、时间边界（ATT-10 / ATT-11 / ATT-27）
# ======================================================================
def test_batch_save_after_grace_rejected_and_settled(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """OBS-08 回归（批量入口）：超过宽限后暂存 → 400，且**自动收卷已提交**。

    修复前：收卷与拒绝同处一个事务，拒绝把收卷一起回滚，作答卡在 in_progress；
    修复后：`save_answers` 只负责结算，再把保存交给独立事务，
    因此返回 400 时状态已经落成 `timeout`。
    """
    eid = _published_exam(seeded_exam_api, fx, "expired_batch")
    aid = _start(student_a_exam_api, eid)
    pq = list(fx["paper_questions"].values())[0]
    _expire(aid)

    resp = student_a_attempt_api.save_answers(
        aid, [{"paper_question_id": pq, "selected_labels": "A"}],
    )
    CommonAssert.assert_error(resp, 400, 10400)
    assert student_a_attempt_api.detail(aid).data["status"] == "timeout", "收卷应随拒绝一起落库"
    rows = student_a_attempt_api.answers(aid).data["results"]
    assert all(row["is_answered"] is False for row in rows), "超时后不应写入答案"


def test_save_single_after_grace_rejected(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """单题入口超过宽限同样 400，答案不落库（与批量入口行为一致的部分）。"""
    eid = _published_exam(seeded_exam_api, fx, "expired_single")
    aid = _start(student_a_exam_api, eid)
    pq = list(fx["paper_questions"].values())[0]
    _expire(aid)

    resp = student_a_attempt_api.save(aid, paper_question_id=pq, selected_labels="A")
    CommonAssert.assert_error(resp, 400, 10400)
    rows = student_a_attempt_api.answers(aid).data["results"]
    assert all(row["is_answered"] is False for row in rows), "超时后不应写入答案"


def test_save_single_after_grace_settles_attempt(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """BUG-03 回归：单题 `/save/` 超时后既要拒绝保存，也要把作答结算成 `timeout`。

    修复前：`save_answer()` 外层 `@transaction.atomic` 把 `resolve_expiry` 的收卷
    一起回滚，作答停在 `in_progress`，教师侧一直显示"进行中"、`finalize` 被拒。
    修复后：去掉该注解，`save_answer()` 与批量入口共用同一事务边界。
    """
    eid = _published_exam(seeded_exam_api, fx, "expired_single_settle")
    aid = _start(student_a_exam_api, eid)
    pq = list(fx["paper_questions"].values())[0]
    _expire(aid)

    resp = student_a_attempt_api.save(aid, paper_question_id=pq, selected_labels="A")
    CommonAssert.assert_error(resp, 400, 10400)
    detail = student_a_attempt_api.detail(aid).data
    assert detail["status"] == "timeout", "单题入口也应结算为 timeout"
    assert detail["is_timeout"] is True
    rows = student_a_attempt_api.answers(aid).data["results"]
    assert all(row["is_answered"] is False for row in rows), "拒绝保存时不应写入答案"


def test_save_single_normal_path_still_saves(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """回归副作用检查：去掉事务注解后，单题保存的正常路径仍能写入并返回该题最新态。"""
    eid = _published_exam(seeded_exam_api, fx, "single_ok")
    aid = _start(student_a_exam_api, eid)
    pq = list(fx["paper_questions"].values())[0]

    resp = student_a_attempt_api.save(aid, paper_question_id=pq, selected_labels="A")
    CommonAssert.assert_ok(resp)
    assert resp.data["saved"] == 1
    assert resp.data["answer"]["is_answered"] is True
    assert resp.data["answer"]["selected_labels"] == "A"


def test_heartbeat_settles_expired_attempt(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """超时后由心跳结算：status=timeout、should_submit=true、剩余 0 秒。"""
    eid = _published_exam(seeded_exam_api, fx, "hb_timeout")
    aid = _start(student_a_exam_api, eid)
    _expire(aid)

    resp = student_a_attempt_api.heartbeat(aid, client_remaining=99999)
    CommonAssert.assert_ok(resp)
    assert resp.data["status"] == "timeout"
    assert resp.data["should_submit"] is True
    assert resp.data["remaining_seconds"] == 0
    assert student_a_attempt_api.detail(aid).data["status"] == "timeout"


def test_heartbeat_cannot_extend_time(
    seeded_exam_api, student_a_exam_api, student_a_attempt_api, fx,
):
    """客户端上报剩余 99999 秒无效：服务端时间是权威，剩余不超过考试时长。"""
    eid = _published_exam(seeded_exam_api, fx, "hb_drift", duration_minutes=30)
    aid = _start(student_a_exam_api, eid)
    resp = student_a_attempt_api.heartbeat(aid, client_remaining=99999)
    CommonAssert.assert_ok(resp)
    assert resp.data["remaining_seconds"] <= 30 * 60
    assert resp.data.get("clock_drift_seconds") not in (None, 0)
