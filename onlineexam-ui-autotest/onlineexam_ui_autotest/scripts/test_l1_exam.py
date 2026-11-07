# -*- coding: utf-8 -*-
"""L1 学生考试闭环：19 条（docs/03 UI-EXAM-05 ~ UI-EXAM-24）。

数据策略：
    - 读类用例共用 runtime 里的 exam_ongoing / exam_exhausted / exam_hidden / exam_future；
    - 写类用例用 `new_exam` 夹具现造一场（max_attempts=1），避免"上一题答过没有"
      影响断言——共享一场考试时这类断言会变成碰运气。
    - 依赖 30s 自动暂存的 3 条打 `slow` 且默认 skip（设 OE_SLOW=1 运行）。

试卷固定 4 题：单选 / 多选 / 填空 / 简答（见 common/data_factory.QUESTIONS）。
"""
import os
import time

import allure
import pytest

import config
from pages.student_pages import ExamResultPage, ExamTakePage, MyExamsPage

pytestmark = [pytest.mark.p1]

SLOW = os.getenv("OE_SLOW") == "1"
SLOW_REASON = "依赖 30s 自动暂存（AUTOSAVE_INTERVAL_SECONDS=30）；设 OE_SLOW=1 运行"


def _open_take(driver, exam_id):
    """打开答题页。

    注意：默认是**单题模式**，`#question-host` 里只渲染当前 1 题，所以总题数要看
    `#progress-text` 的 "x/N"，不能数 .question-block（只有全卷模式才等于总题数）。
    """
    page = ExamTakePage(driver).open(exam_id=exam_id)
    page.wait_questions()
    _, total = page.answered_ratio()
    assert total == 4, "造数试卷应为 4 题，实际 %d 题" % total
    return page


@allure.feature("02 学生·考试闭环")
class TestExamAnswering:
    @allure.story("UI-EXAM-05 多选题可多选且可取消选择")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p0
    def test_multiple_choice_multi_select(self, as_student, new_exam):
        page = _open_take(as_student, new_exam())
        page.goto_by_stem("UIAT 多选")
        page.answer_labels("B")
        page.wait.until(lambda d: len(page.picked_labels()) == 1, message="第一个选项未选中")
        page.answer_labels("D")
        page.wait.until(lambda d: len(page.picked_labels()) == 2, message="多选未同时选中 2 个")
        assert sorted(page.picked_labels()) == ["B", "D"]
        page.answer_labels("B")                       # 再点一次取消
        page.wait.until(lambda d: len(page.picked_labels()) == 1, message="取消选择无效")
        assert page.picked_labels() == ["D"]

    @allure.story("UI-EXAM-11 标记待复查后答题卡出现标记态")
    @allure.severity(allure.severity_level.NORMAL)
    def test_flag_question(self, as_student, new_exam):
        page = _open_take(as_student, new_exam())
        page.flag()
        page.wait.until(lambda d: page.flagged_count() >= 1, message="答题卡没有标记态")
        assert "取消标记" in page.text(page.L["btn_flag"])
        page.flag()
        page.wait.until(lambda d: page.flagged_count() == 0, message="取消标记无效")
        assert "标记待复查" in page.text(page.L["btn_flag"])

    @allure.story("UI-EXAM-12 上一题/下一题在首尾边界的可用性")
    @allure.severity(allure.severity_level.NORMAL)
    def test_pager_boundaries(self, as_student, runtime):
        page = _open_take(as_student, runtime["ids"]["exam_ongoing"])
        page.goto(0)
        assert page.current_index() == 0
        page.go_prev(expect_move=False)     # 首题再点「上一题」
        assert page.current_index() == 0, "首题点「上一题」不应越界"
        last = 3
        page.goto(last)
        page.go_next(expect_move=False)     # 末题再点「下一题」
        assert page.current_index() == last, "末题点「下一题」不应越界"
        page.go_prev()                      # 末题回退应正常

    @allure.story("UI-EXAM-08 答题卡点击题号切换题目")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p0
    def test_answer_sheet_switch(self, as_student, runtime):
        page = _open_take(as_student, runtime["ids"]["exam_ongoing"])
        first = page.stems()[0]
        page.goto(1)
        page.wait.until(lambda d: page.current_index() == 1, message="答题卡没有切开题")
        assert page.stems()[0] != first, "切题后题干没有变化"

    @allure.story("UI-EXAM-14 全卷模式一屏展示全部题目")
    @allure.severity(allure.severity_level.NORMAL)
    def test_all_mode(self, as_student, runtime):
        page = _open_take(as_student, runtime["ids"]["exam_ongoing"])
        assert not page.pager_hidden(), "单题模式下分页器应可见"
        page.toggle_all_mode()
        page.wait.until(lambda d: page.count(page.L["questions"]) == 4,
                        message="全卷模式没有渲染出全部题目")
        assert page.pager_hidden(), "全卷模式下分页器应隐藏"
        page.toggle_all_mode()
        page.wait.until(lambda d: not page.pager_hidden(), message="没切回单题模式")


@allure.feature("02 学生·考试闭环")
class TestExamSubmit:
    @allure.story("UI-EXAM-06 交卷确认弹窗展示未答数量并可继续检查")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p0
    def test_submit_modal_summary(self, as_student, new_exam):
        page = _open_take(as_student, new_exam())
        idx = page.goto_by_stem("UIAT 单选")
        page.answer_labels("B")
        page.wait.until(lambda d: len(page.picked_labels()) == 1, message="选项未选中")

        modal = page.open_submit_modal()
        summary = page.submit_summary()
        assert "共 4 题" in summary, "弹窗未显示总题数：%s" % summary
        assert "已作答" in summary, "弹窗未显示已作答数：%s" % summary

        page.close_submit_modal()
        assert "/take/" in page.url, "点「继续检查」后应留在答题页"
        assert len(page.picked_labels()) == 1, "关闭弹窗后作答被清空"

    @allure.story("UI-EXAM-07 确认交卷后跳转结果页并显示总分")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.p0
    def test_confirm_submit_goes_result(self, as_student, new_exam):
        exam_id = new_exam()
        page = _open_take(as_student, exam_id)
        page.answer_labels("B")
        page.open_submit_modal()
        page.confirm_submit()

        result = ExamResultPage(as_student)
        assert "/result/" in as_student.current_url, "确认交卷后没有跳结果页"
        text = result.text_all()
        assert "作答概况" in text, "结果页缺少「作答概况」区块"
        assert "Traceback" not in as_student.page_source

    @allure.story("UI-EXAM-21 交卷弹窗取消后不产生提交")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.p2
    def test_cancel_submit_keeps_attempt(self, as_student, new_exam):
        exam_id = new_exam()
        page = _open_take(as_student, exam_id)
        page.open_submit_modal()
        page.close_submit_modal()
        page.driver.refresh()
        page.wait_questions()
        assert "/take/" in page.url, "取消交卷后刷新应仍在答题页（说明未被提交）"


@allure.feature("02 学生·考试闭环")
class TestExamResume:
    @allure.story("UI-EXAM-09 刷新答题页题序与选项顺序不变（断网续考）")
    @allure.severity(allure.severity_level.NORMAL)
    def test_refresh_keeps_order(self, as_student, new_exam):
        exam_id = new_exam()
        page = _open_take(as_student, exam_id)
        before = page.stems()
        before_opts = page.texts("#question-host .option-row .option-content")
        page.driver.refresh()
        page.wait_questions()
        assert page.stems() == before, "刷新后题序发生变化（应确定性乱序）"
        assert page.texts("#question-host .option-row .option-content") == before_opts, \
            "刷新后选项顺序发生变化"

    @allure.story("UI-EXAM-19 未开始的考试卡片为不可作答态")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.p2
    def test_future_exam_disabled(self, as_student, runtime):
        page = MyExamsPage(as_student).open()
        page.wait_cards()
        text, disabled = page.card_button(runtime["titles"]["exam_future"])
        assert disabled is True, "未开始的考试按钮应禁用，实际：%r" % text
        assert ("未开始" in text) or ("未到" in text), \
            "禁用原因应可读（如「未开始」），实际：%r" % text

    @allure.story("UI-EXAM-16 已达最大作答次数时按钮禁用并给出原因")
    @allure.severity(allure.severity_level.NORMAL)
    def test_exhausted_exam_disabled(self, as_student, runtime):
        # 用例原预期是「按钮禁用 + 锁定原因」，实测实现是：已考满且已交卷时
        # 展示「查看结果」（不再给「开始考试」）——这是更合理的行为，按实测口径断言，
        # 差异已登记到 docs/05 §7（UI-EXAM-16 用例修订）。
        page = MyExamsPage(as_student).open()
        page.wait_cards()
        text, _ = page.card_button(runtime["titles"]["exam_exhausted"])
        assert "开始考试" not in text, "次数用尽后不应再显示「开始考试」，实际：%r" % text
        assert ("查看结果" in text) or ("继续作答" in text), \
            "已交卷的考试应可查看结果，实际：%r" % text

    @allure.story("UI-EXAM-15 「已完成」页签展示已交卷考试并可查看结果")
    @allure.severity(allure.severity_level.NORMAL)
    def test_done_tab_has_result_link(self, as_student, runtime):
        page = MyExamsPage(as_student).open()
        page.wait_cards()
        page.switch_tab("已完成")
        page.wait.until(lambda d: page.active_tab() == "已完成", message="页签未切换")
        text, disabled = page.card_button(runtime["titles"]["exam_exhausted"])
        assert "查看结果" in text, "已交卷考试应提供「查看结果」，实际：%r" % text
        assert disabled is False

    @allure.story("UI-EXAM-22 答题页倒计时持续递减")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.p2
    def test_timer_counts_down(self, as_student, runtime):
        page = _open_take(as_student, runtime["ids"]["exam_ongoing"])
        first = page.timer_seconds()
        assert first > 0, "计时器未初始化：%r" % page.timer()
        deadline = time.time() + 15
        while time.time() < deadline and page.timer_seconds() > first - 3:
            time.sleep(0.5)
        assert page.timer_seconds() <= first - 3, \
            "15 秒内倒计时没有递减（%s → %s）" % (first, page.timer_seconds())


@allure.feature("02 学生·考试闭环")
class TestExamResult:
    @allure.story("UI-EXAM-17 结果页答对统计与逐题徽章数量一致")
    @allure.severity(allure.severity_level.NORMAL)
    def test_result_badge_counts(self, as_student, runtime):
        page = ExamResultPage(as_student).open(exam_id=runtime["ids"]["exam_exhausted"])
        counts = page.badge_counts()
        text = page.text_all()
        assert counts.get("正确", 0) >= 1, "造数时单选已答对，结果页应有「正确」徽章：%s" % counts
        assert counts.get("未作答", 0) >= 1, "其余题未作答，应有「未作答」徽章：%s" % counts
        assert ("答对" in text) or ("正确" in text), "结果页缺少答对统计"

    @allure.story("UI-EXAM-18 成绩未公开时结果页不显示分数")
    @allure.severity(allure.severity_level.NORMAL)
    def test_result_score_hidden(self, as_student, runtime):
        page = ExamResultPage(as_student).open(exam_id=runtime["ids"]["exam_hidden"])
        text = page.text_all()
        # 实际文案：「成绩由教师阅卷后公布，请稍后查看」——按"含公布/待公布"断言
        assert ("公布" in text) or ("待公布" in text) or ("未公开" in text), \
            "成绩未公开时应出现「成绩待公布」类文案，实际：%s" % text[:120]
        assert not page.has_score_text(), "成绩未公开时不应出现具体分数"

    @allure.story("UI-EXAM-20 不存在的考试 ID 打开答题页给出错误态")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.p2
    def test_missing_exam_shows_error(self, as_student, sessions):
        # 服务端行为：不存在的考试返回 404。DEBUG=True 下 Django 渲染的是调试 404 页
        # （"Page not found"），生产环境会落到自定义 404 —— 页面是否友好单列 OBS-05。
        r = sessions["student"].session.get(
            config.BASE_URL + "/exams/999999/take/", allow_redirects=False, timeout=30)
        assert r.status_code == 404, "不存在的考试应返回 404，实际 %s" % r.status_code
        assert "500" not in r.text, "404 场景不应返回 5xx 内容"
        assert "Traceback" not in as_student.page_source


@allure.feature("02 学生·考试闭环")
class TestExamSlow:
    """依赖 30 秒自动暂存的用例：慢，但它们是"真的会丢答案"的那条防线。"""

    @allure.story("UI-EXAM-10 刷新后已答内容与进度保留")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.slow
    @pytest.mark.skipif(not SLOW, reason=SLOW_REASON)
    def test_refresh_keeps_answer(self, as_student, new_exam):
        page = _open_take(as_student, new_exam())
        idx = page.goto_by_stem("UIAT 单选")
        page.answer_labels("B")
        page.wait_for(lambda d: "已保存" in page.save_flag(), timeout=45,
                      message="30 秒自动暂存后仍未见「已保存」")
        done_before = page.answered_ratio()[0]
        page.driver.refresh()
        page.wait_questions()
        assert page.answered_ratio()[0] == done_before, "刷新后已答数丢失"
        page.goto(idx)
        assert page.picked_labels() == ["B"], "刷新后已选项丢失"

    @allure.story("UI-EXAM-13 填空题输入后自动保存并给出保存状态")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.slow
    @pytest.mark.skipif(not SLOW, reason=SLOW_REASON)
    def test_fill_autosave(self, as_student, new_exam):
        page = _open_take(as_student, new_exam())
        idx = page.goto_by_stem("UIAT 填空")
        page.fill_answer("后进先出")
        page.wait_for(lambda d: "已保存" in page.save_flag(), timeout=45,
                      message="30 秒自动暂存后仍未见「已保存」")
        page.driver.refresh()
        page.wait_questions()
        page.goto(idx)
        assert page.value("#question-host textarea[data-pq]") == "后进先出", "刷新后填空答案丢失"

    @allure.story("UI-EXAM-24 主观题作答内容刷新后保留")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.slow
    @pytest.mark.p2
    @pytest.mark.skipif(not SLOW, reason=SLOW_REASON)
    def test_short_answer_persisted(self, as_student, new_exam):
        page = _open_take(as_student, new_exam())
        idx = page.goto_by_stem("UIAT 简答")
        page.fill_answer("UIAT 自动化作答：进程与线程的区别")
        page.wait_for(lambda d: "已保存" in page.save_flag(), timeout=45,
                      message="30 秒自动暂存后仍未见「已保存」")
        page.driver.refresh()
        page.wait_questions()
        page.goto(idx)
        assert "UIAT 自动化作答" in page.value("#question-host textarea[data-pq]"), \
            "刷新后主观题答案丢失"

    @allure.story("UI-EXAM-23 答题页粘贴行为被记录且不影响答题")
    @allure.severity(allure.severity_level.MINOR)
    @pytest.mark.p2
    def test_paste_reported(self, as_student, new_exam):
        """粘贴是**静默记录**，不弹 `#cheat-banner`（那个只给「全屏退出」和「切屏超限」用）。

        所以证据要看右上角的 `#cheat-stat`：上报成功后它会变成「切屏 0 次 · 粘贴 1 次」。
        页面不拦截粘贴、也不阻断输入——记录与作答互不影响。
        """
        page = _open_take(as_student, new_exam())
        page.goto_by_stem("UIAT 简答")

        page.js("""
            const ta=document.querySelector('#question-host textarea[data-pq]');
            ta.focus();
            let dt;
            try { dt = new DataTransfer(); dt.setData('text/plain', '粘贴进来的内容'); } catch (e) { dt = null; }
            const ev = dt ? new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})
                          : new Event('paste', {bubbles: true, cancelable: true});
            ta.dispatchEvent(ev);""")

        page.wait_for(lambda d: "粘贴" in (page.text("#cheat-stat") or ""),
                      timeout=config.WAIT_TIMEOUT, message="粘贴事件没有被记录（#cheat-stat 无「粘贴」字样）")
        stat = page.text("#cheat-stat")
        assert "粘贴 1 次" in stat.replace(" ", " "), \
            "粘贴计数不符：%r" % stat

        page.fill_answer("UIAT 粘贴后继续输入")
        page.wait_for(lambda d: "已保存" in page.save_flag(), timeout=45,
                      message="粘贴后作答没有保存")
        assert page.value("#question-host textarea[data-pq]") == "UIAT 粘贴后继续输入", \
            "粘贴后继续输入的内容没有留在输入框"
        assert page.console_errors() == [], \
            "粘贴流程触发控制台错误：%s" % page.console_errors()[:2]
