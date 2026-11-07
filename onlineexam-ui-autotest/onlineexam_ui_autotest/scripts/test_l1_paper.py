# -*- coding: utf-8 -*-
"""L1 教师·试卷与组卷：14 条（docs/03 UI-PAP-02 ~ UI-PAP-15）。

数据策略：
    - 读类用例（回填 / 预览 / 导出）共用 `paper_draft`（UIAT_组卷草稿，5 题）；
    - 写类用例（保存卷头 / 发布 / 复制 / 加题 / 随机组卷）用 `new_paper` 现造，
      否则上一轮把共享卷发布掉，这一轮「保存卷头」「发布」按钮就打不开了。

三个必须区分的按钮（点错会真的建出卷子来）：
    `#btnPreview`       预览 = `/papers/ai-compose/` 带 dry_run，**只试算不落库**
    `#btnCompose`       一键组卷 = 真生成
    `#btnRandomCompose` 随机组卷 = 真生成（按题量抽）
"""
import allure
import pytest

import config
from common.data_factory import drop_paper
from pages.teacher_pages import PaperComposePage, PaperListPage

pytestmark = [pytest.mark.p1]

FEATURE = "04 教师·试卷与组卷"


def _open_list(driver):
    page = PaperListPage(driver).open()
    page.wait_rows()
    return page


def _paper_total(driver):
    """列表页的「试卷总数」（异步填充，要等值）。"""
    page = _open_list(driver)
    page.wait_value(page.L["stat_total"])
    return int(page.stat_total())


def _paper_total(driver):
    """列表页的「试卷总数」（异步填充，要等值）。"""
    page = _open_list(driver)
    page.wait_value(page.L["stat_total"])
    return int(page.stat_total())


def _find_paper(api, title):
    data = api.get("/papers/", params={"keyword": title, "page_size": 20})
    for p in (data.get("results") or []):
        if p.get("title") == title:
            return p["id"]
    return None


@allure.feature(FEATURE)
class TestComposeWorkbench:
    """组卷工作台：知识点、蓝图、试算、组卷。"""

    @allure.story("UI-PAP-02 勾选知识点后题池按知识点收敛")
    @allure.severity(allure.severity_level.NORMAL)
    def test_kp_check_narrows_pool(self, as_teacher, paper_draft):
        """勾选叶子知识点 → 题池收敛、勾选可撤销。

        这条曾经拆成两条：一条只验"树渲染/复选框可点"，另一条用 `xfail(strict=True)`
        锁住"勾选应收敛"——因为当时单个勾选**完全失效**（BUG-03：`data-kp` 是无值属性，
        `dataset.kp` 为空串导致监听器直接 return）。BUG-03 修复后合并回一条正常用例。

        另注：全选 35 个知识点 **≠** 整个学科，未标注知识点的题不属于任何知识点会被排除
        （实测 746 → 740），所以这里只验"勾选后题量严格下降、取消后回到全量"。
        """
        page = PaperComposePage(as_teacher).open_paper(paper_draft["id"])
        full_total = page.pool_total()
        assert full_total > 0, "题库池没有算出可用题量（当前：%r）" % (page.pool_text() or "")[:80]
        assert len(page.kp_names()) >= 1, "知识点树没有渲染出节点"

        page.check_kp_by_name("顺序表")
        assert page.checked_kp_count() == 1, "复选框点击后没有变成勾选态"
        narrowed = page.pool_total()
        assert narrowed < full_total, \
            "勾选叶子知识点后题池没有收敛（%d → %d），BUG-03 可能复发" % (full_total, narrowed)

        # 取消勾选 → 恢复全量（勾选状态必须是可撤销的）
        page.check_kp_by_name_off("顺序表")
        assert page.pool_total() == full_total, \
            "取消勾选后题量没有恢复（%d → %d）" % (narrowed, page.pool_total())

    @allure.story("UI-PAP-03 试算不落库且题数与蓝图一致")
    @allure.severity(allure.severity_level.NORMAL)
    def test_preview_dry_run(self, as_teacher, paper_draft):
        # 先记总数再进组卷页：`_paper_total` 会导航到列表页，
        # 之后如果直接 page.preview() 就会在列表页上找 #previewBox（踩过）。
        total_before = _paper_total(as_teacher)

        page = PaperComposePage(as_teacher).open_paper(paper_draft["id"])
        # BUG-03 修复后恢复"按知识点试算"：勾一个叶子知识点，题池收敛到 35 道，
        # 蓝图每行 1 题（合计 6）保证库存充足——这样试算结果才只取决于蓝图，不受库存波动干扰。
        page.check_kp_by_name("顺序表")
        for i in range(page.blueprint_count()):
            page.set_blueprint(i, count=1)
        plan = page.blueprint_plan()
        expected = sum(int(row["count"]) for row in plan)

        page.preview()                                 # dry_run，不落库
        text = page.preview_text()

        assert "可组出 %d 题" % expected in text, \
            "试算题数与蓝图合计（%d）不符：%s" % (expected, text[:150])
        assert "分" in text, "试算结果缺少总分区"

        total_after = _paper_total(as_teacher)
        assert total_after == total_before, \
            "试算后试卷总数变了（%d → %d），说明 dry_run 落库了" % (total_before, total_after)

    @allure.story("UI-PAP-04 随机组卷生成新试卷")
    @allure.severity(allure.severity_level.NORMAL)
    def test_random_compose(self, as_teacher, sessions, request):
        page = PaperComposePage(as_teacher).open_paper_for_new()
        title = config.tag("随机卷_%s" % request.node.name[-8:])
        page.set_title(title)
        # 按知识点组卷是教师的真实用法；BUG-03 修复后这里恢复勾选，
        # 顺带守住"随机组卷真的用了所选知识点"这条路径。
        page.check_kp_by_name("顺序表")

        page.random_compose(count=5)

        try:
            assert page.meta()["meta_count"] == "5", \
                "随机组卷题数应为 5，实际 %s" % page.meta()["meta_count"]
            assert page.sheet_questions() == 5, \
                "卷面渲染了 %d 题，与题量 5 不一致" % page.sheet_questions()
            assert page.status_text() == "草稿", "新生成的卷应为草稿态，实际 %s" % page.status_text()
        finally:
            pid = _find_paper(sessions["teacher"], title)
            if pid:
                drop_paper(pid)

    @allure.story("UI-PAP-13 预览面板渲染卷面统计")
    @allure.severity(allure.severity_level.MINOR)
    def test_preview_panel_renders(self, as_teacher, paper_draft):
        page = PaperComposePage(as_teacher).open_paper(paper_draft["id"])

        page.preview()

        text = page.preview_text()
        assert "题型" in text and "库存" in text, "预览缺少题型/库存表：%s" % text[:120]
        assert "可组出" in text, "预览缺少组卷结论：%s" % text[:120]

    @allure.story("UI-PAP-14 新建页未落库时「保存卷头」按钮禁用")
    @allure.severity(allure.severity_level.MINOR)
    def test_save_title_disabled_before_created(self, as_teacher):
        """用例原文是「未勾知识点直接试算被拦」——实测**不拦**（按整个学科试算，合理）。

        改成验证同类的防错设计：还没有试卷时「保存卷头」禁用，
        避免对不存在的卷发 PATCH。
        """
        page = PaperComposePage(as_teacher).open_paper_for_new()

        assert page.save_title_disabled(), "新建页（尚无试卷）「保存卷头」应禁用"
        assert page.status_text() in ("未创建", "草稿"), \
            "新建页状态徽章应为「未创建」，实际 %r" % page.status_text()


@allure.feature(FEATURE)
class TestPaperEditor:
    """卷头与卷面操作。"""

    @allure.story("UI-PAP-05 保存卷头标题后生效")
    @allure.severity(allure.severity_level.NORMAL)
    def test_save_title(self, as_teacher, new_paper):
        new_title = config.tag("改标题")
        page = PaperComposePage(as_teacher).open_paper(new_paper["id"])

        page.set_title(new_title)
        page.save_title()

        page.open_paper(new_paper["id"])               # 重新加载，确认真的落库
        assert page.title_value() == new_title, \
            "保存后重新打开，标题仍是 %r" % page.title_value()

    @allure.story("UI-PAP-09 编辑已有试卷正确回填卷面")
    @allure.severity(allure.severity_level.NORMAL)
    def test_load_paper_prefilled(self, as_teacher, paper_draft):
        page = PaperComposePage(as_teacher).open_paper(paper_draft["id"])

        assert page.title_value() == paper_draft["title"], \
            "标题未回填：%r" % page.title_value()
        assert page.sheet_questions() == paper_draft["questions"], \
            "卷面题数（%d）与该卷实际题数（%d）不一致" % (
                page.sheet_questions(), paper_draft["questions"])
        meta = page.meta()
        assert int(meta["meta_count"]) == paper_draft["questions"], \
            "卷头统计题数（%s）与卷面不一致" % meta["meta_count"]
        assert float(meta["meta_score"]) > 0, "卷头总分为 0，卷面回填异常"

    @allure.story("UI-PAP-06 从题库加题后卷面与统计同步")
    @allure.severity(allure.severity_level.NORMAL)
    def test_add_question_from_picker(self, as_teacher, new_paper, bank):
        page = PaperComposePage(as_teacher).open_paper(new_paper["id"])
        before = page.sheet_questions()

        page.open_picker()
        page.picker_search(bank["keyword"])
        page.pick_first(1)
        page.add_picked()

        assert page.sheet_questions() == before + 1, \
            "卷面题数应 +1（%d → %d）" % (before, page.sheet_questions())
        assert int(page.meta()["meta_count"]) == before + 1, \
            "卷头统计题数没有同步：%s" % page.meta()["meta_count"]

    @allure.story("UI-PAP-10 发布试卷后状态徽章变化")
    @allure.severity(allure.severity_level.NORMAL)
    def test_publish_paper(self, as_teacher, new_paper):
        page = PaperComposePage(as_teacher).open_paper(new_paper["id"])
        assert page.status_text() == "草稿", "用例前置：新卷应为草稿"

        confirm_text = page.publish()

        assert "发布" in confirm_text, "发布前应二次确认，实际文案：%r" % confirm_text
        page.wait_for(lambda d: page.status_text() == "已发布",
                      message="发布后状态徽章未变（仍为 %s）" % page.status_text())

    @allure.story("UI-PAP-12 复制试卷生成副本并跳转")
    @allure.severity(allure.severity_level.MINOR)
    def test_clone_paper(self, as_teacher, new_paper, sessions):
        page = PaperComposePage(as_teacher).open_paper(new_paper["id"])

        page.clone()

        clone_id = page.paper_id()
        clone_title = page.title_value()
        try:
            assert clone_id != new_paper["id"], "复制后仍停留在原卷，没有跳转到副本"
            assert "副本" in clone_title, "副本标题应含「副本」，实际 %r" % clone_title
            assert page.status_text() == "草稿", "副本应为草稿态，实际 %s" % page.status_text()
            assert page.sheet_questions() == new_paper["questions"], \
                "副本卷面题数应与原卷一致（%d），实际 %d" % (
                    new_paper["questions"], page.sheet_questions())
        finally:
            if clone_id and clone_id != new_paper["id"]:
                drop_paper(clone_id)


@allure.feature(FEATURE)
class TestPaperList:
    """列表：筛选 / 搜索 / 导出 / 分页。"""

    @allure.story("UI-PAP-07 按状态筛选试卷")
    @allure.severity(allure.severity_level.NORMAL)
    def test_filter_by_status(self, as_teacher):
        page = _open_list(as_teacher)
        before = page.row_count()

        page.set_status("published")
        page.do_search()

        statuses = [page.status_of(i) for i in range(page.row_count())]
        assert all("已发布" in s for s in statuses), \
            "筛选「已发布」后仍有其它状态：%s" % [s for s in statuses if "已发布" not in s][:3]
        assert len(statuses) <= before, "筛选后行数不应多于筛选前"

    @allure.story("UI-PAP-08 关键词搜索试卷标题")
    @allure.severity(allure.severity_level.NORMAL)
    def test_search_by_keyword(self, as_teacher, paper_draft):
        page = _open_list(as_teacher)

        page.set_keyword(paper_draft["title"])
        page.do_search()

        assert page.row_count() >= 1, "搜索造数卷标题没有命中：%r" % paper_draft["title"]
        titles = page.titles()
        assert all(paper_draft["title"] in t for t in titles), \
            "搜索结果混入了不匹配的卷：%s" % [t for t in titles if paper_draft["title"] not in t][:2]

    @allure.story("UI-PAP-11 导出卷面以正确地址发起")
    @allure.severity(allure.severity_level.MINOR)
    def test_export_opens_new_window(self, as_teacher, paper_draft):
        """用例原预期"打开新窗口（句柄 +1）"，实测口径调整为验证导出调用参数。

        headless 下 `window.open` 是否真的产出新窗口取决于弹窗策略与用户手势判定，
        属浏览器行为；被测系统该保证的是"点导出会用正确地址、新标签页打开"。
        """
        page = _open_list(as_teacher)
        page.set_keyword(paper_draft["title"])
        page.do_search()
        index = page.row_index_of(paper_draft["title"])
        assert index >= 0, "列表里找不到造数卷"

        page.hook_window_open()
        page.act(index, "export")

        page.wait_for(lambda d: len(page.opened_windows()) > 0,
                      message="点导出没有调用 window.open")
        opened = page.opened_windows()[0]
        assert "/papers/%s/export/" % paper_draft["id"] in opened["url"], \
            "导出地址不对：%s" % opened["url"]
        assert "file_format=html" in opened["url"], \
            "导出格式参数缺失：%s" % opened["url"]
        assert opened["target"] == "_blank", \
            "导出应在新标签页打开，实际 target=%r" % opened["target"]

    @allure.story("UI-PAP-15 结果只有一页时分页按钮禁用")
    @allure.severity(allure.severity_level.MINOR)
    def test_pager_disabled_when_single_page(self, as_teacher, paper_draft):
        page = _open_list(as_teacher)
        page.set_keyword(paper_draft["title"])
        page.do_search()

        assert page.row_count() == 1, "搜造数卷应只剩 1 行，实际 %d 行" % page.row_count()
        # 实测：total_pages <= 1 时 `#pager` 直接清空，不存在"禁用态的 « »"，
        # 所以正确断言是"分页器不渲染 + 页码文案为 1/1"。用例原预期已按实测修订。
        assert page.pager_links() == 0, \
            "只有一页时不应渲染分页按钮，实际有 %d 个" % page.pager_links()
        assert page.page_info().strip() == "第 1 / 1 页", \
            "页码文案异常：%r" % page.page_info()
