# -*- coding: utf-8 -*-
"""教师·学情与作弊（模块 09）的四个页面。

实测约束（2026-11-05，读模板 + 浏览器探测，别再按用例文字猜）：

1. 四个页面都是「先 `innerHTML` 占位『加载中…』→ fetch → 整段重写」，
   等待判据必须落在**内容节点**上；只等容器出现会立刻假通过。
2. 学情看板 / 作弊看板的 `#exam-select` 由 `/analytics/exams/`、`/proctoring/exams/`
   异步填充，而且**只列有数据的考试**（前者要有人交卷，后者要有行为埋点），
   所以「选一场无人作答 / 无埋点的考试」在页面上根本不可达（UI-ANA-08 因此修订）。
3. 证据链页 `#risk-score` 的初始文本就是「—」，等它「非空」会假通过；
   必须等 `#risk-note` / `#signals-host` / `#timeline-host` 三处都不含「加载中」。
4. ECharts 只在有数据时生成 canvas，数据不足时 `emptyChart()` 用文案替换图表。
5. 切考试 / 勾选过滤都是异步重写 DOM：用「给首个子元素打标记 → 等标记消失」
   证明确实重渲染过（docs/05 §4 第 32 条同款做法）。
"""
from common.base_page import BasePage


def _has_option(page, exam_id):
    return bool(page.js(
        "return !!document.querySelector('#exam-select option[value=\"%s\"]');" % exam_id))


def _rewritten(page, host_id):
    """保存前打的标记是否已随 innerHTML 重写而消失。"""
    return not page.js(
        "return !!document.querySelector('#%s [data-uiat-old]');" % host_id)


class AnalyticsDashboardPage(BasePage):
    """班级学情看板：KPI + 四张 ECharts 图 + 排名。"""
    path = "/analytics/"
    ready = "#dashboard-host"

    L = {
        "host": "#dashboard-host",
        "exam_select": "#exam-select",
        "class_select": "#class-select",
        "refresh": "#btn-refresh",
        "kpi": "#dashboard-host .kpi-value",
    }

    def wait_loaded(self, timeout=None):
        return self.wait_for(
            lambda d: bool((self.js_text(self.L["host"]) or "").strip())
            and "加载中" not in self.js_text(self.L["host"]),
            timeout=timeout, message="学情看板一直停在加载中")

    def open_exam(self, exam_id):
        """`?exam_id=` 是页面原生支持的直达参数（从成绩单跳过来时用）。"""
        self.open_raw("/analytics/?exam_id=%s" % exam_id)
        self.wait_ready()
        return self.wait_loaded()

    def text(self):
        return self.js_text(self.L["host"])

    def kpi_values(self):
        return self.js_texts(self.L["kpi"])

    def canvas_count(self):
        return int(self.js("return document.querySelectorAll('canvas').length;") or 0)

    def exam_values(self):
        return self.js(
            "return [...document.querySelectorAll('#exam-select option')]"
            ".map(o=>o.value).filter(v=>v && /^[0-9]+$/.test(v));") or []

    def select_exam(self, exam_id):
        """切考试并等报告**真的重渲染**（内容可能碰巧相同，不拿文本做等待条件）。"""
        self.wait_for(lambda d: _has_option(self, exam_id),
                      message="学情看板下拉里没有考试 %s" % exam_id)
        self.js("const h=document.getElementById('dashboard-host');"
                "if(h.firstElementChild) h.firstElementChild.setAttribute('data-uiat-old','1');"
                "const s=document.getElementById('exam-select');"
                "s.value=String(arguments[0]);s.dispatchEvent(new Event('change'));", exam_id)
        return self.wait_for(
            lambda d: _rewritten(self, "dashboard-host")
            and "加载中" not in self.js_text(self.L["host"])
            and bool(self.js_text(self.L["host"]).strip()),
            message="切换考试后学情看板没有重新渲染")


class StudentAnalyticsPage(BasePage):
    """单个学生的学情详情：掌握度 / 趋势 / AI 诊断。"""
    path = "/analytics/students/{student_id}/"
    ready = "#report-host"

    L = {
        "meta": "#student-meta",
        "host": "#report-host",
        "ai": ".ai-panel",
        "trend": "#chart-trend",
        "diagnose": "#btn-diagnose",
    }

    def wait_loaded(self, timeout=None):
        return self.wait_for(
            lambda d: all("加载中" not in self.js_text(self.L[k]) for k in ("meta", "host"))
            and bool(self.js_text(self.L["host"]).strip()),
            timeout=timeout, message="学生学情详情一直停在加载中")

    def meta(self):
        return self.js_text(self.L["meta"])

    def text(self):
        return self.js_text(self.L["host"])

    def ai_text(self):
        """AI 诊断区：有报告时是诊断正文，没生成过则是可读的空态引导。"""
        return self.js_text(self.L["ai"])

    def canvas_count(self):
        return int(self.js("return document.querySelectorAll('canvas').length;") or 0)


class ProctoringDashboardPage(BasePage):
    """作弊看板：6 张 KPI + 风险列表 + 规则说明 + 只看嫌疑过滤。"""
    path = "/proctoring/"
    ready = "#kpi-row"

    L = {
        "kpi": "#kpi-row .kpi-value",
        "list": "#list-host",
        "rows": "#list-host tbody tr",
        "risk_badge": "#list-host tbody tr .risk-badge",
        "rules": "#rules-host .rule-row",
        "exam_select": "#exam-select",
        "only": "#only-suspicious",
        "meta": "#list-meta",
        "alert": "#alert-host",
    }

    def wait_loaded(self, timeout=None):
        return self.wait_for(
            lambda d: self.count(self.L["kpi"]) >= 6
            and all((v or "").strip() for v in self.js_texts(self.L["kpi"]))
            and "加载中" not in self.js_text(self.L["list"])
            and self.count(self.L["rules"]) >= 1,
            timeout=timeout, message="作弊看板 KPI / 列表 / 规则没有加载完")

    def kpi_values(self):
        return self.js_texts(self.L["kpi"])

    def row_count(self):
        return self.count(self.L["rows"])

    def risk_labels(self):
        return self.js_texts(self.L["risk_badge"])

    def rules_count(self):
        return self.count(self.L["rules"])

    def rules_text(self):
        return self.js_text("#rules-host")

    def list_text(self):
        return self.js_text(self.L["list"])

    def select_exam(self, exam_id):
        self.wait_for(lambda d: _has_option(self, exam_id),
                      message="作弊看板下拉里没有考试 %s（可能没有行为埋点）" % exam_id)
        self.js("const h=document.getElementById('list-host');"
                "if(h.firstElementChild) h.firstElementChild.setAttribute('data-uiat-old','1');"
                "const s=document.getElementById('exam-select');"
                "s.value=String(arguments[0]);s.dispatchEvent(new Event('change'));", exam_id)
        return self.wait_for(
            lambda d: _rewritten(self, "list-host")
            and "加载中" not in self.js_text(self.L["list"]),
            message="切换考试后作弊列表没有重新渲染")

    def set_only_suspicious(self, on=True):
        """勾选/取消「只看嫌疑」：change 触发 `loadReport(only_suspicious=...)`。"""
        self.js("const h=document.getElementById('list-host');"
                "if(h.firstElementChild) h.firstElementChild.setAttribute('data-uiat-old','1');"
                "const c=document.getElementById('only-suspicious');"
                "c.checked=arguments[0];c.dispatchEvent(new Event('change'));", bool(on))
        return self.wait_for(
            lambda d: _rewritten(self, "list-host")
            and "加载中" not in self.js_text(self.L["list"]),
            message="切换「只看嫌疑」后列表没有重新渲染")

    def canvas_count(self):
        return int(self.js("return document.querySelectorAll('canvas').length;") or 0)


class ProctoringEvidencePage(BasePage):
    """单份作答的作弊证据链：风险分 / 命中规则 / 行为时间线。"""
    path = "/proctoring/attempts/{attempt_id}/evidence/"
    ready = "#risk-score"

    L = {
        "score": "#risk-score",
        "note": "#risk-note",
        "signals": "#signals-host",
        "signal_cards": ".signal-card",
        "signal_meta": "#signal-meta",
        "timeline": "#timeline-host",
        "timeline_meta": "#timeline-meta",
        "alert": "#alert-host",
    }

    def wait_loaded(self, timeout=None):
        # 不能只等 #risk-score：它初始就是「—」，会立刻假通过（探测踩过）
        return self.wait_for(
            lambda d: all("加载中" not in self.js_text(self.L[k])
                          for k in ("note", "signals", "timeline"))
            and bool(self.js_text(self.L["score"]).strip()),
            timeout=timeout, message="证据链三段（风险分/规则/时间线）没有加载完")

    def score(self):
        return self.js_text(self.L["score"])

    def note(self):
        return self.js_text(self.L["note"])

    def signal_count(self):
        return self.count(self.L["signal_cards"])

    def signal_text(self):
        return self.js_text(self.L["signals"])

    def timeline_text(self):
        return self.js_text(self.L["timeline"])

    def timeline_meta(self):
        return self.js_text(self.L["timeline_meta"])
