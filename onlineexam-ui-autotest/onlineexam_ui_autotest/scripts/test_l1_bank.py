# -*- coding: utf-8 -*-
"""L1 教师·题库与知识点：20 条（docs/03 UI-QB-02 ~ UI-QB-21）。

数据策略：
    - 读类用例共用 `bank` 造数（5 道题：单选/多选/判断/填空 + 1 道停用靶子）；
    - 写类用例用 `new_question` 现造，避免"上一轮改坏的题干"影响断言；
    - 停用靶子题每轮造数会自动恢复启用（题目删除是软删，记录永留）。

三个实现约束直接决定了断言口径（都实测过）：
    1. 分页是 `#pager a[data-page]`，没有 #btn-next；边界靠 `li.disabled` 表达；
    2. 「停用」是原生 `confirm()`，必须 accept_alert()；
    3. 导出是 `location.href` 触发下载，URL 不变、不开新窗口 → 只能验文件落盘。
"""
import os

import allure
import pytest

import config
from common.data_factory import BANK_QUESTIONS, ensure_import_sample
from pages.teacher_pages import (
    KnowledgePointPage,
    QuestionBankPage,
    QuestionEditorPage,
)

pytestmark = [pytest.mark.p1]

FEATURE = "03 教师·题库与知识点"


def _open_bank(driver):
    page = QuestionBankPage(driver).open()
    page.wait_rows()
    return page


@allure.feature(FEATURE)
class TestQuestionBankList:
    """列表：筛选 / 搜索 / 重置 / 翻页。"""

    @allure.story("UI-QB-04 按题型筛选后列表题型一致")
    @allure.severity(allure.severity_level.NORMAL)
    def test_filter_by_type(self, as_teacher):
        page = _open_bank(as_teacher)
        before = page.row_count()

        page.set_filter("type", "multiple")

        types = set(page.row_types())
        assert types == {"多选题"}, "筛选「多选」后列表仍有其它题型：%s" % types
        assert page.row_count() <= before, "筛选后行数不应多于筛选前"
        assert page.value(page.L["type"]) == "multiple", "筛选项没有保持选中"

    @allure.story("UI-QB-05 关键词搜索命中题干")
    @allure.severity(allure.severity_level.NORMAL)
    def test_search_by_keyword(self, as_teacher, bank):
        page = _open_bank(as_teacher)

        page.keyword(bank["keyword"], expect_hit=True)

        stems = page.stems()
        assert len(stems) >= 5, "造数题应至少 5 条命中，实际 %d 条" % len(stems)
        assert all(bank["keyword"] in s for s in stems), \
            "搜索结果里混入了不匹配的题：%s" % [s for s in stems if bank["keyword"] not in s][:3]

    @allure.story("UI-QB-06 重置清空筛选并恢复全量")
    @allure.severity(allure.severity_level.NORMAL)
    def test_reset_filters(self, as_teacher, bank):
        page = _open_bank(as_teacher)
        full_rows = page.row_count()

        page.set_filter("type", "multiple")
        page.keyword(bank["keyword"], expect_hit=True)
        page.reset()

        assert page.value(page.L["type"]) == "", "重置后题型筛选未清空"
        assert page.value(page.L["keyword"]) == "", "重置后关键词未清空"
        assert page.range_from() == 1, "重置后未回到第 1 页（当前起始 %s）" % page.range_from()
        assert page.row_count() == full_rows, \
            "重置后行数应恢复为 %d，实际 %d" % (full_rows, page.row_count())

    @allure.story("UI-QB-07 翻页后页码与内容变化")
    @allure.severity(allure.severity_level.NORMAL)
    def test_paging(self, as_teacher):
        page = _open_bank(as_teacher)
        page.reset()
        assert page.total() > page.page_size(), "题库总量不足以翻页（%d 条）" % page.total()
        first_page_row = page.first_row_text()

        page.goto_page(2)

        assert page.range_from() == page.page_size() + 1, \
            "第 2 页起始条数应为 %d，实际 %d（%s）" % (
                page.page_size() + 1, page.range_from(), page.page_info())
        assert page.first_row_text() != first_page_row, "翻页后首行内容没变，可能没真正翻页"
        assert not page.prev_disabled(), "第 2 页「上一页」应可用"

    @allure.story("UI-QB-21 末页「下一页」禁用")
    @allure.severity(allure.severity_level.MINOR)
    def test_last_page_next_disabled(self, as_teacher):
        page = _open_bank(as_teacher)
        page.reset()
        last = page.last_page_no()
        assert last >= 2, "题库只有 %d 页，无法验证末页" % last

        page.goto_page(last)

        assert page.next_disabled(), "末页「下一页」应禁用（li 无 disabled class）"
        assert page.range_from() == (last - 1) * page.page_size() + 1, \
            "末页起始条数不符：%s" % page.page_info()
        assert not page.prev_disabled(), "末页「上一页」应可用"

    @allure.story("UI-QB-20 搜索无结果时显示空态文案")
    @allure.severity(allure.severity_level.MINOR)
    def test_search_no_result(self, as_teacher):
        page = _open_bank(as_teacher)

        page.keyword("UIAT_NOT_EXIST_%s" % config.RUN_TAG, expect_hit=False)

        assert page.empty_state(), "无结果时应显示「还没有符合条件的题目」空态"
        assert page.row_count() == 0, "空态下不应有数据行"
        assert page.total() == 0, "空态下总数应为 0，实际 %s" % page.total()


@allure.feature(FEATURE)
class TestQuestionEditor:
    """新增 / 编辑：表单联动与保存回列表。"""

    @allure.story("UI-QB-02 新增单选题保存后回列表可见")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_create_single_choice(self, as_teacher, sessions, request):
        stem = config.tag("新题干_%s" % request.node.name[-12:])
        editor = QuestionEditorPage(as_teacher).open()
        editor.fill(stem=stem, score=5, subject="数据结构")
        # 必须填满默认渲染的 4 行：前端 collect() 不过滤空选项，
        # 留空会原样提交 → 后端 400，且提示是 "[object Object]"（BUG-02）。
        for i, text in enumerate(("选项甲", "选项乙", "选项丙", "选项丁")):
            editor.fill_option(i, text, correct=(i == 0))

        page = editor.save_expect_list()
        page.keyword(stem, expect_hit=True)

        try:
            assert page.row_count() == 1, "应只命中 1 条新题，实际 %d 条" % page.row_count()
            assert stem in page.stems()[0]
            assert page.row_types()[0] == "单选题"
        finally:
            data = sessions["teacher"].get(
                "/questions/", params={"keyword": stem, "page_size": 10})
            for q in data.get("results") or []:
                if q["stem"] == stem:
                    sessions["teacher"].delete("/questions/%s/" % q["id"], expect=(200, 204))

    @allure.story("UI-QB-08 编辑页正确回填已有题目")
    @allure.severity(allure.severity_level.NORMAL)
    def test_edit_page_prefilled(self, as_teacher, bank):
        spec = next(s for s in BANK_QUESTIONS if s["key"] == "single")

        editor = QuestionEditorPage(as_teacher).open_edit(bank["ids"]["single"])
        values = editor.values()

        assert values["stem"] == spec["stem"], "题干未回填：%r" % values["stem"]
        assert values["type"] == "single", "题型未回填：%r" % values["type"]
        # 服务端用 Decimal 序列化，回填到 input 里是 "2.00" 而不是 "2" —— 按数值比，不按字符串比
        assert float(values["score"]) == float(spec["score"]), \
            "分值未回填：%r（期望 %r）" % (values["score"], spec["score"])
        assert values["difficulty"] == str(spec["difficulty"]), \
            "难度未回填：%r（期望 %r）" % (values["difficulty"], spec["difficulty"])
        assert editor.option_count() == len(spec["options"]), \
            "选项未回填：期望 %d 行，实际 %d 行" % (len(spec["options"]), editor.option_count())
        correct = [o["label"] for o in editor.option_rows() if o["correct"]]
        assert correct == ["B"], "正确答案勾选未回填：%s" % correct

    @allure.story("UI-QB-09 修改题目题干保存后列表更新")
    @allure.severity(allure.severity_level.NORMAL)
    def test_edit_stem(self, as_teacher, new_question):
        new_stem = config.tag("改后题干")

        editor = QuestionEditorPage(as_teacher).open_edit(new_question["id"])
        editor.fill(stem=new_stem)
        editor.save_in_place()               # 编辑保存后停留原页，只弹「题目已更新」
        page = QuestionBankPage(as_teacher).open()
        page.wait_rows()
        page.keyword(new_stem, expect_hit=True)

        assert new_stem in page.stems()[0], "列表未出现修改后的题干"
        page.keyword(new_question["stem"], expect_hit=False)
        assert page.empty_state(), "旧题干仍能搜到，说明保存没生效"

    @allure.story("UI-QB-10 停用题目后状态变化")
    @allure.severity(allure.severity_level.NORMAL)
    def test_disable_question(self, as_teacher, bank, sessions):
        page = _open_bank(as_teacher)
        page.keyword(bank["stems"]["disable"], expect_hit=True)
        index = page.row_index_of(bank["stems"]["disable"])
        assert index == 0, "停用靶子题不在搜索结果首行（index=%d）" % index
        assert not page.row_has_disabled_badge(index), "用例前置：该题应处于启用态"

        confirm_text = page.disable_row(index)

        assert "停用" in confirm_text, "二次确认文案未提示停用：%r" % confirm_text
        page.wait.until(lambda d: page.row_has_disabled_badge(0),
                        message="停用后该行未显示「已停用」徽章")
        # 复位：下一轮还要复用它，这里恢复启用，避免依赖"下一轮造数"的时机
        sessions["teacher"].patch("/questions/%s/" % bank["ids"]["disable"],
                                  json={"is_active": True})

    @allure.story("UI-QB-11 题型切换后表单结构相应变化")
    @allure.severity(allure.severity_level.NORMAL)
    def test_type_switch_changes_form(self, as_teacher):
        editor = QuestionEditorPage(as_teacher).open()

        editor.set_type("judge")
        assert editor.block_shown("options_block"), "判断题应显示选项区"
        assert not editor.block_shown("answer_block"), "判断题不应显示参考答案区"
        assert editor.option_count() == 2, "判断题选项应固定为 2 个，实际 %d" % editor.option_count()
        assert editor.attr(editor.L["add_option"], "disabled") is not None, \
            "判断题「添加选项」应禁用"

        editor.set_type("fill")
        assert not editor.block_shown("options_block"), "填空题不应显示选项区"
        assert editor.block_shown("answer_block"), "填空题应显示参考答案区"

        editor.set_type("multiple")
        assert editor.block_shown("options_block"), "多选题应显示选项区"
        assert editor.attr(editor.L["add_option"], "disabled") is None, \
            "多选题「添加选项」应可用"

    @allure.story("UI-QB-12 添加选项按钮新增一行选项")
    @allure.severity(allure.severity_level.NORMAL)
    def test_add_option(self, as_teacher):
        editor = QuestionEditorPage(as_teacher).open()
        editor.set_type("multiple")
        before = editor.option_count()

        editor.add_option()

        assert editor.option_count() == before + 1, \
            "添加选项后行数应为 %d，实际 %d" % (before + 1, editor.option_count())
        rows = editor.option_rows()
        assert rows[-1]["label"], "新增行应自动分配选项标签（A/B/C…），实际为空"
        assert rows[-1]["content"] == "", "新增行的选项内容应为空（待填写）"


@allure.feature(FEATURE)
class TestKnowledgePoint:
    """知识点：树渲染、新建、必填校验、停用持久化。"""

    @allure.story("UI-QB-03 知识点页树形结构渲染出节点")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_knowledge_tree_rendered(self, as_teacher):
        page = KnowledgePointPage(as_teacher).open()

        names = page.node_names()

        assert len(names) >= 1, "知识点树没有渲染出任何节点"
        assert "加载中" not in page.body_text(), "知识点树停在「加载中」"

    @allure.story("UI-QB-14 新建根知识点后树出现新节点")
    @allure.severity(allure.severity_level.NORMAL)
    def test_create_root_knowledge(self, as_teacher, sessions):
        name = config.tag("知识点")
        page = KnowledgePointPage(as_teacher).open()
        before = page.node_count()

        page.create_root(name=name, code="UIAT-KP", subject="数据结构")

        try:
            page.wait_toast("已创建")
            page.wait_for(lambda d: name in page.node_names(),
                          timeout=config.SHORT_TIMEOUT,
                          message="树里没有出现新知识点「%s」" % name)
            assert page.node_count() == before + 1, \
                "节点数应 +1（%d → %d）" % (before, page.node_count())
        finally:
            data = sessions["teacher"].get(
                "/knowledge-points/", params={"keyword": name, "page_size": 20})
            rows = data.get("results") if isinstance(data, dict) else data
            for node in rows or []:
                if node.get("name") == name:
                    sessions["teacher"].delete("/knowledge-points/%s/" % node["id"],
                                               expect=(200, 204, 400))

    @allure.story("UI-QB-18 知识点名称为空保存被拦")
    @allure.severity(allure.severity_level.MINOR)
    def test_create_knowledge_requires_name(self, as_teacher):
        page = KnowledgePointPage(as_teacher).open()
        before = page.node_count()

        page.click(page.L["add_root"])
        page.fill(name="", code="UIAT-EMPTY")
        page.click(page.L["save"])

        page.wait_toast("请填写名称")
        assert page.node_count() == before, "名称为空却新建出了节点"
        assert page.url.endswith("/knowledge-points/"), "校验失败不应跳转"

    @allure.story("UI-QB-19 停用知识点后状态持久化")
    @allure.severity(allure.severity_level.MINOR)
    def test_disable_knowledge(self, as_teacher, sessions):
        """用例原预期「节点显示停用态」，实测是「停用后节点从树里消失」。

        `/knowledge-points/tree/` 只返回启用节点（OBS-09）。所以正确口径是：
        树里不再显示（停用生效），但记录仍在且 is_active=False（停用 ≠ 删除）。
        """
        name = config.tag("停用知识点")
        page = KnowledgePointPage(as_teacher).open()
        page.create_root(name=name, code="UIAT-KP-OFF", subject="数据结构")
        page.wait_toast("已创建")
        node_id = None
        try:
            rows = sessions["teacher"].get(
                "/knowledge-points/", params={"keyword": name, "page_size": 20})
            rows = rows.get("results") if isinstance(rows, dict) else rows
            node_id = next((n["id"] for n in rows or [] if n.get("name") == name), None)
            assert node_id, "新建的知识点查不到 id，无法继续验证停用"

            page.click_node_edit(name)
            page.set_active(False)
            page.click(page.L["save"])
            page.wait_toast("已更新")

            page.refresh()
            assert name not in page.node_names(), \
                "停用后节点仍出现在树里（tree 接口默认应只返回启用节点）"
            detail = sessions["teacher"].get("/knowledge-points/%s/" % node_id)
            assert detail["is_active"] is False, "停用没有落库：is_active 仍为 True"
        finally:
            if node_id:
                sessions["teacher"].delete("/knowledge-points/%s/" % node_id,
                                           expect=(200, 204, 400))


@allure.feature(FEATURE)
class TestImportExport:
    """导入 / 导出：dry-run 明细、未选文件校验、文件真的落盘。"""

    @allure.story("UI-QB-13 题库导入解析（不入库）返回明细")
    @allure.severity(allure.severity_level.NORMAL)
    def test_import_dry_run(self, as_teacher, bank):
        fixture = ensure_import_sample()
        page = _open_bank(as_teacher)
        total_before = page.total()

        page.open_import()
        page.choose_import_file(fixture)
        page.run_import()

        text = page.import_result_text()
        assert "解析 1 行" in text, "解析条数不符（夹具 2 行、1 行合法）：%s" % text[:200]
        assert "试跑模式" in text or "未入库" in text, "未提示仅解析不入库：%s" % text[:200]
        assert "第 3 行" in text, "错误明细缺少行号（夹具第 2 条数据在 Excel 第 3 行）：%s" % text[:200]
        assert "正确答案" in text, "错误原因应指向「正确答案」列：%s" % text[:200]

        page.click_real("#importModal .btn-secondary")     # 关闭弹窗（data-bs-dismiss 需真实指针）
        page.wait_for(lambda d: not page.visible("#importModal"),
                      timeout=config.SHORT_TIMEOUT, message="导入弹窗未关闭")
        page.wait_until_total(total_before)

    @allure.story("UI-QB-15 导入未选文件即解析时给出提示")
    @allure.severity(allure.severity_level.MINOR)
    def test_import_without_file(self, as_teacher):
        page = _open_bank(as_teacher)
        page.open_import()

        page.click(page.L["import_btn"])

        page.wait_toast("请先选择文件")
        assert page.import_result_text() == "", "未选文件却渲染了导入结果明细"

    @allure.story("UI-QB-16 导出 xlsx 文件落盘")
    @allure.severity(allure.severity_level.MINOR)
    def test_export_xlsx(self, as_teacher):
        page = _open_bank(as_teacher)

        path = page.export_file("xlsx")

        assert os.path.getsize(path) > 10240, "导出文件过小（%d 字节），可能是错误页" % os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(2)
        assert head == b"PK", "xlsx 应是 zip 容器（文件头 PK），实际 %r" % head

    @allure.story("UI-QB-17 导入模板下载链接有效")
    @allure.severity(allure.severity_level.MINOR)
    def test_download_import_template(self, as_teacher):
        page = _open_bank(as_teacher)
        page.open_import()

        path = page.template_file()

        assert path.lower().endswith(".csv"), "模板应为 csv，实际 %s" % path
        with open(path, encoding="utf-8-sig") as f:
            header = f.readline()
        assert "题型" in header and "题干" in header, "模板表头不符：%r" % header
