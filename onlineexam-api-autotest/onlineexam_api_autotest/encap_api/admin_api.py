# -*- coding: utf-8 -*-
"""班级、AI 适配层与管理端接口封装（CLS / AI / SYS）。"""
from __future__ import annotations

from .base import BaseApi


class ClassroomApi(BaseApi):
    def list(self, **params):
        return self.get("/classrooms/", params=params)

    def create(self, **payload):
        return self.post("/classrooms/", json=payload)

    def options(self):
        return self.get("/classrooms/options/")

    def detail(self, cid: int):
        return self.get(f"/classrooms/{cid}/")

    def update(self, cid: int, partial: bool = True, **payload):
        method = self.patch if partial else self.put
        return method(f"/classrooms/{cid}/", json=payload)

    def remove(self, cid: int):
        return self.client.delete(self._p(f"/classrooms/{cid}/"))

    def members(self, cid: int):
        return self.get(f"/classrooms/{cid}/students/")

    def add_students(self, cid: int, **payload):
        return self.post(f"/classrooms/{cid}/students/", json=payload)

    def remove_students(self, cid: int, student_ids):
        return self.client.request(
            "DELETE", self._p(f"/classrooms/{cid}/students/"),
            json={"student_ids": student_ids},
        )


class AiApi(BaseApi):
    def providers(self):
        return self.get("/ai/providers/")

    def test_connection(self, provider: str | None = None):
        return self.post("/ai/test-connection/",
                         json={"provider": provider} if provider else {})

    def chat(self, **payload):
        return self.post("/ai/chat/", json=payload)

    def usage(self, **params):
        return self.get("/ai/usage/", params=params)

    def logs(self, **params):
        return self.get("/ai/logs/", params=params)


class SystemApi(BaseApi):
    def overview(self):
        return self.get("/system/overview/")
