# -*- coding: utf-8 -*-
"""读取 scripts/seed_env.py 产出的 fixtures。

测试不直接连数据库取 id，只认 data/fixtures.json：
  * 造数失败 → 文件不存在 → 用例明确 skip（而不是 100 条红）；
  * 换环境只需重跑 seed_env.py。
"""
import json

from config import DATA_DIR

_CACHE = None


def load_fixtures() -> dict:
    global _CACHE
    if _CACHE is None:
        path = DATA_DIR + "/fixtures.json"
        try:
            with open(path, "r", encoding="utf-8") as fh:
                _CACHE = json.load(fh)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"未找到 {path}，请先运行 scripts/seed_env.py 造数"
            )
    return _CACHE


def paper_question_id(fx: dict, question_key: str) -> int:
    """按题目 key 取卷内条目 id（save/grade 用的是 paper_question_id）。"""
    qid = str(fx["questions"][question_key])
    return fx["paper_questions"][qid]
