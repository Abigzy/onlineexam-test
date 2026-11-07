# -*- coding: utf-8 -*-
"""接口封装基类：只负责拼路径与转发，不做断言。"""
from __future__ import annotations

from common.client import ApiClient


class BaseApi:
    prefix = "/api/v1"

    def __init__(self, client: ApiClient):
        self.client = client

    def _p(self, path: str) -> str:
        if path.startswith("/api"):
            return path
        return f"{self.prefix}/{path.lstrip('/')}"

    def get(self, path: str, **kw):
        return self.client.get(self._p(path), **kw)

    def post(self, path: str, **kw):
        return self.client.post(self._p(path), **kw)

    def put(self, path: str, **kw):
        return self.client.put(self._p(path), **kw)

    def patch(self, path: str, **kw):
        return self.client.patch(self._p(path), **kw)

    def delete(self, path: str, **kw):
        return self.client.delete(self._p(path), **kw)
