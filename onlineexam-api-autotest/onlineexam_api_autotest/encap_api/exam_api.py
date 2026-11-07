# -*- coding: utf-8 -*-
"""考试与作答接口封装（EXAM / ATT）。"""
from __future__ import annotations

from .base import BaseApi


class ExamApi(BaseApi):
    def list(self, **params):
        return self.get("/exams/", params=params)

    def create(self, **payload):
        return self.post("/exams/", json=payload)

    def detail(self, eid: int):
        return self.get(f"/exams/{eid}/")

    def update(self, eid: int, partial: bool = True, **payload):
        method = self.patch if partial else self.put
        return method(f"/exams/{eid}/", json=payload)

    def remove(self, eid: int):
        return self.client.delete(self._p(f"/exams/{eid}/"))

    def status(self, eid: int, status: str):
        return self.post(f"/exams/{eid}/status/", json={"status": status})

    def start(self, eid: int, **payload):
        return self.post(f"/exams/{eid}/start/", json=payload)

    def overview(self, eid: int):
        return self.get(f"/exams/{eid}/overview/")

    def attempts(self, eid: int, **params):
        return self.get(f"/exams/{eid}/attempts/", params=params)

    def statistics(self):
        return self.get("/exams/statistics/")

    def candidates(self, **params):
        return self.get("/exams/candidates/", params=params)


class AttemptApi(BaseApi):
    def list(self, **params):
        return self.get("/attempts/", params=params)

    def detail(self, aid: int):
        return self.get(f"/attempts/{aid}/")

    def paper(self, aid: int):
        return self.get(f"/attempts/{aid}/paper/")

    def answers(self, aid: int):
        return self.get(f"/attempts/{aid}/answers/")

    def save_answers(self, aid: int, items):
        return self.post(f"/attempts/{aid}/answers/", json={"items": items})

    def save(self, aid: int, **payload):
        return self.post(f"/attempts/{aid}/save/", json=payload)

    def heartbeat(self, aid: int, client_remaining: int | None = None):
        body = {} if client_remaining is None else {"client_remaining": client_remaining}
        return self.post(f"/attempts/{aid}/heartbeat/", json=body)

    def behavior(self, aid: int, events):
        return self.post(f"/attempts/{aid}/behavior/", json={"events": events})

    def submit(self, aid: int, **payload):
        return self.post(f"/attempts/{aid}/submit/", json=payload)

    def result(self, aid: int):
        return self.get(f"/attempts/{aid}/result/")
