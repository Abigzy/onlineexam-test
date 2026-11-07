# -*- coding: utf-8 -*-
"""B10 文件导入：CSV 导入成功/判重/空文件/缺文件/试算不落库。

样本文件在运行期生成到临时目录，不入库、不进版本库。
"""
from __future__ import annotations

import os
import tempfile
import time

import pytest

from common.assert_tools import CommonAssert

pytestmark = pytest.mark.l1

# 题目会真实入库且判重，「题干」必须每次运行唯一，否则二次执行会全部被判重跳过。
RUN_TAG = str(time.time_ns() % 1000000)

HEADER = (
    "知识点编号,知识点,学科,题型,难度,分值,题干,"
    "选项A,选项B,选项C,选项D,选项E,选项F,正确答案,解析\n"
)


def _write_csv(fx, name: str, rows: list, *, header: bool = True) -> str:
    path = os.path.join(tempfile.gettempdir(), f"{fx['prefix']}_{name}")
    content = (HEADER if header else "") + "".join(rows)
    # utf-8-sig：Windows 下 Excel 直接打开不乱码，也验证后端能识别 BOM
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(content)
    return path


def _rows(fx, count: int, tag: str = "CSV") -> list:
    rows = []
    for index in range(count):
        rows.append(
            f"AT-{index},,{fx['subject']},单选题,简单,2,"
            f"{fx['prefix']}_{tag}{RUN_TAG}_{index},甲,乙,丙,丁,,,B,解析{index}\n"
        )
    return rows


def test_import_csv_success(seeded_question_api, fx):
    """3 行合法 CSV → total_rows=3、created_count=3。"""
    path = _write_csv(fx, "import_ok.csv", _rows(fx, 3))
    resp = seeded_question_api.import_file(path)
    CommonAssert.assert_ok(resp)
    assert resp.data["total_rows"] == 3
    assert resp.data["created_count"] == 3
    assert resp.data["skipped_count"] == 0
    assert len(resp.data["created_ids"]) == 3


def test_import_same_file_skips_duplicates(seeded_question_api, fx):
    """同一文件再导一次：全部判重跳过，不新增。"""
    path = _write_csv(fx, "import_dup.csv", _rows(fx, 3, tag="DUP"))
    first = seeded_question_api.import_file(path)
    CommonAssert.assert_ok(first)
    assert first.data["created_count"] == 3

    second = seeded_question_api.import_file(path)
    CommonAssert.assert_ok(second)
    assert second.data["created_count"] == 0
    assert second.data["skipped_count"] == 3
    assert second.data["skipped"][0]["reason"]


def test_import_dry_run_no_side_effect(seeded_question_api, fx):
    """dry_run=true 只解析不入库。"""
    path = _write_csv(fx, "import_dry.csv", _rows(fx, 2, tag="DRY"))
    before = seeded_question_api.statistics().data["total"]
    resp = seeded_question_api.import_file(path, dry_run="true")
    CommonAssert.assert_ok(resp)
    assert resp.data["dry_run"] is True
    assert resp.data["created_count"] == 0
    assert resp.data["parsed"] == 2
    assert seeded_question_api.statistics().data["total"] == before


def test_import_empty_file_rejected(seeded_question_api, fx):
    """只有表头、没有数据行 → 400/12034。"""
    path = _write_csv(fx, "import_empty.csv", [])
    resp = seeded_question_api.import_file(path)
    CommonAssert.assert_error(resp, 400, 12034)


def test_import_without_file_rejected(seeded_question_api):
    """不传 file 字段 → 400/12033。"""
    resp = seeded_question_api.post("/questions/import/", files={})
    CommonAssert.assert_error(resp, 400, 12033)


def test_import_partial_invalid_rows(seeded_question_api, fx):
    """混合批次：合法行进库、非法行记 errors，不整批失败。"""
    rows = _rows(fx, 2, tag="MIX")
    rows.append(f"AT-X,,{fx['subject']},单选题,简单,2,,甲,乙,丙,丁,,,B,\n")  # 题干为空（本就非法）
    path = _write_csv(fx, "import_mix.csv", rows)

    resp = seeded_question_api.import_file(path)
    CommonAssert.assert_ok(resp)
    assert resp.data["total_rows"] == 3
    assert resp.data["created_count"] == 2
    assert len(resp.data["errors"]) == 1


def test_import_template_has_header(seeded_question_api):
    """模板下载返回 CSV 且首行为中文表头。"""
    resp = seeded_question_api.template()
    assert resp.status == 200
    assert "text/csv" in resp.headers.get("Content-Type", "")
    first_line = resp.body.splitlines()[0]
    assert "题干" in first_line and "正确答案" in first_line
