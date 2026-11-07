# -*- coding: utf-8 -*-
"""B7 文件类与 AI 适配层：导出/模板的文件头与 Content-Type、AI 清单/连通/对话/用量/日志。"""
from __future__ import annotations

import pytest

from common.assert_tools import CommonAssert
from encap_api.admin_api import AiApi
from encap_api.content_api import PaperApi, QuestionApi

pytestmark = pytest.mark.l1


# ======================================================================
# 文件类
# ======================================================================
def test_export_questions_xlsx(seeded_question_api):
    resp = seeded_question_api.export("xlsx")
    assert resp.status == 200, resp.brief()
    assert "spreadsheet" in resp.headers.get("Content-Type", "")
    assert resp.raw[:2] == b"PK", "xlsx 应是 zip 容器（PK 文件头）"


def test_export_questions_csv(seeded_question_api):
    resp = seeded_question_api.export("csv")
    assert resp.status == 200
    assert "text/csv" in resp.headers.get("Content-Type", "")


def test_import_template(seeded_question_api):
    resp = seeded_question_api.template()
    assert resp.status == 200
    assert "text/csv" in resp.headers.get("Content-Type", "")
    assert "stem" in resp.text.lower() or "题干" in resp.text


def test_paper_export_html(seeded_teacher_client, fx):
    resp = PaperApi(seeded_teacher_client).export(fx["papers"]["published"], "html")
    assert resp.status == 200
    assert "text/html" in resp.headers.get("Content-Type", "")
    assert "<html" in resp.text.lower()


def test_paper_export_markdown(seeded_teacher_client, fx):
    resp = PaperApi(seeded_teacher_client).export(
        fx["papers"]["published"], "md", with_answer="true",
    )
    assert resp.status == 200
    assert "text/plain" in resp.headers.get("Content-Type", "")


def test_question_file_format_param_not_format(seeded_question_api):
    """`?format=csv` 是 DRF 内容协商参数，不能当业务参数用。"""
    resp = seeded_question_api.get("/questions/export/", params={"format": "csv"})
    assert resp.status in (200, 404), resp.brief()


# ======================================================================
# AI 适配层
# ======================================================================
def test_ai_providers(ai_api):
    resp = ai_api.providers()
    CommonAssert.assert_ok(resp)
    for key in ("current", "allow_mock", "providers"):
        assert key in resp.data
    assert isinstance(resp.data["providers"], list)


def test_ai_test_connection(ai_api):
    resp = ai_api.test_connection("mock")
    CommonAssert.assert_ok(resp)
    assert isinstance(resp.data["ok"], bool)


def test_ai_chat(ai_api):
    resp = ai_api.chat(prompt="用一句话解释栈", provider="mock")
    CommonAssert.assert_ok(resp)
    assert resp.data["content"]


def test_ai_chat_requires_input(ai_api):
    resp = ai_api.chat(provider="mock")
    CommonAssert.assert_error(resp, 400)


def test_ai_usage(ai_api):
    resp = ai_api.usage(days=7)
    CommonAssert.assert_ok(resp)
    assert "totals" in resp.data and "by_scene" in resp.data


def test_ai_logs(ai_api):
    resp = ai_api.logs(page_size=5)
    CommonAssert.assert_ok(resp)
    assert "results" in resp.data
    assert "total_pages" in resp.data
