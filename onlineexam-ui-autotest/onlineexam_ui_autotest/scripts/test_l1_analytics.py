# -*- coding: utf-8 -*-
"""L1 教师·学情与作弊：8 条（docs/03 UI-ANA-01 ~ 08，P1 4 / P2 4）。

数据策略：`proctor_scene` 每条用例现造一场考试，内含两份作答 ——
    ① 上报 6 次切屏 + 1 次粘贴并已判分（风险分 73 / 高度可疑 / 3 条规则 / 7 条时间线）；
    ② 不上报行为的正常对照（风险 0）。
这样「只看嫌疑」过滤、"证据链三段齐全"都有确定的数据，不依赖演示库里
274 场 `at_*` 历史考试，也不受它们默认排在下拉第一行的影响。

两条按实测修订的用例（详见用例 docstring 与 docs/05 §5.1）：
    UI-ANA-02 切换目标改为「已有出分成绩的考试」，保证统计值确实变化；
    UI-ANA-08 「无人作答的考试」在页面上根本不可达，改为验证「有交卷但未出分」
              时的空态/占位降级，并核对数据口径。
"""
import allure
import pytest

from pages.analytics_pages import (
    AnalyticsDashboardPage,
    ProctoringDashboardPage,
    ProctoringEvidencePage,
    StudentAnalyticsPage,
)

P1 = pytest.mark.p1
P2 = pytest.mark.p2
FEATURE = "09 教师·学情与作弊"


@allure.feature(FEATURE)
class TestAnalytics:
    """学情看板与学生学情详情。"""

    @P1
    @allure.story("UI-ANA-01 学情看板图表渲染")
    @allure.severity(allure.severity_level.NORMAL)
    def test_analytics_charts(self, as_teacher, proctor_scene):
        page = AnalyticsDashboardPage(as_teacher).open_exam(proctor_scene["exam_id"])

        assert page.canvas_count() >= 1, "学情看板没有渲染出 ECharts 画布"
        assert "加载中" not in page.text(), "看板残留「加载中…」"
        assert "Traceback" not in as_teacher.page_source, "页面泄露了服务端堆栈"
        assert page.console_errors() == [], "看板出现 JS 错误：%s" % page.console_errors()[:2]

    @P1
    @allure.story("UI-ANA-02 切换考试后学情数据刷新")
    @allure.severity(allure.severity_level.NORMAL)
    def test_switch_exam_refreshes(self, as_teacher, sessions, proctor_scene):
        eid = proctor_scene["exam_id"]
        page = AnalyticsDashboardPage(as_teacher).open_exam(eid)
        before = page.text()

        # 只挑「已有出分成绩」的考试：随便切到另一场 1 份未出分作答的 UIAT_ 考试，
        # KPI / 排名文本可能一模一样，断言"内容变了"就会假红。
        rows = sessions["teacher"].get("/analytics/exams/").get("results") or []
        target = next((str(r["id"]) for r in rows
                       if str(r["id"]) != str(eid) and (r.get("graded_total") or 0) >= 1), None)
        assert target, "库里没有另一场已出分的考试，无法验证切换刷新"

        page.select_exam(target)
        after = page.text()

        assert after != before, "切换考试后看板内容没有变化（可能没重新拉数据）"
        assert "加载中" not in after, "切换后残留「加载中…」"
        assert page.console_errors() == [], "切换考试后出现 JS 错误：%s" % page.console_errors()[:2]

    @P1
    @allure.story("UI-ANA-03 学生学情详情页诊断区有文案")
    @allure.severity(allure.severity_level.NORMAL)
    def test_student_diagnosis(self, as_teacher, proctor_scene):
        page = StudentAnalyticsPage(as_teacher).open(
            student_id=proctor_scene["student_id"]).wait_loaded()

        assert page.meta().strip() and "加载中" not in page.meta(), "学生信息没渲染"
        ai = page.ai_text()
        assert "AI 学情诊断" in ai, "诊断区标题缺失：%r" % ai[:80]
        assert len(ai) > 40, "诊断区只有标题，没有可读正文（AI 报告或生成引导）"
        assert page.canvas_count() >= 1 or "还没有已判分的答题记录" in page.text(), \
            "掌握度/趋势既没有图表也没有明确空态"
        assert "Traceback" not in as_teacher.page_source
        assert page.console_errors() == []

    @P2
    @allure.story("UI-ANA-08 学情看板数据不足时的空态与降级")
    @allure.severity(allure.severity_level.MINOR)
    def test_analytics_empty_state(self, as_teacher, proctor_scene):
        """用例原文是「选一场无人作答的考试看空态」——实测该场景在页面上不可达：

        - `/analytics/exams/` 只列**有人交卷**的考试，无人作答的考试不在下拉里，
          `?exam_id=` 也只会 fallback 到 rows[0]；
        - `#class-select` 里 52 个班级对当前教师调用 report 接口**全部 404**
          （教师没有可管理班级，见 OBS-04），选了只会显示错误，不是空态。

        改成验证同类且更有价值的降级：**有交卷但尚未出分**时，看板用
        「暂无 / —」给出可读空态与占位、不残留加载中、零 JS 错误。
        """
        page = AnalyticsDashboardPage(as_teacher).open_exam(proctor_scene["exam_id"])
        text = page.text()

        assert "加载中" not in text, "图表区残留「加载中…」"
        assert "暂无" in text, "数据不足时没有给出「暂无…」空态文案：%r" % text[:120]
        assert "—" in text, "未出分的统计卡没有用「—」占位：%r" % text[:120]
        assert page.console_errors() == [], "空态场景出现 JS 错误：%s" % page.console_errors()[:2]


@allure.feature(FEATURE)
class TestProctoring:
    """作弊看板、证据链、规则目录。"""

    @P1
    @allure.story("UI-ANA-04 作弊看板 KPI 与列表渲染")
    @allure.severity(allure.severity_level.NORMAL)
    def test_proctor_kpi_and_list(self, as_teacher, proctor_scene):
        page = ProctoringDashboardPage(as_teacher).open().wait_loaded()
        page.select_exam(proctor_scene["exam_id"])
        page.wait_loaded()

        kpis = page.kpi_values()
        assert len(kpis) >= 6, "KPI 卡数量不足 6：%d" % len(kpis)
        assert all((v or "").strip() for v in kpis), "有 KPI 卡没有值：%s" % kpis
        assert page.row_count() >= 2, \
            "造数场景应有一份高风险 + 一份正常作答，实际 %d 行" % page.row_count()
        assert "加载中" not in page.list_text(), "列表残留「加载中…」"
        assert page.rules_count() >= 5, "规则说明区没有渲染规则条目"
        assert page.console_errors() == []

    @P2
    @allure.story("UI-ANA-05 作弊证据链三段内容齐全")
    @allure.severity(allure.severity_level.MINOR)
    def test_evidence_chain(self, as_teacher, proctor_scene):
        # 注意：#risk-score 初始就是「—」，PO 的 wait_loaded() 等的是
        # 风险说明 / 命中规则 / 时间线三处都不含「加载中」（探测踩过假等待）。
        page = ProctoringEvidencePage(as_teacher).open(
            attempt_id=proctor_scene["flagged_attempt"]).wait_loaded()

        score = page.score().strip()
        assert score.replace(".", "", 1).isdigit(), "风险分不是数值：%r" % score
        assert page.note().strip() and page.note() != "加载中…", "风险等级/说明缺失"

        assert page.signal_count() >= 1, "命中规则列表为空"
        sig = page.signal_text()
        assert "证据：" in sig and "切屏次数超限" in sig, \
            "命中规则缺少名称 / 理由 / 证据任一项：%r" % sig[:160]

        timeline = page.timeline_text()
        assert timeline.strip() and "加载中" not in timeline, "时间线没有事件记录"
        assert any(ch.isdigit() for ch in page.timeline_meta()), \
            "时间线条数没有数字：%r" % page.timeline_meta()
        assert page.console_errors() == []

    @P2
    @allure.story("UI-ANA-06 作弊看板「只看嫌疑」过滤")
    @allure.severity(allure.severity_level.MINOR)
    def test_only_suspicious_filter(self, as_teacher, proctor_scene):
        page = ProctoringDashboardPage(as_teacher).open().wait_loaded()
        page.select_exam(proctor_scene["exam_id"])
        before = page.row_count()
        assert before >= 2, "造数场景应有高风险 + 正常两份作答，实际 %d 行" % before

        page.set_only_suspicious(True)
        after = page.row_count()
        labels = page.risk_labels()

        assert 0 < after <= before, "过滤后行数异常：%d → %d" % (before, after)
        assert labels, "过滤后没有风险等级徽章"
        assert all("可疑" in x for x in labels), \
            "「只看嫌疑」结果里混入了非可疑考生：%s" % labels
        assert not any("正常" in x for x in labels), "过滤结果里仍有「正常」考生"

        page.set_only_suspicious(False)
        assert page.row_count() == before, \
            "取消勾选后没有恢复：%d → %d" % (before, page.row_count())

    @P2
    @allure.story("UI-ANA-07 规则说明区渲染规则条目")
    @allure.severity(allure.severity_level.MINOR)
    def test_rules_catalog(self, as_teacher):
        page = ProctoringDashboardPage(as_teacher).open().wait_loaded()

        assert page.rules_count() >= 5, \
            "RULE_CATALOG 应有 9 条规则，实际渲染 %d 条" % page.rules_count()
        text = page.rules_text()
        assert "加载中" not in text, "规则区残留「加载中…」"
        assert "触发条件" in text and "切屏次数超限" in text, "规则表头/名称缺失"
        thresholds = page.js_texts("#rules-host .rule-row td:nth-child(2)")
        assert len(thresholds) >= 5 and all((t or "").strip() for t in thresholds), \
            "有规则缺少阈值说明：%s" % thresholds[:3]
        assert page.console_errors() == []
