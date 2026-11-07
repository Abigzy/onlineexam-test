# -*- coding: utf-8 -*-
"""获取 token（对齐 IHRM 的 common/get_token.py）。

IHRM 每次调用都登录一次；这里加一层缓存，原因是本项目 `auth` 限流 30/min，
全量用例重复登录会在第 31 条开始集体 429。
"""
from common.auth import login
from config import TEACHER

_TOKEN_CACHE: dict[str, str] = {}


def get_token(alias: str = TEACHER) -> str:
    """返回 access token 字符串。"""
    if alias not in _TOKEN_CACHE:
        _TOKEN_CACHE[alias] = login(alias).token
    return _TOKEN_CACHE[alias]


def get_headers(alias: str = TEACHER) -> dict:
    """返回可直接塞进 requests 的鉴权头。"""
    return {"Authorization": f"Bearer {get_token(alias)}"}
