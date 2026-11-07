# -*- coding: utf-8 -*-
"""判分、成绩单与复核接口封装（GRAD）。"""
from __future__ import annotations

from .base import BaseApi


class GradingApi(BaseApi):
    def grade(self, aid: int, **payload):
        return self.post(f"/grading/attempts/{aid}/grade/", json=payload)

    def finalize(self, aid: int):
        return self.post(f"/grading/attempts/{aid}/finalize/", json={})

    def review(self, answer_id: int, **payload):
        return self.post(f"/grading/answers/{answer_id}/review/", json=payload)

    def queue(self, **params):
        return self.get("/grading/queue/", params=params)

    def exams(self):
        return self.get("/grading/exams/")

    def report(self, aid: int):
        return self.get(f"/grading/attempts/{aid}/report/")

    def scoreboard(self, **params):
        return self.get("/grading/scoreboard/", params=params)

    def wrong_book(self, **params):
        return self.get("/grading/wrong-book/", params=params)

    def calibration(self):
        return self.get("/grading/calibration/")

    def feedback_list(self, **params):
        return self.get("/grading/feedback/", params=params)

    def feedback_detail(self, fid: int):
        return self.get(f"/grading/feedback/{fid}/")
