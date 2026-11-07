# -*- coding: utf-8 -*-
"""B12 限流专项（GEN-12）：登录 30 次/分钟后返回 429。

为什么单独放一个文件并标 ``slow``：
  * 触发限流会污染同一分钟内的 auth 作用域，影响其它批次登录；
  * 需要连发 30+ 次请求，不适合作为常规回归。

运行方式（显式指定，默认套件会跳过）：
    pytest scripts/test_b12_ratelimit.py -m slow
"""
from __future__ import annotations

import pytest

from common.client import ApiClient
from encap_api.auth_user_api import AuthApi

pytestmark = [pytest.mark.slow, pytest.mark.l4]

MAX_TRIES = 40


def test_login_throttled_after_30_attempts():
    """连续错误登录：第 31 次左右返回 429/42900，提示带剩余秒数。"""
    api = AuthApi(ApiClient(label="ratelimit"))
    hit = None
    for index in range(1, MAX_TRIES + 1):
        resp = api.login("no_such_user", "wrong-pass")
        if resp.status == 429:
            hit = (index, resp)
            break
        assert resp.status == 401, f"第 {index} 次应为 401，实际 {resp.status}：{resp.brief()}"

    assert hit is not None, f"连发 {MAX_TRIES} 次错误登录仍未触发限流（限流可能被关闭）"
    index, resp = hit

    assert index <= 31, f"限流触发过晚：第 {index} 次才 429（配置是 30/min）"
    assert resp.code == 42900
    assert "限流" in resp.message
    assert "秒" in resp.message, "应告知多久后可重试"


def test_throttle_does_not_block_authenticated_calls(teacher_client):
    """限流只作用于 auth 作用域：已登录用户的其他接口不受影响。"""
    api = AuthApi(teacher_client)
    resp = api.me()
    assert resp.status == 200, f"已登录用户被误伤：{resp.status} {resp.brief()}"
    assert resp.code == 0
