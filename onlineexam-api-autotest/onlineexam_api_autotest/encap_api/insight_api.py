# -*- coding: utf-8 -*-
"""学情、推荐与监考接口封装（AN / REC / PRO）。"""
from __future__ import annotations

from .base import BaseApi


class AnalyticsApi(BaseApi):
    def exams(self):
        return self.get("/analytics/exams/")

    def exam_report(self, eid: int, **params):
        return self.get(f"/analytics/exams/{eid}/report/", params=params)

    def exam_questions(self, eid: int, **params):
        return self.get(f"/analytics/exams/{eid}/questions/", params=params)

    def mastery(self, sid: int, **params):
        return self.get(f"/analytics/students/{sid}/mastery/", params=params)

    def trend(self, sid: int, **params):
        return self.get(f"/analytics/students/{sid}/trend/", params=params)

    def report(self, sid: int, **params):
        return self.get(f"/analytics/students/{sid}/report/", params=params)

    def diagnosis(self, sid: int, **payload):
        return self.post(f"/analytics/students/{sid}/diagnosis/", json=payload)


class RecommendApi(BaseApi):
    def practice(self, sid: int, **params):
        return self.get(f"/recommend/students/{sid}/practice/", params=params)

    def practice_ai(self, sid: int, **payload):
        return self.post(f"/recommend/students/{sid}/practice/", json=payload)


class ProctoringApi(BaseApi):
    def exams(self):
        return self.get("/proctoring/exams/")

    def report(self, eid: int, **params):
        return self.get(f"/proctoring/exams/{eid}/report/", params=params)

    def evidence(self, aid: int):
        return self.get(f"/proctoring/attempts/{aid}/evidence/")

    def rules(self):
        return self.get("/proctoring/rules/")
