# -*- coding: utf-8 -*-
"""L1 教师·判分与成绩：11 条（docs/03 UI-GRD-02 ~ UI-GRD-12）。

数据策略：
    批改用例一律用 `pending_attempt` 现造（教师建考试 → 学生交卷 → 未判分）：
    判客观题 / 改主观分 / 出分都会改状态，共用一份会让"待批 N 道"互相污染。

四个实测约束：
    1. `#btn-grade`（判客观题）无确认；`#btn-ai`、`#btn-finalize` 有原生 confirm；
    2. 每个动作后都会 `refresh()` 重载面板，按钮节点被替换（不能缓存 element）；
    3. 成绩单**没有分页**，一次拉全部；关键词要**回车**才触发；
    4. 成绩单统计卡是 `#s-*`（应考/已交卷/已判分/平均分/及格率），
       `#i-*` 是右侧的判分口径指标卡，两套都要看。
"""
import allure
import pytest

import config
from pages.teacher_pages import GradingPage, ScoreboardPage

pytestmark = [pytest.mark.p1]

FEATURE = "06 教师·判分与成绩"


def _open_grading(driver, exam_id):
    page = GradingPage(driver).open()
    page.select_exam(exam_id)
    return page


@allure.feature(FEATURE)
class TestScoreboard:
    """成绩单：指标卡 / 筛选 / 搜索 / 刷新。"""

    @allure.story("UI-GRD-02 成绩单指标卡与判分口径有值")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_scoreboard_stats(self, as_teacher, runtime):
        exam_id = runtime["ids"]["exam_exhausted"]        # 已判分并出分
        page = ScoreboardPage(as_teacher).open(exam_id=exam_id)

        stats = page.stats()
        for key, label in (("s_applicants", "应考"), ("s_submitted", "已交卷"),
                           ("s_graded", "已判分"), ("s_avg", "平均分"),
                           ("s_passrate", "及格率")):
            assert stats[key].strip() not in ("", "—"), "%s 指标卡没有值" % label
        assert stats["s_applicants"].isdigit(), "应考人数不是数字：%r" % stats["s_applicants"]
        assert int(stats["s_applicants"]) >= 1, "该场有作答，应考人数应 ≥1"

        summary = page.summary()
        assert summary["i_policy"].strip() not in ("", "—"), "多选判分策略没有显示"
        assert page.row_count() >= 1, "成绩单没有学生行"

    @allure.story("UI-GRD-07 成绩单按班级筛选")
    @allure.severity(allure.severity_level.NORMAL)
    def test_scoreboard_filter_classroom(self, as_teacher, runtime):
        page = ScoreboardPage(as_teacher).open(exam_id=runtime["ids"]["exam_exhausted"])
        page.wait_loaded()
        options = page.classroom_options()
        real = [o for o in options if o[0]]
        assert real, "班级下拉没有可选项（只有占位项）"
        before_rows = page.row_count()
        before_applicants = page.stats()["s_applicants"]

        page.filter_classroom(real[0][0])

        assert page.row_count() <= before_rows, "按班级筛选后行数不应增加"
        # 应考人数是全场的，不随班级筛选变化——这是数据口径，不是 bug
        assert page.stats()["s_applicants"] == before_applicants, \
            "应考人数不应随班级筛选变化（%s → %s）" % (
                before_applicants, page.stats()["s_applicants"])

    @allure.story("UI-GRD-08 成绩单学生关键词搜索（回车触发）")
    @allure.severity(allure.severity_level.NORMAL)
    def test_scoreboard_search(self, as_teacher, sessions, runtime):
        exam_id = runtime["ids"]["exam_exhausted"]
        page = ScoreboardPage(as_teacher).open(exam_id=exam_id)
        page.wait_loaded()
        students = page.row_students()
        assert students, "成绩单没有学生行"
        # 取第一位学生的姓名片段（姓名里可能有学号，取前两个字更稳）
        keyword = students[0].split()[0][:2]

        page.search(keyword)

        assert page.row_count() >= 1, "按 %r 搜索没有命中" % keyword
        assert all(keyword in s for s in page.row_students()), \
            "搜索结果里混入了不匹配的学生：%s" % [
                s for s in page.row_students() if keyword not in s][:2]

    @allure.story("UI-GRD-11 成绩单刷新后数据保持一致")
    @allure.severity(allure.severity_level.MINOR)
    def test_scoreboard_reload(self, as_teacher, runtime):
        """用例原文是「成绩单分页」——实测**没有分页**（一次拉全部），

        所以改成验证同类的稳定性：点「刷新」后统计与行数不变、无 JS 错误。
        """
        page = ScoreboardPage(as_teacher).open(exam_id=runtime["ids"]["exam_exhausted"])
        before_stats = page.stats()
        before_rows = page.row_count()

        page.reload()

        assert page.stats() == before_stats, \
            "刷新后统计卡变化：%s → %s" % (before_stats, page.stats())
        assert page.row_count() == before_rows, "刷新后行数变化"
        assert page.console_errors() == [], "刷新后出现 JS 错误：%s" % page.console_errors()[:2]


@allure.feature(FEATURE)
class TestWorkbench:
    """批改台：队列 / 判分 / 出分 / 空态。"""

    @allure.story("UI-GRD-03 点队列条目加载答题详情")
    @allure.severity(allure.severity_level.NORMAL)
    def test_open_queue_item(self, as_teacher, pending_attempt):
        page = _open_grading(as_teacher, pending_attempt["exam_id"])

        assert page.queue_count() >= 1, "刚交卷的作答没有出现在批改队列里"
        page.open_attempt(0)

        assert page.card_count() >= 1, "答题详情没有渲染出题目卡片"
        text = page.panel_text()
        assert "客观题" in text and "主观题" in text, "面板缺少判分进度信息"
        assert page.elements(page.L["grade_btn"]), "「判客观题」按钮没有渲染"

    @allure.story("UI-GRD-04 判客观题后分数更新")
    @allure.severity(allure.severity_level.NORMAL)
    def test_grade_objective(self, as_teacher, pending_attempt):
        page = _open_grading(as_teacher, pending_attempt["exam_id"])
        page.open_attempt(0)
        before = page.panel_score()
        assert before[0] is not None, "面板头部没有得分/总分"

        page.grade_objective()

        after = page.panel_score()
        assert after[0] is not None, "判分后面板没有得分"
        assert float(after[0]) >= 0, "客观题得分异常：%r" % (after[0],)
        assert after[1] == before[1], "总分不应变（%s → %s）" % (before[1], after[1])

    @allure.story("UI-GRD-05 改主观题分数后总分重算")
    @allure.severity(allure.severity_level.NORMAL)
    def test_edit_subjective_score(self, as_teacher, pending_attempt):
        page = _open_grading(as_teacher, pending_attempt["exam_id"])
        page.open_attempt(0)
        page.grade_objective()                        # 先判客观题，总分才有基数

        index = page.subjective_index()
        assert index >= 0, "这份试卷没有主观题，无法验证改分"
        before_score, total = page.panel_score()
        old = float(page.card_score(index) or 0)
        full = page.card_full_score(index)          # 后端会把分数夹在 [0, 满分]；别硬编码 10
        new = old + 1 if old + 1 <= full else old - 1
        assert 0 <= new <= full and new != old, \
            "构造不出合法且不同的分数（原分 %s，满分 %s）" % (old, full)

        page.set_card_score(index, new)
        page.save_card(index)

        after_score, after_total = page.panel_score()
        assert float(after_score) == float(before_score) + (new - old), \
            "改主观题分数后总分没按差值变化：%s → %s（改 %s → %s）" % (
                before_score, after_score, old, new)
        assert after_total == total, "总分基数不应变化"

    @allure.story("UI-GRD-06 出分并公开成绩后状态变化")
    @allure.severity(allure.severity_level.NORMAL)
    def test_finalize_attempt(self, as_teacher, sessions, pending_attempt):
        page = _open_grading(as_teacher, pending_attempt["exam_id"])
        page.open_attempt(0)
        page.grade_objective()

        confirm_text = page.finalize()

        assert "出分" in confirm_text or "成绩" in confirm_text, \
            "出分前应有二次确认，实际文案：%r" % confirm_text
        detail = sessions["teacher"].get(
            "/grading/attempts/%s/report/" % pending_attempt["attempt_id"])
        assert detail["attempt"]["status"] in ("graded", "auto_graded"), \
            "出分后作答状态应为 graded/auto_graded，实际 %r" % detail["attempt"]["status"]

    @allure.story("UI-GRD-09 未选择考试时批改台显示引导")
    @allure.severity(allure.severity_level.MINOR)
    def test_workbench_without_exam(self, as_teacher):
        page = GradingPage(as_teacher).open()

        text = page.panel_text() or ""
        assert ("请选择" in text) or ("选一位考生" in text), \
            "未选考试时右侧面板应给出引导文案，实际：%r" % text[:80]
        assert page.console_errors() == [], "首屏出现 JS 错误：%s" % page.console_errors()[:2]

    @allure.story("UI-GRD-10 未判客观题直接出分应被拦或有明确提示")
    @allure.severity(allure.severity_level.MINOR)
    def test_finalize_without_grading(self, as_teacher, pending_attempt):
        page = _open_grading(as_teacher, pending_attempt["exam_id"])
        page.open_attempt(0)

        page.click(page.L["finalize_btn"])
        page.accept_alert()
        page.wait_for(lambda d: "出分中" not in (page.panel_text() or ""),
                      message="出分请求一直没有结束")

        toast = page.toast_text() or ""
        assert toast, "点击出分后既没有成功提示也没有错误提示"
        # 两种正确结果：被拦（提示需先判分）或放开（提示已出分）。不允许"静默无反应"。
        assert ("判" in toast) or ("出分" in toast), \
            "出分结果提示不可读：%r" % toast

    @allure.story("UI-GRD-12 批改队列不漏人（与已交卷人数一致）")
    @allure.severity(allure.severity_level.MINOR)
    def test_queue_matches_submitted(self, as_teacher, sessions, pending_attempt):
        """用例原文是"选一场没人交卷的考试看空态"——实测不可行：批改台的考试下拉
        只列出**有作答记录**的考试（`/grading/exams/` 过滤 `attempts__isnull=False`），
        没人交卷的考试根本不在列表里。

        改成更有价值的一致性断言：**待批队列的人数必须等于已交卷人数**。
        这条一旦不成立，就意味着有学生永远不会被批改（漏卷），比空态文案重要得多。
        """
        exam_id = pending_attempt["exam_id"]
        page = _open_grading(as_teacher, exam_id)

        submitted = sessions["teacher"].get(
            "/grading/scoreboard/", params={"exam_id": exam_id})["results"]
        assert page.queue_count() == len(submitted), \
            "待批队列 %d 人，已交卷 %d 人 —— 有学生不在队列里" % (
                page.queue_count(), len(submitted))
        assert page.queue_count() >= 1, "刚交卷的作答应出现在队列里"
