# -*- coding: utf-8 -*-
"""已关闭缺陷的守门用例（回归守卫）。

这里放"曾经真出过、修好之后不能再坏"的检查。它们不走浏览器，直接打接口，
成本低（毫秒级），但能在每次回归时把老问题重新钉一遍。

当前守卫：
    BUG-01  删除「被考试引用的草稿试卷」必须返回 4xx 业务错误（13008），不能 500
    BUG-02  题目编辑器只填部分选项必须能保存；嵌套错误必须渲染成可读文案
            （这两条依赖前端，所以走浏览器；其余守卫仍是纯接口）
"""
import allure
import pytest

import config
from common.api_client import ApiSession
from common.data_factory import _delete_exam
from pages.teacher_pages import QuestionBankPage, QuestionEditorPage
from pages.teacher_pages import QuestionBankPage, QuestionEditorPage

pytestmark = [pytest.mark.p1]


def _make_paper(adm, title, count=2):
    data = adm.post("/papers/random-compose/",
                    json={"title": title, "total_count": count,
                          "target_difficulty": 2.0, "duration_minutes": 10})
    return (data.get("paper") or data)["id"]


def _make_exam(adm, paper_id, title):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone(timedelta(hours=8)))
    data = adm.post("/exams/", json={
        "title": title, "paper_id": paper_id,
        "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=1)).isoformat(),
        "duration_minutes": 10, "open_to_all": True})
    return (data.get("exam") or data)["id"]


def _raw_delete(adm, pid):
    r = adm.session.delete(config.API_URL + "/papers/%s/" % pid, timeout=30)
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body.get("code"), str(body.get("message", ""))


@allure.feature("已关闭缺陷守门")
class TestClosedDefects:
    @allure.story("BUG-01 删除被考试引用的草稿试卷返回 4xx 而非 500")
    @allure.severity(allure.severity_level.NORMAL)
    def test_bug01_delete_referenced_draft_paper(self, sessions):
        adm = sessions["admin"]
        tag = config.tag("BUG01")
        pid = _make_paper(adm, tag)
        adm.post("/papers/%s/status/" % pid, json={"status": "published"})
        eid = _make_exam(adm, pid, tag)
        try:
            adm.post("/papers/%s/status/" % pid, json={"status": "draft"})
            status, code, msg = _raw_delete(adm, pid)
            assert 400 <= status < 500, \
                "被引用的草稿卷删除应返回 4xx，实际 HTTP %s（BUG-01 复发）" % status
            assert code == 13008, "业务码应为 13008（引用检查），实际 %s" % code
            assert "引用" in msg, "提示文案应说明「被考试引用」，实际：%s" % msg
        finally:
            _delete_exam(adm, eid)

    @allure.story("BUG-01 修复不误伤：无引用的草稿卷仍能删除")
    @allure.severity(allure.severity_level.NORMAL)
    def test_bug01_unreferenced_draft_paper_still_deletable(self, sessions):
        adm = sessions["admin"]
        pid = _make_paper(adm, config.tag("BUG01_CLEAN"))
        status, code, _ = _raw_delete(adm, pid)
        assert status in (200, 204), \
            "无引用的草稿卷应能正常删除，实际 HTTP %s code=%s" % (status, code)


@allure.feature("已关闭缺陷守门")
class TestBug02Guard:
    """BUG-02 的守卫：前端行为，只能走浏览器。

    为什么值得占一条 UI 用例：这两点都是"只改前端、后端看起来一切正常"的修复，
    最容易在后来的重构里被顺手删掉（`filter(o => o.content)` 少一行就复发）。
    """

    @allure.story("BUG-02 只填部分选项也能保存，且空行不入库")
    @allure.severity(allure.severity_level.NORMAL)
    def test_bug02_partial_options_savable(self, as_teacher, sessions, request):
        stem = config.tag("BUG02守卫_%s" % request.node.name[-10:])
        editor = QuestionEditorPage(as_teacher).open()
        editor.fill(stem=stem, subject="数据结构")
        editor.fill_option(0, "甲", correct=True)
        editor.fill_option(1, "乙")               # 故意只填 2 行，C/D 留空

        page = editor.save_expect_list()
        try:
            page.keyword(stem, expect_hit=True)
            assert page.row_count() == 1, "只填 2 个选项的题目没有保存成功（BUG-02 复发）"

            data = sessions["teacher"].get(
                "/questions/", params={"keyword": stem, "page_size": 10})
            qid = next(q["id"] for q in (data.get("results") or []) if q["stem"] == stem)
            options = sessions["teacher"].get("/questions/%s/" % qid).get("options") or []
            assert len(options) == 2, \
                "空选项行应被前端过滤掉，实际入库 %d 个选项" % len(options)
        finally:
            data = sessions["teacher"].get(
                "/questions/", params={"keyword": stem, "page_size": 10})
            for q in data.get("results") or []:
                if q["stem"] == stem:
                    sessions["teacher"].delete("/questions/%s/" % q["id"], expect=(200, 204))

    @allure.story("BUG-02 嵌套错误渲染成可读文案，不出现 [object Object]")
    @allure.severity(allure.severity_level.NORMAL)
    def test_bug02_error_text_readable(self, as_teacher):
        page = QuestionBankPage(as_teacher).open()
        rendered = page.js(
            "return UI.errorText({data: {options: [{}, {}, "
            "{content: ['该字段不能为空。']}, {content: ['该字段不能为空。']}]}});")

        assert "[object Object]" not in (rendered or ""), \
            "嵌套错误又渲染成 [object Object]（BUG-02 复发）：%r" % rendered
        assert "该字段不能为空" in (rendered or ""), \
            "错误原文丢失，用户仍看不懂：%r" % rendered


@allure.feature("已关闭缺陷守门")
class TestBug02Guard:
    """BUG-02 的守卫：前端行为，只能走浏览器。

    为什么值得占一条 UI 用例：这两点都是"只改前端、后端看起来一切正常"的修复，
    最容易在后来的重构里被顺手删掉（`filter(o => o.content)` 少一行就复发）。
    """

    @allure.story("BUG-02 只填部分选项也能保存，且空行不入库")
    @allure.severity(allure.severity_level.NORMAL)
    def test_bug02_partial_options_savable(self, as_teacher, sessions, request):
        stem = config.tag("BUG02守卫_%s" % request.node.name[-10:])
        editor = QuestionEditorPage(as_teacher).open()
        editor.fill(stem=stem, subject="数据结构")
        editor.fill_option(0, "甲", correct=True)
        editor.fill_option(1, "乙")               # 故意只填 2 行，C/D 留空

        page = editor.save_expect_list()
        try:
            page.keyword(stem, expect_hit=True)
            assert page.row_count() == 1, "只填 2 个选项的题目没有保存成功（BUG-02 复发）"

            data = sessions["teacher"].get(
                "/questions/", params={"keyword": stem, "page_size": 10})
            qid = next(q["id"] for q in (data.get("results") or []) if q["stem"] == stem)
            options = sessions["teacher"].get("/questions/%s/" % qid).get("options") or []
            assert len(options) == 2,                 "空选项行应被前端过滤掉，实际入库 %d 个选项" % len(options)
        finally:
            data = sessions["teacher"].get(
                "/questions/", params={"keyword": stem, "page_size": 10})
            for q in data.get("results") or []:
                if q["stem"] == stem:
                    sessions["teacher"].delete("/questions/%s/" % q["id"], expect=(200, 204))

    @allure.story("BUG-02 嵌套错误渲染成可读文案，不出现 [object Object]")
    @allure.severity(allure.severity_level.NORMAL)
    def test_bug02_error_text_readable(self, as_teacher):
        page = QuestionBankPage(as_teacher).open()
        rendered = page.js(
            "return UI.errorText({data: {options: [{}, {}, "
            "{content: ['该字段不能为空。']}, {content: ['该字段不能为空。']}]}});")

        assert "[object Object]" not in (rendered or ""),             "嵌套错误又渲染成 [object Object]（BUG-02 复发）：%r" % rendered
        assert "该字段不能为空" in (rendered or ""),             "错误原文丢失，用户仍看不懂：%r" % rendered
