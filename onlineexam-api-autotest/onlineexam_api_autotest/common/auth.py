# -*- coding: utf-8 -*-
"""登录与 token 缓存。

为什么要落盘缓存：
  * `auth` 限流 30/min，一套用例跑两遍就会 429；
  * access 有效期 2 小时，回归批次内完全可复用。
缓存按 username 存，校验 exp（剩余 <60s 视为过期）；
换账号/换环境只要删 data/token_cache.json。
"""
from __future__ import annotations

import base64
import json
import time

from common import config
from common.client import ApiClient

CACHE_FILE = config.DATA_DIR / "token_cache.json"


class AuthError(RuntimeError):
    pass


def _decode_exp(token: str) -> int:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return int(data.get("exp", 0))
    except Exception:  # noqa: BLE001
        return 0


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _cached_token(username: str) -> str | None:
    token = _load_cache().get(username)
    if token and _decode_exp(token) - time.time() > 60:
        return token
    return None


def _remember(username: str, token: str) -> None:
    cache = _load_cache()
    cache[username] = token
    _save_cache(cache)


def login_user(username: str, password: str, label: str = "") -> ApiClient:
    """按用户名登录；命中未过期缓存则直接复用。"""
    label = label or username
    token = _cached_token(username)
    if token:
        return ApiClient(token=token, label=label)

    anon = ApiClient(label=f"{label}:login")
    resp = anon.post("/api/v1/auth/login/", json={
        "username": username, "password": password,
    })
    if resp.status != 200 or resp.code != 0:
        raise AuthError(f"{username} 登录失败：HTTP {resp.status} code={resp.code} {resp.message}")
    token = (resp.data or {}).get("access")
    if not token:
        raise AuthError(f"{username} 登录成功但未返回 access")
    _remember(username, token)
    return ApiClient(token=token, label=label)


def login(alias: str) -> ApiClient:
    """按账号别名（data/accounts.yaml）登录。"""
    acc = config.account(alias)
    return login_user(acc["username"], acc["password"], label=alias)


class TokenPool:
    """按别名复用客户端，避免同一进程内重复登录。"""

    def __init__(self):
        self._clients: dict[str, ApiClient] = {}

    def get(self, alias: str) -> ApiClient:
        if alias not in self._clients:
            self._clients[alias] = login(alias)
        return self._clients[alias]

    def reset(self, alias: str | None = None):
        if alias is None:
            self._clients.clear()
        else:
            self._clients.pop(alias, None)
