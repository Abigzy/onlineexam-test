# -*- coding: utf-8 -*-
"""HTTP 客户端：统一信封解析 + 全量报文日志 + 耗时记录。

设计取舍：
  * 不抛异常表示"HTTP 4xx 失败"——测试要断言失败，异常会打断断言；
    只有网络层错误（连不上、超时）才抛，避免把环境问题伪装成用例失败。
  * 文件下载接口（xlsx/csv/html）不解析 JSON，保留原始 bytes 供文件头断言。
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from . import config

log = logging.getLogger("api")

if not log.handlers:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(config.LOG_DIR / f"api_{config.RUN_TS}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)


@dataclass
class ApiResponse:
    """一次调用的可断言结果。"""

    status: int
    body: Any
    elapsed: float
    method: str
    path: str
    raw: bytes = b""
    headers: dict = field(default_factory=dict)

    @property
    def code(self) -> int | None:
        if isinstance(self.body, dict):
            return self.body.get("code")
        return None

    @property
    def message(self) -> str:
        if isinstance(self.body, dict):
            return self.body.get("message") or ""
        return ""

    @property
    def data(self) -> Any:
        if isinstance(self.body, dict):
            return self.body.get("data")
        return None

    @property
    def text(self) -> str:
        if isinstance(self.body, (dict, list)):
            return json.dumps(self.body, ensure_ascii=False)
        return self.raw.decode("utf-8", errors="replace")

    def brief(self, limit: int = 600) -> str:
        text = self.text
        return text if len(text) <= limit else text[:limit] + "..."


class ApiClient:
    """带 token 的会话；一个角色一个实例。"""

    def __init__(self, base_url: str | None = None, token: str | None = None,
                 label: str = "anon"):
        self.base_url = (base_url or config.BASE_URL).rstrip("/")
        self.token = token
        self.label = label
        self.session = requests.Session()
        # 本机调试环境常带 HTTP_PROXY（如 WorkBuddy/抓包工具），
        # 会让本地请求走代理、以绝对 URI 发给 Django → 直接 404。
        # 接口自动化只打内网/本机，显式忽略系统代理。
        self.session.trust_env = False

    # ------------------------------------------------------------------
    def request(self, method: str, path: str, *, expect_json: bool = True,
                timeout: float | None = None, **kwargs) -> ApiResponse:
        url = config.url(path) if not path.startswith("http") else path
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.token:
            headers.setdefault("Authorization", f"Bearer {self.token}")
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")

        started = time.perf_counter()
        resp = self.session.request(method, url, headers=headers,
                                    timeout=timeout or config.TIMEOUT, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000, 1)

        if expect_json and "json" in (resp.headers.get("Content-Type") or ""):
            try:
                body: Any = resp.json()
            except ValueError:
                body = None
        else:
            body = resp.text if not expect_json else None

        result = ApiResponse(status=resp.status_code, body=body, elapsed=elapsed,
                             method=method.upper(), path=path, raw=resp.content,
                             headers=dict(resp.headers))
        log.info("[%s] %s %s -> %s code=%s %sms",
                 self.label, result.method, path, result.status, result.code, elapsed)
        # 响应全文放 DEBUG：控制台只留一行调用记录，完整报文仍进日志文件
        log.debug("  resp: %s", result.brief())
        return result

    # 便捷方法 ---------------------------------------------------------
    def get(self, path: str, **kw) -> ApiResponse:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw) -> ApiResponse:
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw) -> ApiResponse:
        return self.request("PUT", path, **kw)

    def patch(self, path: str, **kw) -> ApiResponse:
        return self.request("PATCH", path, **kw)

    def delete(self, path: str, **kw) -> ApiResponse:
        return self.request("DELETE", path, **kw)

    def download(self, path: str, **kw) -> ApiResponse:
        """文件类接口：不解析 JSON，断言 Content-Type 与文件头。"""
        return self.request("GET", path, expect_json=False, **kw)
