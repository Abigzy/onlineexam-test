# -*- coding: utf-8 -*-
"""L0 冒烟：15 条，覆盖三角色登录 + 9 个核心页可用 + 核心权限。

对应 docs/03-测试用例.md 中标记「冒烟」的用例，失败即阻断提测。
"""
import re

import allure
import pytest

import config
from pages.admin_pages import ManageDashboardPage
from pages.auth_pages import LoginPage
from pages.student_pages import (ClassroomPage, ExamTakePage, HomePage, MyExamsPage,
                                 PracticePage)
from pages.teacher_pages import (ExamListPage, GradingPage, PaperListPage,
                                 QuestionBankPage)

pytestmark = [pytest.mark.smoke, pytest.mark.p0]

epic = allure.epic


@allure.feature("01 认证与账号")
class TestAuth:
    @allure.story("UI-AUTH-01 学生账号表单登录成功并落到学生工作台")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_student_login_lands_home(self, anonymous):
        page = LoginPage(anonymous).login(config.ACCOUNTS["student"])
        assert anonymous.current_url.rstrip("/") == config.BASE_URL, \
            "登录后应落到首页，实际 %s" % anonymous.current_url

        home = HomePage(anonymous)
        nav = home.nav_texts()
        assert "我的考试" in nav and "我的学情" in nav, "学生导航缺少核心入口：%s" % nav
        assert "题库" not in nav and "考试管理" not in nav, "学生导航不应出现教师入口：%s" % nav
        assert page.error_text() == ""

    @allure.story("UI-AUTH-02 教师账号登录落到教师工作台导航")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_teacher_login_nav(self, anonymous):
        LoginPage(anonymous).login(config.ACCOUNTS["teacher"])
        nav = HomePage(anonymous).nav_texts()
        for item in ("教学资源", "组卷与考试", "批改与分析"):
            assert item in nav, "教师导航缺少「%s」，实际：%s" % (item, nav)
        assert "管理控制台" not in nav and "我的考试" not in nav, \
            "教师导航不应出现管理端/学生端入口：%s" % nav

    @allure.story("UI-AUTH-03 管理员登录直接跳管理控制台")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_admin_login_redirects_manage(self, anonymous):
        LoginPage(anonymous).login(config.ACCOUNTS["admin"])
        assert "/manage/" in anonymous.current_url, \
            "管理员登录后应落到 /manage/，实际 %s" % anonymous.current_url
        assert ManageDashboardPage(anonymous).count(".stat-card") >= 1, "管理控制台没有指标卡"

    @allure.story("UI-AUTH-04 退出登录后会话失效")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_logout_invalidates_session(self, as_student_isolated):
        as_student = as_student_isolated
        HomePage(as_student).open().logout()
        as_student.get(config.BASE_URL + "/my-exams/")
        # 只断"被拒绝并跳登录"这个稳定事实；是否带 next= 取决于服务端拦在哪一层
        # （mixin 直跳 /login/ 时不带），不能当 L0 的硬断言——回跳行为归 P1 的 UI-SEC-07。
        assert "/login/" in as_student.current_url, \
            "退出后访问受保护页应跳登录，实际 %s" % as_student.current_url
        assert MyExamsPage(as_student).count("#exam-cards") == 0, \
            "登录页不应渲染出考试卡片（说明会话没失效）"


@allure.feature("02 学生·考试闭环")
class TestExamLoop:
    @allure.story("UI-EXAM-01 我的考试页渲染出考试卡片")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_my_exams_cards(self, as_student):
        page = MyExamsPage(as_student).open()
        page.wait_cards()
        assert page.count(page.L["cards"]) >= 1, "我的考试页没有渲染出卡片"
        assert "加载中" not in page.body_text(), "页面仍停在加载中"
        assert page.active_tab() == "全部", "默认页签应为「全部」，实际「%s」" % page.active_tab()

    @allure.story("UI-EXAM-02 页签切换到「可作答」只保留可作答考试")
    @allure.severity(allure.severity_level.NORMAL)
    def test_tab_switch_open_only(self, as_student):
        page = MyExamsPage(as_student).open()
        page.wait_cards()
        all_titles = page.titles()
        page.switch_tab("可作答")
        page.wait.until(lambda d: page.active_tab() == "可作答", message="页签未切换")
        open_titles = page.titles()
        assert set(open_titles) <= set(all_titles), \
            "「可作答」出现了「全部」里没有的卡片：%s" % (set(open_titles) - set(all_titles))
        body = page.body_text()
        for badge in ("已结束", "已归档"):
            assert badge not in body or open_titles == [], \
                "「可作答」不应出现「%s」的考试" % badge

    @allure.story("UI-EXAM-03 点「开始考试」进入答题页并渲染第一题")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_start_exam_renders_question(self, as_student, runtime):
        exam_id = runtime["ids"]["exam_ongoing"]
        page = ExamTakePage(as_student).open(exam_id=exam_id)
        page.wait_questions()
        assert page.question_count() >= 1, "答题页没有渲染出题目"
        assert re.fullmatch(r"\d+/\d+", page.progress()), \
            "进度文本格式异常：%r" % page.progress()
        assert page.timer() not in ("--:--", ""), "计时器未初始化：%r" % page.timer()

    @allure.story("UI-EXAM-04 单选题选中后答题卡与进度同步更新")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_answer_single_choice_updates_progress(self, as_student, runtime):
        exam_id = runtime["ids"]["exam_ongoing"]
        page = ExamTakePage(as_student).open(exam_id=exam_id)
        page.wait_questions()
        # 注意：自动暂存间隔 30 秒（AUTOSAVE_INTERVAL_SECONDS=30），
        # 这里只断言"本地状态立刻正确"，保存状态由 slow 用例单独验证。
        page.elements(page.L["options"])[0].click()
        page.wait.until(lambda d: page.picked_count() == 1, message="选项没有被选中")
        assert page.picked_count() == 1, "单选应只选中 1 个选项，实际 %d" % page.picked_count()
        done, total = page.answered_ratio()
        assert done >= 1, "已答数没有增加：%s" % page.progress()
        assert page.count(page.L["answered_cells"]) >= 1, "答题卡没有标记已答"
        assert page.save_flag() in ("待保存…", "保存中…", "已保存"), \
            "保存状态异常：%s" % page.save_flag()


@allure.feature("03 学生·学情练习")
class TestStudentPages:
    @allure.story("UI-STU-01 每日练习页加载出题目卡片")
    @allure.severity(allure.severity_level.NORMAL)
    def test_practice_page_loaded(self, as_student):
        page = PracticePage(as_student).open()
        page.wait_loading_gone()
        cards = page.count(page.L["cards"])
        body = page.body_text()
        empty_hint = any(x in body for x in ("没有可推荐", "暂时没有", "完成一次考试并判分后"))
        assert cards >= 1 or empty_hint, \
            "每日练习既没有题卡也没有可读空态（cards=%d）" % cards
        assert "加载中" not in body, "练习页停在加载中"


@allure.feature("04 学生·班级")
class TestClassroom:
    @allure.story("UI-CLS-01 我的班级列表加载出班级卡片")
    @allure.severity(allure.severity_level.NORMAL)
    def test_classroom_list(self, as_student):
        page = ClassroomPage(as_student).open()
        page.wait_loading_gone()
        assert page.card_count() >= 1, "我的班级没有渲染出班级卡片"


@allure.feature("05 教师·题库与知识点")
class TestQuestionBank:
    @allure.story("UI-QB-01 题库列表渲染出题目行")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_question_bank_rows(self, as_teacher):
        page = QuestionBankPage(as_teacher).open()
        page.wait_rows()
        assert page.row_count() >= 1, "题库列表没有数据行"
        assert "加载中" not in page.body_text(), "题库仍停在加载中"


@allure.feature("06 教师·试卷与组卷")
class TestPaperList:
    @allure.story("UI-PAP-01 试卷列表渲染并与统计卡一致")
    @allure.severity(allure.severity_level.NORMAL)
    def test_paper_list(self, as_teacher):
        page = PaperListPage(as_teacher).open()
        page.wait_rows()
        page.wait_value(page.L["stat_total"])
        total = page.stat_total()
        assert total.isdigit(), "试卷统计总数异常：%r" % total
        assert page.row_count() >= 1, "试卷列表没有数据行"


@allure.feature("07 教师·考试管理与监控")
class TestExamManage:
    @allure.story("UI-EXM-01 考试列表与概览统计渲染")
    @allure.severity(allure.severity_level.NORMAL)
    def test_exam_list(self, as_teacher):
        page = ExamListPage(as_teacher).open()
        page.wait_rows()
        assert page.row_count() >= 1, "考试列表没有数据行"
        page.wait_value(".stat-value")
        stats = page.stat_values()          # 现在返回 dict：{"stat_total": ..., "stat_running": ...}
        assert stats and all(v.strip() not in ("", "—") for v in stats.values()), \
            "考试统计卡为空：%s" % stats


@allure.feature("08 教师·判分与成绩")
class TestGrading:
    @allure.story("UI-GRD-01 批改台选择考试后队列加载")
    @allure.severity(allure.severity_level.NORMAL)
    def test_grading_queue(self, as_teacher):
        page = GradingPage(as_teacher).open()
        # 考试下拉由 JS 拉取后填充，等选项到位再断言
        page.wait.until(lambda d: page.count(page.L["exam_select"] + " option") >= 2,
                        message="批改台没有可选考试（下拉未填充）")
        page.select_exam_by_index(1)
        text = page.queue_text()
        assert "加载中" not in text, "队列一直停在加载中"


@allure.feature("11 权限与可见性")
class TestGuard:
    @allure.story("UI-SEC-01 学生访问题库页被拒")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_student_cannot_open_question_bank(self, as_student, sessions):
        # 先看服务端真实状态码（页面被 403 时浏览器渲染的是 Django 错误页）
        r = sessions["student"].session.get(
            config.BASE_URL + "/question-bank/", allow_redirects=False, timeout=30)
        assert r.status_code == 403, "学生访问题库应返回 403，实际 %s" % r.status_code
        as_student.get(config.BASE_URL + "/question-bank/")
        assert QuestionBankPage(as_student).count("#question-rows") == 0, \
            "403 页面不应包含题库表格"
        assert "Traceback" not in as_student.page_source, "403 页面泄露了 Traceback"
