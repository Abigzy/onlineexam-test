# -*- coding: utf-8 -*-
"""JSON 数据驱动（对齐 IHRM 的 common/get_data.py）。

IHRM 的做法：data/*.json 存"一条用例一条记录"，读取后转成
`[(desc, req_data, status_code, code, message), ...]` 供 parametrize 使用。
这里保留同一约定，但把"转元组"做成通用函数，并按需保留字典形态。
"""
import json
import os

from config import DATA_DIR


def read_json(filename: str):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_as_tuples(filename: str, fields: list):
    """按指定字段顺序把每条记录转成元组，缺字段直接报错（避免静默漏列）。"""
    rows = []
    for index, item in enumerate(read_json(filename), start=1):
        missing = [f for f in fields if f not in item]
        if missing:
            raise KeyError(f"{filename} 第 {index} 条缺少字段：{missing}")
        rows.append(tuple(item[f] for f in fields))
    return rows


def read_login_data():
    """登录用例：desc, req_data, status_code, code, message"""
    return read_as_tuples("login_data.json",
                          ["desc", "req_data", "status_code", "code", "message"])
