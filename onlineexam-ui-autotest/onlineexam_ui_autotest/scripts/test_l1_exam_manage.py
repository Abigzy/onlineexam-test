# -*- coding: utf-8 -*-
"""L1 教师·考试管理与监控：12 条（docs/03 UI-EXM-02 ~ UI-EXM-13）。

数据策略：
    - 写类用例（新建 / 编辑 / 发布）用 `new_exam` 现造，`publish=False` 得到草稿态；
    - 读类用例（筛选 / 搜索 / 分页 / 监控）用造出来的考试，跑完归档清理；
    - 跨角色联动（教师建 → 学生见）用 `extra_driver` 开第二个会话，
      不能在同一个 driver 上换 cookie——会把教师的登录态顶掉。

四个实测约束（都写进 PO 注释了）：
    1. 分页是 `#btn-prev/#btn-next` 按钮，越界直接 return，只能看页码变没变；
    2. 状态切换（发布/开始/结束/归档）**没有二次确认**，点了就生效；
    3. 关键词是 input + 防抖，无搜索按钮；
    4. 监控页「只看嫌疑」是**前端过滤**，不发请求。
"""
from datetime import datetime, timedelta, timezone

import allure
import pytest

import config
from common.api_client import ApiSession
from common.data_factory import drop_paper  # noqa: F401  (保留给后续批次)
from pages.student_pages import MyExamsPage
from pages.teacher_pages import ExamListPage, MonitorPage

pytestmark = [pytest.mark.p1]

FEATURE = "05 教师·考试管理与监控"
TZ = timezone(timedelta(hours=8))


def _open_list(driver):
    page = ExamListPage(driver).open()
    page.wait_rows()
    return page


def _fmt(dt):
    """datetime-local 需要 `2026-11-05T09:00` 这种格式。"""
    return dt.strftime("%Y-%m-%dT%H:%M")


def _find_exam(api, title):
    data = api.get("/exams/", params={"keyword": title, "page_size": 20})
    for e in (data.get("results") or []):
        if e.get("title") == title:
            return e["id"]
    return None


@allure.feature(FEATURE)
class TestExamCreate:
    """新建 / 编辑 / 发布。"""

    @allure.story("UI-EXM-02 新建考试保存后列表出现")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_create_exam(self, as_teacher, sessions, request):
        title = config.tag("新建考试_%s" % request.node.name[-8:])
        now = datetime.now(TZ)
        page = _open_list(as_teacher)

        page.open_new()
        assert len(page.paper_options()) > 1, "试卷下拉没有可选的已发布试卷"
        page.fill(title=title, paper_index=1,
                  start=_fmt(now + timedelta(hours=1)),
                  end=_fmt(now + timedelta(hours=3)),
                  duration=30, attempts=1)
        page.save_expect_created()

        try:
            page.keyword(title)
            index = page.row_index_of(title)
            assert index == 0, "新建的考试没有出现在列表里（首条：%r）" % (page.titles()[:2],)
            assert "草稿" in page.status_of(index), \
                "新建考试应为草稿态，实际 %r" % page.status_of(index)
        finally:
            eid = _find_exam(sessions["teacher"], title)
            if eid:
                sessions["teacher"].delete("/exams/%s/" % eid, expect=(200, 204, 400))

    @allure.story("UI-EXM-03 教师建考试后学生端可见（跨角色联动）")
    @allure.severity(allure.severity_level.NORMAL)
    def test_exam_visible_to_student(self, extra_driver, sessions, new_exam):
        """教师建好并发布 → 学生「我的考试」能看到同一场。

        用 API 建考试（发布时间窗与面向全体都由造数保证），学生端走真实 UI：
        这样既不重复 UI-EXM-02 的表单覆盖，又能确认"建完就能考"这条链路。
        """
        exam_id = new_exam(publish=True)
        detail = sessions["admin"].get("/exams/%s/" % exam_id)
        title = detail["title"]

        student = ApiSession(config.ACCOUNTS["student"])
        extra_driver.get(config.BASE_URL + "/login/")
        extra_driver.delete_all_cookies()
        extra_driver.add_cookie({"name": "sessionid", "value": student.session_id,
                                 "domain": "127.0.0.1", "path": "/"})

        my = MyExamsPage(extra_driver).open()
        my.wait_cards()

        assert title in my.body_text(), \
            "学生端看不到教师刚建的考试《%s》" % title
        text, disabled = my.card_button(title)
        assert "开始考试" in text or "继续作答" in text, \
            "学生卡片按钮应可开考，实际 %r（disabled=%s）" % (text, disabled)
        assert disabled is not True, "可作答的考试按钮不应禁用"


@allure.feature(FEATURE)
class TestExamEdit:
    """编辑 / 状态流转 / 校验。"""

    @allure.story("UI-EXM-04 编辑考试标题生效")
    @allure.severity(allure.severity_level.NORMAL)
    def test_edit_exam_title(self, as_teacher, sessions, new_exam):
        exam_id = new_exam(publish=True)
        old_title = sessions["admin"].get("/exams/%s/" % exam_id)["title"]
        new_title = config.tag("改后考试")

        page = _open_list(as_teacher)
        page.keyword(old_title)
        index = page.row_index_of(old_title)
        assert index == 0, "列表里找不到待编辑的考试"

        page.open_edit(index)
        page.fill(title=new_title)
        page.save_expect_updated()

        page.keyword(new_title)
        assert page.row_index_of(new_title) == 0, "保存后列表没有出现新标题"
        assert old_title not in (page.js_text("#exam-body") or ""), "旧标题仍在列表里"

    @allure.story("UI-EXM-05 发布考试后状态徽章变化")
    @allure.severity(allure.severity_level.NORMAL)
    def test_publish_exam(self, as_teacher, sessions, new_exam):
        # 时间窗放到**未来**（+1h）：否则发布瞬间就落在考试时段内，
        # computed_status 会直接算成「进行中」，断言"已发布"就永远不成立。
        exam_id = new_exam(publish=False, offset_minutes=60)
        title = sessions["admin"].get("/exams/%s/" % exam_id)["title"]

        page = _open_list(as_teacher)
        page.keyword(title)
        index = page.row_index_of(title)
        assert index == 0, "列表里找不到草稿考试"
        assert "草稿" in page.status_of(index), "用例前置：应为草稿态"

        page.change_status(index, "published")

        page.keyword(title)
        index = page.row_index_of(title)
        assert "草稿" not in page.status_of(index), \
            "发布后状态仍是草稿：%r" % page.status_of(index)
        assert page.status_of(index) in ("已发布", "进行中"), \
            "发布后状态应为「已发布」（未到时间窗）或「进行中」，实际 %r" % page.status_of(index)

    @allure.story("UI-EXM-10 新建考试未选试卷保存被拦")
    @allure.severity(allure.severity_level.MINOR)
    def test_create_exam_requires_paper(self, as_teacher):
        page = _open_list(as_teacher)
        page.open_new()

        page.fill(title=config.tag("缺试卷"), paper_index=0)   # 0 = 「请选择试卷」
        page.save()

        page.wait_toast("请选择试卷")
        assert page.modal_open(), "校验失败时弹窗不应关闭"
        assert page.url.endswith("/exams/"), "校验失败不应跳转"


@allure.feature(FEATURE)
class TestExamList:
    """筛选 / 搜索 / 分页。"""

    @allure.story("UI-EXM-06 按状态筛选考试")
    @allure.severity(allure.severity_level.NORMAL)
    def test_filter_by_status(self, as_teacher, sessions, new_exam):
        """按状态筛选：核对「UI 行数 == 接口 count（封顶 10）」。

        **不能断言徽章文案**：筛选用的是**存储状态** `status`，而徽章显示的是
        `computed_status`——时间已过的 published 考试会显示「已结束」。
        所以"筛已发布却看到已结束"不是筛选失效（已登记 OBS-10），
        真正该验的是"前端确实把 status 传给了后端、后端确实按它过滤"。
        """
        new_exam(publish=True, offset_minutes=60)
        page = _open_list(as_teacher)

        page.set_status("published")

        ui_rows = page.row_count()
        api_count = sessions["teacher"].get(
            "/exams/", params={"status": "published", "page_size": 1})["count"]
        assert ui_rows == min(api_count, 10), \
            "UI 行数（%d）与接口 count（%d，封顶 10）不一致，筛选可能没传到后端" % (
                ui_rows, api_count)
        assert "草稿" not in "".join(page.status_of(i) for i in range(ui_rows)), \
            "筛选「已发布」后出现了草稿考试"

    @allure.story("UI-EXM-07 考试标题关键词搜索")
    @allure.severity(allure.severity_level.NORMAL)
    def test_search_by_keyword(self, as_teacher, sessions, new_exam):
        exam_id = new_exam(publish=True)
        title = sessions["admin"].get("/exams/%s/" % exam_id)["title"]

        page = _open_list(as_teacher)
        page.keyword(title)

        assert page.row_count() == 1, "按完整标题搜索应命中 1 条，实际 %d 条" % page.row_count()
        assert page.row_index_of(title) == 0, "命中的不是目标考试"

    @allure.story("UI-EXM-13 考试列表分页边界")
    @allure.severity(allure.severity_level.MINOR)
    def test_pager_boundary(self, as_teacher):
        page = _open_list(as_teacher)
        page.reset()
        current, total = page.page_no()

        if total <= 1:
            assert page.next_disabled(), "只有一页时「下一页」应禁用"
            assert page.prev_disabled(), "只有一页时「上一页」应禁用"
            return

        for _ in range(total - 1):                        # 翻到末页
            page.goto_next_page()
        assert page.page_no()[0] == total, "没有翻到末页（当前 %s / %s）" % (page.page_no())
        assert page.next_disabled(), "末页「下一页」应禁用"
        assert not page.prev_disabled(), "末页「上一页」应可用"


@allure.feature(FEATURE)
class TestExamMonitor:
    """监控页：概览 / 页签 / 只看嫌疑 / 刷新。"""

    @allure.story("UI-EXM-08 监控页概览卡有数据")
    @allure.severity(allure.severity_level.NORMAL)
    def test_monitor_overview(self, as_teacher, sessions, exam_with_attempt):
        page = MonitorPage(as_teacher).open(exam_id=exam_with_attempt["exam_id"])

        ov = page.overview()

        for key, label in (("applicants", "应考人数"), ("started", "已开始"),
                           ("submitted", "已交卷"), ("notstarted", "未开始")):
            assert ov[key].isdigit(), "%s 不是数字：%r" % (label, ov[key])
        assert int(ov["started"]) >= 1, "该场已有作答，已开始人数应 ≥1"
        assert int(ov["applicants"]) >= int(ov["started"]), \
            "应考人数（%s）不应少于已开始（%s）" % (ov["applicants"], ov["started"])
        # BUG-04 已修复（2026-11-05）：overview 补了 computed_status_display，
        # 徽章不再空白。把 UI 文案与接口字段锁在一起 —— 字段再丢会立刻红，
        # 而不是像修复前那样静默空一块（守门由 UI-EXM-08 直接承担，不另加用例）。
        ov_api = sessions["teacher"].get(
            "/exams/%s/attempts/" % exam_with_attempt["exam_id"])["overview"]
        display = ov_api.get("computed_status_display")
        badge = page.status_badge()
        assert display, "overview 缺少 computed_status_display（BUG-04 复发）"
        assert badge not in ("", "—"), "状态徽章仍是空白/占位符（BUG-04 复发）：%r" % badge
        assert badge == display, \
            "监控页状态徽章与接口不一致：页面 %r / 接口 %r" % (badge, display)

        status = sessions["teacher"].get(
            "/exams/%s/" % exam_with_attempt["exam_id"])["computed_status"]
        assert status in ("ongoing", "published", "finished"), \
            "考试状态异常：%r" % status

    @allure.story("UI-EXM-09 监控页状态页签过滤生效")
    @allure.severity(allure.severity_level.NORMAL)
    def test_monitor_tab_filter(self, as_teacher, exam_with_attempt):
        page = MonitorPage(as_teacher).open(exam_id=exam_with_attempt["exam_id"])
        page.overview()
        all_rows = page.row_count()
        assert all_rows >= 1, "该场应有作答记录"

        page.switch_tab("in_progress")
        in_progress_rows = page.row_count()
        tab_states = page.row_statuses()

        assert page.active_tab() == "in_progress", "页签 active 态没有跟随切换"
        assert in_progress_rows >= 1, "该场有学生正在作答，「答题中」页签应有记录"
        assert in_progress_rows <= all_rows, "「答题中」行数不应多于「全部」"
        bad = [s for s in tab_states if "答题中" not in s]
        assert not bad, "「答题中」页签下混入了其它状态：%s" % bad[:3]

        page.switch_tab("submitted")
        assert page.row_count() <= all_rows, "「已交卷」行数不应多于「全部」"

    @allure.story("UI-EXM-11 监控页「只看嫌疑」过滤")
    @allure.severity(allure.severity_level.MINOR)
    def test_monitor_only_suspicious(self, as_teacher, exam_with_attempt):
        page = MonitorPage(as_teacher).open(exam_id=exam_with_attempt["exam_id"])
        page.overview()
        before = page.row_count()

        page.toggle_suspicious()

        after = page.row_count()
        assert after <= before, "「只看嫌疑」后行数不应增加（%d → %d）" % (before, after)
        assert after == page.risk_rows(), \
            "过滤后应只剩嫌疑行（行数 %d，risk-row %d）" % (after, page.risk_rows())

        page.toggle_suspicious()                          # 再点一次取消过滤
        page.wait_for(lambda d: page.row_count() == before,
                      message="取消「只看嫌疑」后行数未恢复（%d，期望 %d）"
                              % (page.row_count(), before))

    @allure.story("UI-EXM-12 监控页立即刷新不报错")
    @allure.severity(allure.severity_level.MINOR)
    def test_monitor_refresh(self, as_teacher, exam_with_attempt):
        page = MonitorPage(as_teacher).open(exam_id=exam_with_attempt["exam_id"])
        before = page.overview()

        page.refresh()

        after = page.overview()
        assert after == before, "刷新后概览数据发生变化：%s → %s" % (before, after)
        assert page.console_errors() == [], \
            "刷新后出现 JS 错误：%s" % page.console_errors()[:2]
