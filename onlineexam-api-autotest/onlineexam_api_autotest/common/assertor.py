# -*- coding: utf-8 -*-
"""断言工具：双断言、禁 500、敏感字段扫描、分页两套模板。

所有失败信息都带 method/path/status/code/响应摘要，定位不需要再翻日志。
"""
from __future__ import annotations

from typing import Iterable

from .client import ApiResponse


class AssertionFailure(AssertionError):
    pass


def _ctx(resp: ApiResponse) -> str:
    return (f"{resp.method} {resp.path} -> HTTP {resp.status} code={resp.code} "
            f"msg={resp.message!r} body={resp.brief()}")


def assert_ok(resp: ApiResponse, expected_status: int | None = None) -> ApiResponse:
    """成功：HTTP 2xx（默认 200/201）+ code == 0。"""
    if expected_status is not None:
        assert resp.status == expected_status, f"期望 HTTP {expected_status}，实际 {_ctx(resp)}"
    else:
        assert 200 <= resp.status < 300, f"期望 2xx，实际 {_ctx(resp)}"
    assert resp.code == 0, f"期望 code=0，实际 {_ctx(resp)}"
    return resp


def assert_error(resp: ApiResponse, status: int, code: int | None = None) -> ApiResponse:
    """失败：HTTP 状态与业务码都要对上；没有 code 的接口只校验状态。"""
    assert resp.status == status, f"期望 HTTP {status}，实际 {_ctx(resp)}"
    if code is not None:
        assert resp.code == code, f"期望 code={code}，实际 {_ctx(resp)}"
    assert resp.status != 500, f"出现 500：{_ctx(resp)}"
    return resp


def assert_no_500(resp: ApiResponse) -> ApiResponse:
    assert resp.status != 500, f"不允许 500：{_ctx(resp)}"
    return resp


def assert_status_in(resp: ApiResponse, allowed: Iterable[int]) -> ApiResponse:
    allowed = tuple(allowed)
    assert resp.status in allowed, f"期望 HTTP ∈ {allowed}，实际 {_ctx(resp)}"
    return resp


def assert_code_in(resp: ApiResponse, allowed: Iterable[int]) -> ApiResponse:
    allowed = tuple(allowed)
    assert resp.code in allowed, f"期望 code ∈ {allowed}，实际 {_ctx(resp)}"
    return resp


def assert_field(data: dict, key: str, expected=None):
    assert isinstance(data, dict), f"data 不是对象：{data!r}"
    assert key in data, f"缺少字段 {key!r}，实际字段={sorted(data)}"
    if expected is not None:
        assert data[key] == expected, f"字段 {key} 期望 {expected!r}，实际 {data[key]!r}"
    return data[key]


def assert_pagination_a(resp: ApiResponse, page_size: int | None = None) -> dict:
    """形态 A：DRF 标准分页，必须有 total_pages/next/previous/results。"""
    data = resp.data or {}
    for key in ("count", "total_pages", "page", "page_size", "next", "previous", "results"):
        assert key in data, f"形态 A 缺少 {key!r}：{_ctx(resp)}"
    assert isinstance(data["results"], list), f"results 不是数组：{_ctx(resp)}"
    assert data["count"] >= len(data["results"]), f"count 小于本页条数：{_ctx(resp)}"
    if page_size is not None:
        assert len(data["results"]) <= page_size, f"本页条数超过 page_size：{_ctx(resp)}"
    return data


def assert_pagination_b(resp: ApiResponse) -> dict:
    """形态 B：手写 {count, results}，不应出现 page/total_pages。"""
    data = resp.data or {}
    assert "count" in data and "results" in data, f"形态 B 缺少 count/results：{_ctx(resp)}"
    assert isinstance(data["results"], list), f"results 不是数组：{_ctx(resp)}"
    assert len(data["results"]) == data["count"], f"count 与 results 长度不一致：{_ctx(resp)}"
    for key in ("page", "total_pages"):
        assert key not in data, f"形态 B 不应有 {key}：{_ctx(resp)}"
    return data


# ----------------------------------------------------------------------
# 敏感字段扫描（横切安全的本地实现，不依赖被测项目的测试代码）
# ----------------------------------------------------------------------
ANSWER_FIELDS = ("reference_answer", "analysis", "correct_answer")
SCORE_FIELDS = ("is_correct", "score", "ai_score", "ai_comment", "teacher_comment", "passed")


def collect_fields(node, targets, out: dict | None = None) -> dict:
    """递归收集目标字段的全部取值（列表里逐行都要查，不能只看首个）。"""
    out = {} if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            if key in targets:
                out.setdefault(key, []).append(value)
            collect_fields(value, targets, out)
    elif isinstance(node, list):
        for item in node:
            collect_fields(item, targets, out)
    return out


def _is_blank(value) -> bool:
    return value is None or value == "" or value == []


def assert_no_answer_fields(payload) -> None:
    found = collect_fields(payload, ANSWER_FIELDS)
    assert not found, f"学生视角出现答案字段：{found}"


def assert_score_fields_blank(payload) -> None:
    found = collect_fields(payload, SCORE_FIELDS)
    leaked = {k: [v for v in vals if not _is_blank(v)] for k, vals in found.items()}
    leaked = {k: v for k, v in leaked.items() if v}
    assert not leaked, f"未公开成绩却下发分数/对错：{leaked}"
