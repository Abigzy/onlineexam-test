# -*- coding: utf-8 -*-
"""L1/L2 学生·学情练习：13 条（docs/03 UI-STU-02 ~ 14，P0 1 / P1 8 / P2 4）。

`UI-STU-01`（练习页加载）已在 L0 冒烟覆盖，本批不重复。

造数策略（三条实测事实决定的）：
  1. 演示账号 student 有 2039 条作答 / 200 条错题，**空态走不到**；
     空态用例（STU-11 / 12）用 `bare_student`（现造的、没有学科班的新生）。
  2. 每日练习一次只给 6 题且**题型混合**，可能全是主观题；
     要「点选项」的用例用 `practice_student`（造数时已按接口预检出客观题）。
  3. 错题本、学情页要**真实数据**才能验出内容，沿用演示账号（只读，不写库）。
"""
import re
import time

import allure
import pytest

import config
from common.api_client import ApiSession
from pages.student_pages import (HomePage, MyAnalyticsPage, PracticePage,
                                 WrongBookPage)

P0 = pytest.mark.p0
P1 = pytest.mark.p1
P2 = pytest.mark.p2
FEATURE = "03 学生·学情练习"


def login_as(drv, username, password=None):
    """把指定账号的 sessionid 注入浏览器（不销毁服务端会话）。"""
    api = ApiSession(username, password or config.PASSWORD)
    host = config.BASE_URL.split("//")[1].split(":")[0]
    drv.get(config.BASE_URL + "/login/")
    drv.delete_all_cookies()
    drv.add_cookie({"name": "sessionid", "value": api.session_id,
                    "domain": host, "path": "/"})
    return drv


@pytest.fixture()
def as_practice_student(driver, practice_student):
    return login_as(driver, practice_student["username"], practice_student["password"])


@pytest.fixture()
def as_bare_student(driver, bare_student):
    return login_as(driver, bare_student["username"], bare_student["password"])


@allure.feature(FEATURE)
class TestPracticeInteraction:
    """每日练习的作答交互：判分、看答案、再做一次、换一批、AI 理由。"""

    @P1
    @allure.story("UI-STU-03 练习单选题提交后给出判分结论")
    @allure.severity(allure.severity_level.NORMAL)
    def test_submit_objective(self, as_practice_student):
        page = PracticePage(as_practice_student).open()
        page.wait_settled()
        index = page.first_objective_index()
        assert index >= 0, "这组练习没有带选项的题卡，用例前置不成立：%s" % page.qids()

        assert page.submit_count(index) == 1, "作答前应恰好有一个「提交作答」按钮"
        page.pick_option(index, 0)
        page.submit(index)

        result = page.result_text(index)
        assert ("答对了" in result) or ("答错了" in result), \
            "提交后没有出现判分结论：%r" % result[:120]
        assert page.submit_count(index) == 0, \
            "判分后「提交作答」应消失（结果区自带按钮），实际仍存在"
        assert not page.answer_visible(index), "判分后答案区不应自动展开"

    @P1
    @allure.story("UI-STU-04 提交后可查看答案与解析")
    @allure.severity(allure.severity_level.NORMAL)
    def test_view_answer_after_submit(self, as_practice_student):
        page = PracticePage(as_practice_student).open()
        page.wait_settled()
        index = page.first_objective_index()
        assert index >= 0, "没有带选项的题卡"

        disabled_before = page.js(
            "const card=[...document.querySelectorAll('.practice-card')][%d];"
            "return card.querySelector('[data-toggle-answer]').disabled;" % index)
        assert disabled_before is True, "未作答时「查看答案」不应可点"
        assert not page.answer_visible(index), "未作答时答案区就是展开的"

        page.pick_option(index, 0)
        page.submit(index)
        disabled_after = page.js(
            "const card=[...document.querySelectorAll('.practice-card')][%d];"
            "return card.querySelector('[data-toggle-answer]').disabled;" % index)
        assert disabled_after is False, "判分后「查看答案」仍然不可点"

        page.toggle_answer(index)
        page.wait_for(lambda d: page.answer_visible(index), message="点开后答案区没有展示")
        text = page.answer_text(index)
        assert "参考答案" in text and len(text.strip()) > 10, \
            "答案区没有正确答案文本：%r" % text[:120]
        assert "收起" in page.toggle_label(index), \
            "展开后按钮文案没有变成「收起答案与解析」：%r" % page.toggle_label(index)

        page.toggle_answer(index)
        page.wait_for(lambda d: not page.answer_visible(index), message="再次点击没有收起答案")

    @P1
    @allure.story("UI-STU-05 「再做一次」重置作答与结论")
    @allure.severity(allure.severity_level.NORMAL)
    def test_redo(self, as_practice_student):
        page = PracticePage(as_practice_student).open()
        page.wait_settled()
        index = page.first_objective_index()
        assert index >= 0, "没有带选项的题卡"

        page.pick_option(index, 0)
        page.submit(index)
        assert page.result_text(index), "前置：先要有一份判分结论"

        page.redo(index)
        assert page.result_text(index) == "", "「再做一次」后判分结论没有清空"
        assert page.picked_count(index) == 0, "「再做一次」后选项选中态没有清除"
        assert page.submit_count(index) == 1, "「再做一次」后「提交作答」没有恢复"

    @P1
    @allure.story("UI-STU-06 「换一批」重新拉取练习题")
    @allure.severity(allure.severity_level.NORMAL)
    def test_shuffle(self, as_practice_student):
        page = PracticePage(as_practice_student).open()
        page.wait_settled()
        assert page.card_count() >= 1, "前置：练习页没有题卡"

        before, after = page.shuffle()
        assert page.card_count() >= 1, "换一批后题卡空了"
        assert set(before) != set(after), "换一批后题目完全没变：%s" % before[:5]
        host = page.host_text()
        for bad in ("系统繁忙", "请求失败", "加载中"):
            assert bad not in host, "换一批后页面出现异常文案「%s」" % bad

    @P2
    @allure.story("UI-STU-13 练习页 AI 优化理由按钮不报错")
    @allure.severity(allure.severity_level.MINOR)
    def test_ai_reason(self, as_practice_student):
        page = PracticePage(as_practice_student).open()
        page.wait_settled()

        banner = page.ai_reason()
        assert len(banner) > 10, "AI 理由区没有内容：%r" % banner
        assert ("理由" in banner) or ("说明" in banner) or ("推荐" in banner), \
            "理由区文案不符合预期：%r" % banner[:120]
        state = page.ai_button_state()
        assert state.get("disabled") is False, "AI 按钮停在加载中（没有恢复）"
        assert page.card_count() >= 1, "AI 理由刷新后题卡消失了"
        assert page.console_errors() == [], \
            "AI 理由按钮触发控制台错误：%s" % page.console_errors()[:2]


@allure.feature(FEATURE)
class TestAnalytics:
    """我的学情：图表、区块、导航入口、1280 视口。"""

    @P0
    @allure.story("UI-STU-02 我的学情页图表正常渲染")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_analytics_charts(self, as_student):
        page = MyAnalyticsPage(as_student).open()
        page.wait_loaded()

        assert page.canvas_count() >= 1, \
            "学情页一个 canvas 都没有，图表没渲染（KPI：%s）" % page.kpi_labels()
        host = page.host_text()
        assert "加载中" not in host, "学情页残留「加载中」"
        assert "Traceback" not in as_student.page_source, "学情页泄露了服务端堆栈"
        assert len(page.kpi_labels()) >= 4, "KPI 卡数量异常：%s" % page.kpi_labels()

    @P1
    @allure.story("UI-STU-09 学情页薄弱知识点区块有内容或明确空态")
    @allure.severity(allure.severity_level.NORMAL)
    def test_weak_points_block(self, as_student):
        page = MyAnalyticsPage(as_student).open()
        page.wait_loaded()

        text = page.section_text("薄弱知识点")
        assert text, "没有找到「薄弱知识点」区块"
        assert "加载中" not in text, "薄弱知识点区块停在加载中"
        has_rows = "正确率" in text
        has_empty = "暂无" in text or "数据不足" in text
        assert has_rows or has_empty, \
            "薄弱知识点区块既没有条目也没有空态文案：%r" % text[:160]
        if has_rows:
            assert re.search(r"\d+(\.\d+)?%", text), \
                "薄弱知识点条目没有掌握度百分比：%r" % text[:160]

    @P1
    @allure.story("UI-STU-10 从导航进入我的学情标题与内容正确")
    @allure.severity(allure.severity_level.NORMAL)
    def test_nav_to_analytics(self, as_student):
        HomePage(as_student).open()
        as_student.execute_script("""
            const link=[...document.querySelectorAll('#mainNav a')]
              .find(a=>(a.innerText||'').trim()==='我的学情');
            link.click();""")
        page = MyAnalyticsPage(as_student)
        page.wait_url("/analytics/me/")
        page.wait_loaded()

        assert "我的学情" in as_student.title, "<title> 不含「我的学情」：%s" % as_student.title
        titles = " ".join(page.section_titles())
        for keyword in ("掌握度", "趋势", "薄弱"):
            assert keyword in titles, "页面缺少「%s」区块：%s" % (keyword, titles)
        assert "Traceback" not in as_student.page_source, "页面泄露了服务端堆栈"

    @P2
    @allure.story("UI-STU-14 1280×800 视口下学情页主要区块可见")
    @allure.severity(allure.severity_level.MINOR)
    def test_viewport_1280(self, as_student):
        as_student.set_window_size(1280, 800)
        page = MyAnalyticsPage(as_student).open()
        page.wait_loaded()

        metrics = page.scroll_metrics()
        assert metrics["scrollW"] <= metrics["clientW"] + 1, \
            "1280 视口出现横向溢出：scrollWidth=%s clientWidth=%s" % (
                metrics["scrollW"], metrics["clientW"])
        assert len(page.kpi_labels()) >= 4, "1280 视口下 KPI 卡缺失"
        assert page.chart_boxes_visible() >= 3, \
            "1280 视口下有图表容器尺寸异常（<100x100）：%s" % page.chart_boxes_visible()
        assert page.canvas_count() >= 1, "1280 视口下图表没有渲染"


@allure.feature(FEATURE)
class TestWrongBook:
    """错题本：学科筛选、答案解析可见性、空态。"""

    @P1
    @allure.story("UI-STU-07 错题本按学科筛选列表随之变化")
    @allure.severity(allure.severity_level.NORMAL)
    def test_filter_by_subject(self, as_student):
        page = WrongBookPage(as_student).open()
        page.wait_loaded(timeout=config.WAIT_TIMEOUT * 2)
        before_cards = page.card_count()
        assert before_cards > 0, "前置：演示账号应已有错题记录"
        assert page.summary_number() == before_cards, \
            "统计数字（%s）与卡片数（%s）不一致" % (page.summary_number(), before_cards)

        subjects = [s for s in page.subject_options() if s]
        assert subjects, "学科下拉没有可选项：%s" % page.subject_options()

        page.filter_subject(subjects[0])
        page.wait_for(lambda d: page.card_count() > 0, message="筛选后一道错题都没有了")
        after_cards = page.card_count()
        assert after_cards <= before_cards, \
            "筛选后条目反而变多（%s → %s）" % (before_cards, after_cards)
        assert page.summary_number() == after_cards, \
            "筛选后统计（%s）与卡片数（%s）不一致" % (page.summary_number(), after_cards)

        page.filter_subject("")
        page.wait_for(lambda d: page.card_count() == before_cards,
                      message="切回「全部学科」后没有恢复全量列表")

    @P1
    @allure.story("UI-STU-08 错题答案与解析可见")
    @allure.severity(allure.severity_level.NORMAL)
    def test_reference_and_analysis(self, as_student):
        """实测修订：错题本**没有展开/收起入口**，参考答案与解析在 `.ref-box`
        里始终可见（卡片内一个 button 都没有）。原文的「点展开」不可达，
        断言改为「默认可见 + 内容非空 + 我的作答区存在」。
        """
        page = WrongBookPage(as_student).open()
        page.wait_loaded(timeout=config.WAIT_TIMEOUT * 2)
        assert page.card_count() > 0, "前置：没有错题记录"
        assert not page.has_toggle(), \
            "错题卡出现了按钮，说明产品已加展开/收起——本用例需要按新结构重写"

        refs = [page.ref_text(i) for i in range(min(5, page.card_count()))]
        assert all(len(r) > 0 for r in refs), "有错题卡没有参考答案：%s" % refs
        assert any("解析" in r for r in refs), \
            "前 5 条错题都没有解析内容（`analysis` 全为空？）：%s" % [r[:40] for r in refs]
        assert page.mine_text(0), "错题卡缺少「我的作答」区"

    @P2
    @allure.story("UI-STU-12 错题本无数据时展示空态文案")
    @allure.severity(allure.severity_level.MINOR)
    def test_wrong_book_empty(self, as_bare_student):
        page = WrongBookPage(as_bare_student).open()
        page.wait_loaded()

        assert page.card_count() == 0, "新账号不应有错题记录"
        assert "暂无错题" in page.summary_text(), \
            "空态统计文案不符：%r" % page.summary_text()
        text = page.js_text(page.L["list"]) or ""
        assert "还没有错题" in text, "空态列表文案不符：%r" % text[:120]
        assert "加载中" not in text, "空态停在加载中"


@allure.feature(FEATURE)
class TestPracticeEmpty:
    """没有学科班的新生：练习页必须给出可读引导，而不是空白。"""

    @P2
    @allure.story("UI-STU-11 未加入学科时练习页给出引导空态")
    @allure.severity(allure.severity_level.MINOR)
    def test_practice_no_subject(self, as_bare_student):
        page = PracticePage(as_bare_student).open()
        page.wait_settled()

        text = page.host_text()
        assert page.card_count() == 0, "没有学科班却出现了题卡"
        assert "还没有加入任何学科班" in text, \
            "没有给出「联系任课教师加入学科班」的引导：%r" % text[:160]
        assert "加载中" not in text, "空态停在加载中"
        assert page.shuffle_disabled() is True, "空态下「换一批」应为禁用"
        assert [s for s in page.subject_options() if s] == [], \
            "没有学科却给出可选的学科：%s" % page.subject_options()
