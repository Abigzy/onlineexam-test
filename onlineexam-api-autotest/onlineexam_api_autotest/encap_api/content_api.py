# -*- coding: utf-8 -*-
"""知识点、题库、试卷与组卷接口封装（KP / QUES / PAPER）。"""
from __future__ import annotations

from .base import BaseApi


class KnowledgeApi(BaseApi):
    def list(self, **params):
        return self.get("/knowledge-points/", params=params)

    def create(self, **payload):
        return self.post("/knowledge-points/", json=payload)

    def detail(self, kid: int):
        return self.get(f"/knowledge-points/{kid}/")

    def update(self, kid: int, partial: bool = True, **payload):
        method = self.patch if partial else self.put
        return method(f"/knowledge-points/{kid}/", json=payload)

    def remove(self, kid: int):
        return self.client.delete(self._p(f"/knowledge-points/{kid}/"))

    def tree(self, **params):
        return self.get("/knowledge-points/tree/", params=params)

    def questions(self, kid: int, **params):
        return self.get(f"/knowledge-points/{kid}/questions/", params=params)


class QuestionApi(BaseApi):
    def list(self, **params):
        return self.get("/questions/", params=params)

    def create(self, **payload):
        return self.post("/questions/", json=payload)

    def detail(self, qid: int):
        return self.get(f"/questions/{qid}/")

    def update(self, qid: int, partial: bool = True, **payload):
        method = self.patch if partial else self.put
        return method(f"/questions/{qid}/", json=payload)

    def remove(self, qid: int):
        return self.client.delete(self._p(f"/questions/{qid}/"))

    def ai_generate(self, **payload):
        return self.post("/questions/ai-generate/", json=payload)

    def batch(self, **payload):
        return self.post("/questions/batch/", json=payload)

    def ai_explain(self, qid: int, **payload):
        return self.post(f"/questions/{qid}/ai-explain/", json=payload)

    def ai_grade(self, qid: int, **payload):
        return self.post(f"/questions/{qid}/ai-grade/", json=payload)

    def import_file(self, file_path, **data):
        with open(file_path, "rb") as fh:
            return self.post("/questions/import/", files={"file": fh}, data=data)

    def export(self, file_format: str = "xlsx", **params):
        return self.get("/questions/export/",
                        params={"file_format": file_format, **params}, expect_json=False)

    def template(self):
        return self.get("/questions/import-template/", expect_json=False)

    def statistics(self, **params):
        return self.get("/questions/statistics/", params=params)

    def subjects(self):
        return self.get("/questions/subjects/")


class PaperApi(BaseApi):
    def list(self, **params):
        return self.get("/papers/", params=params)

    def create(self, **payload):
        return self.post("/papers/", json=payload)

    def detail(self, pid: int):
        return self.get(f"/papers/{pid}/")

    def update(self, pid: int, partial: bool = True, **payload):
        method = self.patch if partial else self.put
        return method(f"/papers/{pid}/", json=payload)

    def remove(self, pid: int):
        return self.client.delete(self._p(f"/papers/{pid}/"))

    def status(self, pid: int, status: str):
        return self.post(f"/papers/{pid}/status/", json={"status": status})

    def preview(self, pid: int):
        return self.get(f"/papers/{pid}/preview/")

    def analysis(self, pid: int, planned=None):
        params = {"planned": planned} if planned else {}
        return self.get(f"/papers/{pid}/analysis/", params=params)

    def export(self, pid: int, file_format: str = "html", **params):
        return self.get(f"/papers/{pid}/export/",
                        params={"file_format": file_format, **params}, expect_json=False)

    def clone(self, pid: int, title: str | None = None):
        return self.post(f"/papers/{pid}/clone/", json={"title": title} if title else {})

    def add_questions(self, pid: int, question_ids, score=None, strict=False):
        body = {"question_ids": question_ids, "strict": strict}
        if score is not None:
            body["score"] = score
        return self.post(f"/papers/{pid}/questions/", json=body)

    def remove_questions(self, pid: int, ids):
        return self.post(f"/papers/{pid}/remove-questions/", json={"ids": ids})

    def reorder(self, pid: int, ordered_ids):
        return self.post(f"/papers/{pid}/reorder/", json={"ordered_ids": ordered_ids})

    def set_scores(self, pid: int, items):
        return self.post(f"/papers/{pid}/scores/", json={"items": items})

    def ai_notes(self, pid: int, **payload):
        return self.post(f"/papers/{pid}/ai-notes/", json=payload)

    def ai_compose(self, **payload):
        return self.post("/papers/ai-compose/", json=payload)

    def random_compose(self, **payload):
        return self.post("/papers/random-compose/", json=payload)

    def pool(self, **params):
        return self.get("/papers/pool/", params=params)

    def statistics(self):
        return self.get("/papers/statistics/")
