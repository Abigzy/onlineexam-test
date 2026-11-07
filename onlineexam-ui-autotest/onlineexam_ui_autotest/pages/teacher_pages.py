# -*- coding: utf-8 -*-
"""教师侧页面（本阶段实现 L0 需要的列表页，后续按需补编辑器/组卷/监控）。"""
from selenium.webdriver.common.by import By

import config

from common.base_page import BasePage
from common.components import Modal, Pager


class QuestionBankPage(BasePage):
    """题库列表：筛选 / 搜索 / 翻页 / 行内操作 / 导入导出。

    两个实现细节决定了断言口径（读模板 + 实测确认）：
      1. 分页是 `<ul id="pager">` 里的 `<a data-page>` 链接，**没有** #btn-next/#btn-prev；
         越界不靠 disabled，而是渲染成 `li.page-item.disabled`（`<a>` 仍可点，点击后端直接 return）。
      2. 「停用」用原生 `confirm()`，必须 accept_alert()，否则后续命令全被对话框卡住。
    """
    path = "/question-bank/"
    ready = "#question-rows"

    L = {
        "rows": "#question-rows tr",
        "stem": "#question-rows .stem-text",
        "type_tag": "#question-rows .type-tag",
        "subject": "#f-subject",
        "type": "#f-type",
        "difficulty": "#f-difficulty",
        "source": "#f-source",
        "knowledge": "#f-knowledge",
        "keyword": "#f-keyword",
        "reset": "#btn-reset",
        "import_btn": "#btn-import",
        "import_modal": "#importModal",
        "import_file": "#import-file",
        "import_file_name": "#import-file-name",
        "import_dry": "#import-dry-run",
        "import_result": "#import-result",
        "export_xlsx": "#export-xlsx",
        "export_csv": "#export-csv",
        "download_tpl": "#download-template-2",
        "page_info": "#page-info",
        "pager": "#pager",
    }

    # ------------------------------------------------------------ 列表就绪
    def wait_rows(self):
        """等"真实数据行"。

        坑：表格初始 HTML 里就有表头行和「加载中」行，`tr` 数量天然 ≥1，
        只等 tr 会立刻返回，随后断言"页面不含加载中"就随机失败——第一轮跑踩过。
        数据行的可靠信号是行内操作按钮 `button[data-id]`。
        """
        self.wait.until(
            lambda d: d.execute_script(
                "const t=document.getElementById('question-rows');"
                "if(!t) return false;"
                "return t.querySelectorAll('button[data-id]').length>0"
                " || (t.innerText||'').includes('还没有符合条件');"),
            message="题库未渲染出数据行")
        return self

    def row_count(self):
        return self.js("return [...document.querySelectorAll('#question-rows tr')]"
                       ".filter(t=>t.querySelector('button[data-id]')).length")

    def first_row_text(self):
        return self.js("const tr=[...document.querySelectorAll('#question-rows tr')]"
                       ".find(t=>t.querySelector('button[data-id]'));return tr?tr.innerText.trim():'';")

    def stems(self):
        self.wait_rows()
        return self.js_texts(self.L["stem"])

    def row_types(self):
        """每行题型标签文案（td:nth-child(2) 里的 .type-tag）。"""
        self.wait_rows()
        return self.js_texts(self.L["type_tag"])

    def row_difficulty(self, index):
        return self.js("const tr=[...document.querySelectorAll('#question-rows tr')]"
                       ".filter(t=>t.querySelector('button[data-id]'))[arguments[0]];"
                       "if(!tr) return '';"
                       "return tr.querySelectorAll('td')[3].innerText.trim();", index)

    def row_has_disabled_badge(self, index):
        """该行是否带「已停用」徽章。"""
        return self.js(
            "const tr=[...document.querySelectorAll('#question-rows tr')]"
            ".filter(t=>t.querySelector('button[data-id]'))[arguments[0]];"
            "if(!tr) return false;"
            "return (tr.innerText||'').includes('已停用');", index)

    def row_index_of(self, substring):
        """按题干片段找行号（0 基），找不到 -1。"""
        return self.js(
            "const rows=[...document.querySelectorAll('#question-rows tr')]"
            ".filter(t=>t.querySelector('button[data-id]'));"
            "return rows.findIndex(t=>t.innerText.includes(arguments[0]));", substring)

    def row_id(self, index):
        return self.js(
            "const rows=[...document.querySelectorAll('#question-rows tr')]"
            ".filter(t=>t.querySelector('button[data-id]'));"
            "if(!rows[arguments[0]]) return null;"
            "return rows[arguments[0]].querySelector('button[data-id]').dataset.id;", index)

    # ------------------------------------------------------------ 分页
    def page_info(self):
        return self.js_text(self.L["page_info"])

    def total(self):
        """从「共 N 条，当前第 x-y 条」里取 N。"""
        import re
        m = re.search(r"共\s*(\d+)\s*条", self.page_info())
        return int(m.group(1)) if m else -1

    def range_from(self):
        import re
        m = re.search(r"第\s*(\d+)-(\d+)\s*条", self.page_info())
        return int(m.group(1)) if m else -1

    def page_size(self):
        return 10

    def last_page_no(self):
        total = self.total()
        return max(1, -(-total // self.page_size()))          # 向上取整

    def current_page(self):
        """当前页码：从「当前第 x-y 条」反推。"""
        start = self.range_from()
        return max(1, (start - 1) // self.page_size() + 1) if start > 0 else 1

    def goto_page(self, no):
        """跳到指定页。

        pager 只渲染「当前页 ±2」+ « » 共 5 个页码，目标页往往不在 DOM 里
        （实测：第 1 页只有 1~5，直接找 data-page="78" 会一直等不到）。
        所以不在当前渲染范围内时，用 » / « 逐页走。
        """
        while self.current_page() != no:
            cur = self.current_page()
            delta = 1 if no > cur else -1
            if delta > 0 and self.next_disabled():
                raise AssertionError("已到末页（第 %d 页），无法继续前进到第 %d 页" % (cur, no))
            if delta < 0 and self.prev_disabled():
                raise AssertionError("已到首页，无法回退到第 %d 页" % no)
            self.click('#pager a[data-page="%d"]' % (cur + delta))
            self.wait.until(lambda d: self.current_page() == cur + delta,
                            message="翻页未生效（仍停在第 %d 页）" % cur)
        self.wait_rows()
        return self

    def pager_class_of(self, label):
        """取 « / » 所在 li 的 class，用于判断边界禁用态。"""
        return self.js(
            "const links=[...document.querySelectorAll('#pager a[data-page]')];"
            "const a=links.find(x=>x.innerText.trim()===arguments[0]);"
            "return a ? a.parentElement.className : '';", label)

    def next_disabled(self):
        return "disabled" in (self.pager_class_of("»") or "")

    def prev_disabled(self):
        return "disabled" in (self.pager_class_of("«") or "")

    # ------------------------------------------------------------ 筛选
    def set_filter(self, key, value):
        """下拉筛选：直接设值并派发 change（服务端只认 change 事件）。"""
        before = self.page_info()
        self.js("const s=document.querySelector(arguments[0]);"
                "s.value=arguments[1];"
                "s.dispatchEvent(new Event('change'));", self.L[key], value)
        self.wait.until(
            lambda d: self.page_info() != before or "加载中" not in (d.execute_script(
                "const t=document.getElementById('question-rows');return t?(t.innerText||''):'';")),
            message="筛选后列表未刷新")
        self.wait_rows()
        return self

    def keyword(self, text, expect_hit=None):
        """关键词搜索（input 事件 + 400ms 防抖）。

        **不能只等「tbody 里出现关键词」**：造数题就是最新创建的，默认排在第一页，
        旧列表本来就含关键词，条件会立刻满足 —— 于是读到的是搜索前的 10 行。
        正确判据是「数据行**全部**含关键词」（或空态）。
        """
        self.js("const el=document.querySelector(arguments[0]);"
                "el.value=arguments[1];"
                "el.dispatchEvent(new Event('input'));", self.L["keyword"], text)
        cond = """
        const t = document.getElementById('question-rows');
        if (!t) return false;
        const rows = [...t.querySelectorAll('tr')].filter(r => r.querySelector('button[data-id]'));
        const empty = (t.innerText || '').includes('还没有符合条件');
        const loading = (t.innerText || '').includes('加载中');
        if (rows.length === 0) return %s ? empty : (empty || !loading);
        return %s ? rows.every(r => r.innerText.includes(arguments[0])) : false;
        """
        if expect_hit is True:
            script, msg = cond % ("false", "true"), "搜索「%s」后仍有不匹配的行" % text
        elif expect_hit is False:
            script, msg = cond % ("true", "false"), "搜索「%s」未显示空态" % text
        else:
            script, msg = cond % ("true", "true"), "搜索「%s」后列表未刷新" % text
        self.wait.until(lambda d: d.execute_script(script, text), message=msg)
        self.wait_rows()
        return self

    def wait_until_total(self, expected, timeout=None):
        """等总数回到某个值（导入 dry-run 不应改变题库总量）。"""
        self.wait_for(lambda d: self.total() == expected, timeout=timeout,
                      message="题库总数未回到 %d（当前 %s）" % (expected, self.total()))
        return self

    def wait_until_total(self, expected, timeout=None):
        """等总数回到某个值（导入 dry-run 不应改变题库总量）。"""
        self.wait_for(lambda d: self.total() == expected, timeout=timeout,
                      message="题库总数未回到 %d（当前 %s）" % (expected, self.total()))
        return self

    def reset(self):
        before = self.page_info()
        self.click(self.L["reset"])
        self.wait.until(lambda d: self.page_info() != before or self.range_from() == 1,
                        message="重置后列表未恢复")
        self.wait_rows()
        return self

    def empty_state(self):
        return "还没有符合条件" in (self.js_text("#question-rows") or "")

    # ------------------------------------------------------------ 行内操作
    def edit_row(self, index):
        self.js("const rows=[...document.querySelectorAll('#question-rows tr')]"
                ".filter(t=>t.querySelector('button[data-id]'));"
                "rows[arguments[0]].querySelector(\"a[href*='/edit/']\").click();", index)
        self.wait_url("/edit/")
        return self

    def disable_row(self, index):
        """点「停用」→ 处理原生 confirm → 等提示。"""
        self.js("const rows=[...document.querySelectorAll('#question-rows tr')]"
                ".filter(t=>t.querySelector('button[data-id]'));"
                "rows[arguments[0]].querySelector('.btn-delete').click();", index)
        text = self.accept_alert()
        self.wait_toast("停用")
        return text

    def ai_explain_row(self, index):
        self.js("const rows=[...document.querySelectorAll('#question-rows tr')]"
                ".filter(t=>t.querySelector('button[data-id]'));"
                "rows[arguments[0]].querySelector('.btn-explain').click();", index)
        return self

    # ------------------------------------------------------------ 导入 / 导出
    def open_import(self):
        self.click('[data-bs-target="#importModal"]')
        Modal(self, self.L["import_modal"]).wait_open()
        return self

    def choose_import_file(self, path):
        self.driver.find_element(By.CSS_SELECTOR, self.L["import_file"]).send_keys(path)
        self.wait.until(lambda d: "已选择" in (self.js_text("#import-file-name") or ""),
                        message="文件名未回显")
        return self

    def run_import(self):
        self.click(self.L["import_btn"])
        self.wait.until(lambda d: (self.js_text("#import-result") or "").strip() != "",
                        message="导入结果为空")
        return self

    def import_result_text(self):
        return self.js_text(self.L["import_result"])

    def export_file(self, kind="xlsx"):
        """点导出，返回落盘的文件路径。

        实现是 `API.download()` → `location.href = /questions/export/?...`：
        浏览器把它当附件下载，**页面 URL 不变、也不开新窗口**，
        所以用例原预期「窗口句柄 +1」是错的（见 docs/05 §5.1 修订）。
        真正的可验证信号是文件落盘，因此这里用下载目录 + 文件出现来断言。
        """
        return self.download(lambda: self.click(self.L["export_%s" % kind]),
                             suffix="." + kind)

    def template_file(self):
        """下载导入模板（弹窗里的「下载模板」链接）。"""
        def _click():
            self.js("document.getElementById('download-template-2').click();")
        return self.download(_click, suffix=".csv")


class QuestionEditorPage(BasePage):
    """题目新增 / 编辑页（同一个页面，靠 URL 区分）。"""
    path = "/question-bank/new/"
    ready = "#q-stem"

    L = {
        "type": "#q-type",
        "difficulty": "#q-difficulty",
        "score": "#q-score",
        "stem": "#q-stem",
        "options_block": "#options-block",
        "options_list": "#options-list",
        "add_option": "#btn-add-option",
        "options_hint": "#options-hint",
        "answer_block": "#answer-block",
        "answer": "#q-answer",
        "analysis": "#q-analysis",
        "subject": "#q-subject",
        "active": "#q-active",
        "reviewed": "#q-reviewed",
        "kp_names": "#kp-names",
        "save": "#btn-save",
        "ai_explain": "#btn-ai-explain",
    }

    def open_edit(self, question_id):
        self.driver.get(config.BASE_URL + "/question-bank/%s/edit/" % question_id)
        self.wait_ready()
        self.wait_input_value(self.L["stem"])       # textarea 只能读 value
        return self

    def set_type(self, value):
        self.select_by_value(self.L["type"], value)
        self.wait.until(lambda d: d.execute_script(
            "return document.querySelector('#q-type').value") == value, message="题型未切换")
        return self

    def block_shown(self, name):
        return self.js("const el=document.querySelector(arguments[0]);"
                       "return el && getComputedStyle(el).display!=='none';", self.L[name])

    def option_count(self):
        return self.count("#options-list .option-row")

    def option_rows(self):
        return self.js(
            "return [...document.querySelectorAll('#options-list .option-row')].map(r=>({"
            " label:(r.querySelector('.option-label-input')||{}).value||'',"
            " content:(r.querySelector('.option-content')||{}).value||'',"
            " correct:!!(r.querySelector('.option-correct')||{}).checked}));")

    def add_option(self):
        before = self.option_count()
        self.click(self.L["add_option"])
        self.wait.until(lambda d: self.option_count() == before + 1,
                        message="添加选项后行数未增加")
        return self

    def fill_option(self, index, content, correct=False):
        # 选项行是 JS 按题型渲染出来的，页面 ready 时可能还没渲染完
        self.wait.until(lambda d: self.option_count() >= index + 1,
                        message="选项行还没渲染到第 %d 行" % (index + 1))
        self.js("const rows=[...document.querySelectorAll('#options-list .option-row')];"
                "const r=rows[arguments[0]];"
                "r.querySelector('.option-content').value=arguments[1];"
                "r.querySelector('.option-content').dispatchEvent(new Event('input'));"
                "const c=r.querySelector('.option-correct');"
                "c.checked=arguments[2];"
                "c.dispatchEvent(new Event('change'));", index, content, correct)
        return self

    def fill(self, stem=None, score=None, answer=None, analysis=None, subject=None):
        if stem is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["stem"], stem)
        if score is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["score"], str(score))
        if answer is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["answer"], answer)
        if analysis is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["analysis"], analysis)
        if subject is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["subject"], subject)
        return self

    def values(self):
        return self.js(
            "const g=id=>{const e=document.querySelector(id);return e?e.value:null;};"
            "return {stem:g('#q-stem'), type:g('#q-type'), score:g('#q-score'),"
            " difficulty:g('#q-difficulty'), subject:g('#q-subject'),"
            " answer:g('#q-answer'), analysis:g('#q-analysis')};")

    def save(self):
        self.click(self.L["save"])
        return self

    def save_in_place(self):
        """保存并等提示——**编辑**分支不跳转（`save()` 只在新建时 location.href 回列表）。"""
        self.save()
        self.wait_toast("已更新")
        return self

    def save_expect_list(self):
        """保存成功后跳到题库列表。"""
        self.save()
        self.wait_url("/question-bank/")
        self.wait.until(lambda d: "/edit/" not in d.current_url and
                        not d.current_url.endswith("/new/"),
                        message="保存后未离开编辑页（当前 %s）" % self.driver.current_url)
        return QuestionBankPage(self.driver)


class KnowledgePointPage(BasePage):
    """知识点维护：左侧树 + 右侧表单（新建/编辑共用一个表单）。"""
    path = "/knowledge-points/"
    ready = "#tree-container"

    L = {
        "tree": "#tree-container",
        "nodes": "#tree-container .tree-node",
        "node_name": "#tree-container .node-name",
        "form_title": "#form-title",
        "name": "#kp-name",
        "code": "#kp-code",
        "parent": "#kp-parent",
        "subject": "#kp-subject",
        "order": "#kp-order",
        "desc": "#kp-desc",
        "active": "#kp-active",
        "save": "#btn-save",
        "reset_form": "#btn-reset-form",
        "add_root": "#btn-add-root",
        "refresh": "#btn-refresh",
        "subject_filter": "#f-subject",
    }

    def wait_tree(self):
        self.wait.until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "#tree-container .tree-node")) > 0
            or "还没有知识点" in (d.find_element(By.CSS_SELECTOR, "#tree-container").text or ""),
            message="知识点树未渲染")
        return self

    def node_names(self):
        self.wait_tree()
        return self.texts(self.L["node_name"])

    def node_count(self):
        self.wait_tree()                     # 树是 fetch 注入的，不等就会读到 0
        return self.count(self.L["nodes"])

    def create_root(self, name, code="", subject=""):
        self.click(self.L["add_root"])
        self.fill(name=name, code=code, subject=subject)
        self.click(self.L["save"])
        return self

    def fill(self, name=None, code=None, subject=None, desc=None):
        for sel, val in ((self.L["name"], name), (self.L["code"], code),
                         (self.L["subject"], subject), (self.L["desc"], desc)):
            if val is not None:
                self.js("const el=document.querySelector(arguments[0]);"
                        "el.value=arguments[1];el.dispatchEvent(new Event('input'));", sel, val)
        return self

    def click_node_edit(self, name):
        self.js("const nodes=[...document.querySelectorAll('#tree-container .tree-node')];"
                "const n=nodes.find(x=>x.querySelector('.node-name').innerText.trim()===arguments[0]);"
                "if(!n) return false;"
                "n.querySelector('.btn-edit').click();return true;", name)
        self.wait.until(lambda d: name in (self.value(self.L["name"]) or ""),
                        message="点编辑后表单未回填「%s」" % name)
        return self

    def refresh(self):
        """点「刷新」重载知识点树（保存后页面自己也会 load，这里用于断言持久化）。"""
        before = self.node_count()
        self.click(self.L["refresh"])
        self.wait.until(lambda d: "加载中" not in (self.js_text(self.L["tree"]) or "")
                        or self.node_count() != before,
                        message="刷新后树未重载")
        self.wait_tree()
        return self

    def refresh(self):
        """点「刷新」重载知识点树（保存后页面自己也会 load，这里用于断言持久化）。"""
        before = self.node_count()
        self.click(self.L["refresh"])
        self.wait.until(lambda d: "加载中" not in (self.js_text(self.L["tree"]) or "")
                        or self.node_count() != before,
                        message="刷新后树未重载")
        self.wait_tree()
        return self

    def is_active_checked(self):
        return self.js("return document.querySelector('#kp-active').checked")

    def set_active(self, flag):
        self.js("const el=document.querySelector('#kp-active');"
                "el.checked=arguments[0];el.dispatchEvent(new Event('change'));", flag)
        return self


class PaperListPage(BasePage):
    """试卷列表：统计卡 / 筛选 / 翻页 / 行内操作。

    列表行内按钮是 `button[data-act]`（export / clone / publish / draft / delete），
    但**行本身没有 data-id**，只能靠标题链接 `a[href*='/compose/']` 认行。
    """
    path = "/papers/"
    ready = "#paperRows"

    L = {
        "rows": "#paperRows tr",
        # 注意：每行有**两个**指向 /compose/ 的链接（标题 + 操作列图标按钮），
        # 只取第一列那个，否则行数会翻倍、标题列表里混进空串。
        "title_link": "#paperRows td:first-child a[href*='/compose/']",
        "keyword": "#filterKeyword",
        "status": "#filterStatus",
        "subject": "#filterSubject",
        "mode": "#filterMode",
        "search": "#btnSearch",
        "reset": "#btnReset",
        "stat_total": "#statTotal",
        "stat_draft": "#statDraft",
        "stat_published": "#statPublished",
        "list_summary": "#listSummary",
        "page_info": "#pageInfo",
        "pager": "#pager",
    }

    def wait_rows(self):
        self.wait.until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, self.L["title_link"])) > 0
            or "还没有试卷" in (self.js_text("#paperRows") or ""),
            message="试卷列表未渲染出数据行")
        return self

    def row_count(self):
        self.wait_rows()
        return self.count(self.L["title_link"])

    def titles(self):
        self.wait_rows()
        return self.js_texts(self.L["title_link"])

    def row_index_of(self, title):
        return self.js(
            "const rows=[...document.querySelectorAll('#paperRows tr')]"
            ".filter(r=>r.querySelector('a[href*=\"/compose/\"]'));"
            "return rows.findIndex(r=>r.innerText.includes(arguments[0]));", title)

    def status_of(self, index):
        """第 2 列的状态徽章文案。"""
        return self.js("const rows=[...document.querySelectorAll('#paperRows tr')]"
                       ".filter(r=>r.querySelector('a[href*=\"/compose/\"]'));"
                       "if(!rows[arguments[0]]) return '';"
                       "return rows[arguments[0]].querySelectorAll('td')[1].innerText.trim();", index)

    def questions_of(self, index):
        return self.js("const rows=[...document.querySelectorAll('#paperRows tr')]"
                       ".filter(r=>r.querySelector('a[href*=\"/compose/\"]'));"
                       "if(!rows[arguments[0]]) return '';"
                       "return rows[arguments[0]].querySelectorAll('td')[2].innerText.trim();", index)

    def stat_total(self):
        return self.js_text(self.L["stat_total"])

    def stats(self):
        return {k: self.js_text(self.L[k]) for k in ("stat_total", "stat_draft", "stat_published")}

    # ------------------------------------------------------------ 筛选
    def set_status(self, value):
        self.select_by_value(self.L["status"], value)
        return self

    def set_keyword(self, text):
        self.js("const el=document.querySelector(arguments[0]);"
                "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                self.L["keyword"], text)
        return self

    def do_search(self):
        before = self.js_text(self.L["list_summary"])
        self.click(self.L["search"])
        self.wait.until(lambda d: self.js_text(self.L["list_summary"]) != before
                        or "加载中" not in (self.js_text(self.L["list_summary"]) or ""),
                        message="筛选后列表未刷新")
        self.wait_rows()
        return self

    def reset(self):
        self.click(self.L["reset"])
        self.wait.until(lambda d: self.js_text(self.L["page_info"]) or True,
                        message="重置未生效")
        self.wait_rows()
        return self

    def empty_state(self):
        return "还没有试卷" in (self.js_text("#paperRows") or "")

    # ------------------------------------------------------------ 行内操作
    def act(self, index, action):
        """点行内按钮：export / clone / publish / draft / delete。

        必须用**真实指针**点击，不能用 JS `b.click()`：
        「导出」走的是 `window.open(url, "_blank")`，Chrome 会把"非用户手势触发的
        window.open"当弹窗拦掉——JS 点击时一个新窗口都不会开（实测踩过）。
        做法是先用 JS 给目标按钮打个临时标记，再用 BasePage.click 走真实指针。
        """
        mark = "uiat-act-%s" % action
        found = self.js(
            "const rows=[...document.querySelectorAll('#paperRows tr')]"
            ".filter(r=>r.querySelector('a[href*=\"/compose/\"]'));"
            "const row=rows[arguments[0]]; if(!row) return false;"
            "const b=row.querySelector('button[data-act=\"' + arguments[1] + '\"]');"
            "if(!b) return false;"
            "document.querySelectorAll('[data-uiat-act]').forEach(e=>e.removeAttribute('data-uiat-act'));"
            "b.setAttribute('data-uiat-act', arguments[2]); return true;", index, action, mark)
        assert found, "第 %d 行没有「%s」按钮" % (index, action)
        try:
            self.click('[data-uiat-act="%s"]' % mark)
        finally:
            self.js("document.querySelectorAll('[data-uiat-act]')"
                    ".forEach(e=>e.removeAttribute('data-uiat-act'));")
        return self

    def open_compose(self, index):
        self.js("const rows=[...document.querySelectorAll('#paperRows tr')]"
                ".filter(r=>r.querySelector('a[href*=\"/compose/\"]'));"
                "rows[arguments[0]].querySelector('a[href*=\"/compose/\"]').click();", index)
        self.wait_url("/compose/")
        return self

    # ------------------------------------------------------------ 导出（拦截 window.open）
    def hook_window_open(self):
        """接管 `window.open`，只记录参数、不真的开窗。

        为什么不验"句柄 +1"：列表「导出」是 `window.open(url, "_blank")`，
        headless 下是否真开窗取决于浏览器弹窗策略（--disable-popup-blocking、
        用户手势判定……），属于**浏览器行为**而不是被测逻辑，验它只会带来假失败。
        被测系统该保证的是"点导出会用正确的地址发起导出"，所以拦调用看参数。
        """
        self.js("""
            window.__uiat_opened = [];
            window.open = function (url, target) {
                window.__uiat_opened.push({url: String(url), target: target || ""});
                return null;
            };
        """)
        return self

    def opened_windows(self):
        return self.js("return window.__uiat_opened || [];") or []

    # ------------------------------------------------------------ 导出（拦截 window.open）
    def hook_window_open(self):
        """接管 `window.open`，只记录参数、不真的开窗。

        为什么不验"句柄 +1"：列表「导出」是 `window.open(url, "_blank")`，
        headless 下是否真开窗取决于浏览器弹窗策略（--disable-popup-blocking、
        用户手势判定……），属于**浏览器行为**而不是被测逻辑，验它只会带来假失败。
        被测系统该保证的是"点导出会用正确的地址发起导出"，所以拦调用看参数。
        """
        self.js("""
            window.__uiat_opened = [];
            window.open = function (url, target) {
                window.__uiat_opened.push({url: String(url), target: target || ""});
                return null;
            };
        """)
        return self

    def opened_windows(self):
        return self.js("return window.__uiat_opened || [];") or []

    # ------------------------------------------------------------ 分页
    def page_info(self):
        return self.js_text(self.L["page_info"])

    def range_from(self):
        import re
        m = re.search(r"第?\s*(\d+)\s*-\s*\d+\s*/?\s*共", self.page_info())
        if m:
            return int(m.group(1))
        m = re.search(r"共\s*(\d+)\s*条", self.page_info())
        return int(m.group(1)) if m else 1

    def pager_links(self):
        """分页链接数量。

        **只有 1 页时 `#pager` 会被整体清空**（`pager.innerHTML = ""`）——
        没有 « » 按钮可查，所以"单页禁用"只能断言"分页器不渲染"。
        """
        return self.count("#pager a[data-page]")

    def pager_links(self):
        """分页链接数量。

        **只有 1 页时 `#pager` 会被整体清空**（`pager.innerHTML = ""`）——
        没有 « » 按钮可查，所以"单页禁用"只能断言"分页器不渲染"。
        """
        return self.count("#pager a[data-page]")

    def pager_class_of(self, label):
        return self.js("const links=[...document.querySelectorAll('#pager a[data-page]')];"
                       "const a=links.find(x=>x.innerText.trim()===arguments[0]);"
                       "return a ? a.parentElement.className : '';", label)


class PaperComposePage(BasePage):
    """组卷工作台（新增 `/papers/new/`，编辑 `/papers/{id}/compose/`）。

    3 个容易搞混的按钮，实测确认过：
      `#btnPreview` 「预览」→ 走 `/papers/ai-compose/` 带 `dry_run=True`，**只试算不落库**；
      `#btnCompose` 「一键组卷」→ 真生成（`generate_notes=True`）；
      `#btnRandomCompose` 「随机组卷」→ 真生成（按题量随机抽）。
    用例里的"试算（不落库）"必须点 `#btnPreview`，点错就会真的建出卷子来。
    """
    path = "/papers/new/"
    ready = "#paperTitle"

    L = {
        "title": "#paperTitle",
        "status_badge": "#statusBadge",
        "meta_count": "#metaCount",
        "meta_score": "#metaScore",
        "meta_duration": "#metaDuration",
        "meta_actual": "#metaActual",
        "save_title": "#btnSaveTitle",
        "export_btn": "#btnExport",
        "clone": "#btnClone",
        "publish": "#btnPublish",
        "kp_tree": "#kpTree",
        "kp_box": "#kpTree input[data-kp]",
        "kp_toggle_all": "#kpToggleAll",
        "blueprint_rows": "#blueprintRows",
        "blueprint_total": "#blueprintTotal",
        "add_row": "#btnAddRow",
        "pool_body": "#poolBody",
        "preview_btn": "#btnPreview",
        "preview_box": "#previewBox",
        "preview_body": "#previewBody",
        "compose_btn": "#btnCompose",
        "random_count": "#composeRandomCount",
        "random_btn": "#btnRandomCompose",
        "sheet_body": "#sheetBody",
        "open_picker": "#btnOpenPicker",
        "picker_modal": "#pickerModal",
        "pick_keyword": "#pickKeyword",
        "pick_search": "#btnPickSearch",
        "pick_summary": "#pickSummary",
        "pick_list": "#pickList",
        "pick_box": "#pickList input[data-pick]",
        "pick_count": "#pickCount",
        "pick_add": "#btnPickAdd",
        "subject": "#composeSubject",
        "duration": "#composeDuration",
        "difficulty": "#composeDifficulty",
    }

    def open_paper_for_new(self):
        """打开新建组卷页（还没有 paper_id，保存卷头等按钮是禁用的）。"""
        self.driver.get(config.BASE_URL + "/papers/new/")
        self.wait_ready()
        self.wait_loaded()
        return self

    def open_paper_for_new(self):
        """打开新建组卷页（还没有 paper_id，保存卷头等按钮是禁用的）。"""
        self.driver.get(config.BASE_URL + "/papers/new/")
        self.wait_ready()
        self.wait_loaded()
        return self

    def open_paper(self, paper_id):
        """打开已有卷的组卷页，并等**卷面**真正画完。

        `loadPaper()` 的顺序是 `applyHead()` → `renderSheet()`：卷头统计先更新、
        卷面后渲染。只等标题/题库池会出现「卷头已是 3 题、卷面还是 0 个 `.paper-q`」
        的中间态，`sheet_questions()` 读到 0 就是假失败（UI-PAP-06 曾因此报 0→4）。
        所以这里必须等卷面进入终态：有题目卡片，或明确显示「还没有题目」。
        """
        self.driver.get(config.BASE_URL + "/papers/%s/compose/" % paper_id)
        self.wait_ready()
        self.wait_input_value(self.L["title"])
        self.wait.until(lambda d: "加载中" not in (self.js_text(self.L["pool_body"]) or ""),
                        message="组卷页题库池未加载")
        self.wait.until(lambda d: self.count(self.L["sheet_body"] + " .paper-q") > 0
                        or "还没有题目" in (self.js_text(self.L["sheet_body"]) or ""),
                        message="组卷页卷面未渲染（`#sheetBody` 仍停在加载中）")
        return self

    def wait_loaded(self):
        """新建页没有 loadPaper，等知识点树与题库池都渲染完。"""
        self.wait.until(lambda d: self.count(self.L["kp_box"]) > 0
                        or "还没有知识点" in (self.js_text(self.L["kp_tree"]) or ""),
                        message="知识点树未渲染")
        self.wait.until(lambda d: "加载中" not in (self.js_text(self.L["pool_body"]) or ""),
                        message="题库池一直停在加载中")
        return self

    # ------------------------------------------------------------ 知识点 / 蓝图
    def kp_names(self):
        return self.js_texts("#kpTree label")

    def check_kp(self, index=0):
        """勾选第 index 个知识点（触发 loadPool）。"""
        before = self.pool_text()
        self.js("const boxes=[...document.querySelectorAll('#kpTree input[data-kp]')];"
                "const b=boxes[arguments[0]];"
                "b.checked=true; b.dispatchEvent(new Event('change'));", index)
        self.wait.until(lambda d: self.pool_text() != before
                        or "可用题" in (self.pool_text() or ""),
                        message="勾选知识点后题库池没刷新")
        return self

    def check_kp_by_name(self, name):
        """勾选指定名称的知识点，并等题池真的按新条件刷新。

        等待判据是**可用题量发生变化**，不能等"页面出现『可用题』字样"——
        那个字样一直都在，条件会立刻满足，读到的还是旧值（踩过）。
        """
        return self._toggle_kp(name, True)

    def check_kp_by_name_off(self, name):
        """取消勾选指定知识点。"""
        return self._toggle_kp(name, False)

    def _toggle_kp(self, name, checked):
        before_total = self.pool_total()
        ok = self.js(
            "const labels=[...document.querySelectorAll('#kpTree label')];"
            "const l=labels.find(x=>x.innerText.includes(arguments[0]));"
            "if(!l) return false;"
            "const b=l.querySelector('input[data-kp]');"
            "b.scrollIntoView({block:'center'});"
            "if (b.checked !== arguments[1]) b.click();"
            "return true;", name, checked)
        assert ok, "知识点树里找不到「%s」" % name
        # 必须同时满足「算出了有效题量」和「与之前不同」：
        # 只看"变化"会在加载中的瞬间通过（那时 pool_total 是 -1，正好不等于旧值）。
        self.wait.until(
            lambda d: self.pool_total() > 0 and self.pool_total() != before_total,
            message="勾选/取消「%s」后题池没有刷新（仍为 %s 道）"
                    % (name, self.pool_total()))
        return self

    def check_kp_by_name(self, name):
        """勾选指定名称的知识点，并等题池真的按新条件刷新。

        等待判据是**可用题量发生变化**，不能等"页面出现『可用题』字样"——
        那个字样一直都在，条件会立刻满足，读到的还是旧值（踩过）。
        """
        return self._toggle_kp(name, True)

    def check_kp_by_name_off(self, name):
        """取消勾选指定知识点。"""
        return self._toggle_kp(name, False)

    def _toggle_kp(self, name, checked):
        before_total = self.pool_total()
        ok = self.js(
            "const labels=[...document.querySelectorAll('#kpTree label')];"
            "const l=labels.find(x=>x.innerText.includes(arguments[0]));"
            "if(!l) return false;"
            "const b=l.querySelector('input[data-kp]');"
            "b.scrollIntoView({block:'center'});"
            "if (b.checked !== arguments[1]) b.click();"
            "return true;", name, checked)
        assert ok, "知识点树里找不到「%s」" % name
        # 必须同时满足「算出了有效题量」和「与之前不同」：
        # 只看"变化"会在加载中的瞬间通过（那时 pool_total 是 -1，正好不等于旧值）。
        self.wait.until(
            lambda d: self.pool_total() > 0 and self.pool_total() != before_total,
            message="勾选/取消「%s」后题池没有刷新（仍为 %s 道）"
                    % (name, self.pool_total()))
        return self

    def checked_kp_count(self):
        return self.js("return [...document.querySelectorAll('#kpTree input[data-kp]')]"
                       ".filter(b=>b.checked).length")

    def pool_text(self):
        return self.js_text(self.L["pool_body"])

    def pool_total(self):
        import re
        m = re.search(r"共\s*(\d+)\s*道可用题", self.pool_text() or "")
        return int(m.group(1)) if m else -1

    def blueprint_count(self):
        return self.count("#blueprintRows .blueprint-row")

    def set_blueprint(self, index, count=None, score=None):
        """改蓝图第 index 行的题量 / 分值（input 事件即时生效）。"""
        if count is not None:
            self.js("const el=document.querySelector('#blueprintRows [data-bp-count=\"' + "
                    "arguments[0] + '\"]');"
                    "el.value=arguments[1]; el.dispatchEvent(new Event('input',{bubbles:true}));",
                    index, str(count))
        if score is not None:
            self.js("const el=document.querySelector('#blueprintRows [data-bp-score=\"' + "
                    "arguments[0] + '\"]');"
                    "el.value=arguments[1]; el.dispatchEvent(new Event('input',{bubbles:true}));",
                    index, str(score))
        return self

    def blueprint_plan(self):
        """蓝图当前各行：{type: count}，用于核对"题量与蓝图一致"。"""
        return self.js(
            "return [...document.querySelectorAll('#blueprintRows .blueprint-row')].map(r=>({"
            "type: r.querySelector('[data-bp-type]').value,"
            "count: Number(r.querySelector('[data-bp-count]').value)}));")

    # ------------------------------------------------------------ 试算 / 组卷
    def preview(self):
        """点「预览」= dry_run 试算，不落库。"""
        self.click(self.L["preview_btn"])
        self.wait.until(lambda d: not self.js("return document.querySelector('#previewBox')"
                                              ".classList.contains('d-none')"),
                        message="预览面板没有展开（可能是接口失败）")
        self.wait.until(lambda d: (self.js_text(self.L["preview_body"]) or "").strip() != "",
                        message="预览内容为空")
        return self

    def preview_text(self):
        return self.js_text(self.L["preview_body"])

    def compose(self):
        self.click(self.L["compose_btn"])
        self.wait_toast("已生成")
        return self

    def random_compose(self, count=5):
        self.js("const el=document.querySelector(arguments[0]);"
                "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                self.L["random_count"], str(count))
        self.click(self.L["random_btn"])
        self.wait_toast("随机生成")
        return self

    # ------------------------------------------------------------ 卷头 / 状态
    def set_title(self, text):
        self.js("const el=document.querySelector(arguments[0]);"
                "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                self.L["title"], text)
        return self

    def title_value(self):
        return self.value(self.L["title"])

    def save_title(self):
        self.click(self.L["save_title"])
        self.wait_toast("已保存")
        return self

    def save_title_disabled(self):
        return self.attr(self.L["save_title"], "disabled") is not None

    def status_text(self):
        return self.js_text(self.L["status_badge"])

    def publish(self):
        """发布：原生 confirm 要先接受，再等提示。"""
        self.click(self.L["publish"])
        text = self.accept_alert()
        self.wait_toast("已发布")
        return text

    def clone(self):
        """复制并等跳转到副本。

        `clonePaper()` 是「toast → 立刻 location.href」，跳转会清掉 toast，
        所以不能靠 toast 判断成功，只能等 URL 变成**另一份**卷子。
        """
        before = self.driver.current_url
        self.click(self.L["clone"])
        self.wait.until(lambda d: d.current_url != before and "/compose/" in d.current_url,
                        message="复制后没有跳转到副本（仍在 %s）" % before)
        self.wait_ready()
        self.wait_input_value(self.L["title"])
        # 跳转后是全新文档，卷面要等 loadPaper() 渲染完（否则会读到 0 题）
        self.wait.until(lambda d: self.count("#sheetBody .paper-q") > 0 or self.sheet_empty(),
                        message="副本卷面没有渲染出来")
        return self

    def paper_id(self):
        """从 URL 里取当前卷 id（/papers/123/compose/）。"""
        import re
        m = re.search(r"/papers/(\d+)/compose/", self.driver.current_url)
        return int(m.group(1)) if m else None

    def meta(self):
        return {k: self.js_text(self.L[k]) for k in
                ("meta_count", "meta_score", "meta_actual")}

    def sheet_questions(self):
        return self.count("#sheetBody .paper-q")

    def sheet_empty(self):
        return "还没有题目" in (self.js_text(self.L["sheet_body"]) or "")

    # ------------------------------------------------------------ 从题库加题
    def open_picker(self):
        self.click(self.L["open_picker"])
        Modal(self, self.L["picker_modal"]).wait_open()
        self.wait.until(lambda d: self.count(self.L["pick_box"]) > 0
                        or "没有匹配" in (self.js_text(self.L["pick_list"]) or ""),
                        message="选题器列表未渲染")
        return self

    def picker_search(self, keyword):
        before = self.js_text(self.L["pick_summary"])
        self.js("const el=document.querySelector(arguments[0]);"
                "el.value=arguments[1];", self.L["pick_keyword"], keyword)
        self.click(self.L["pick_search"])
        self.wait.until(lambda d: self.js_text(self.L["pick_summary"]) != before,
                        message="选题器搜索无响应")
        return self

    def pick_first(self, n=1):
        self.js("const boxes=[...document.querySelectorAll('#pickList input[data-pick]')];"
                "boxes.slice(0, arguments[0]).forEach(b=>{b.checked=true;"
                "b.dispatchEvent(new Event('change',{bubbles:true}));});", n)
        self.wait.until(lambda d: self.js_text(self.L["pick_count"]) == str(n),
                        message="勾选题目数不符")
        return self

    def add_picked(self, added=1):
        """把选题器里勾中的题加进卷面，并等卷头统计与卷面**都**重渲染完。

        toast「已添加」和弹窗关闭都早于 `loadPaper()` 回来，直接读卷面会读到旧值。
        这里以加题前的卷头题数为基准，等 `#metaCount` 与 `.paper-q` 数量同时到位。
        """
        before = int(self.js_text(self.L["meta_count"]) or 0)
        self.click(self.L["pick_add"])
        self.wait_toast("已添加")
        self.wait.until(lambda d: not Modal(self, self.L["picker_modal"]).is_open(
            timeout=config.SHORT_TIMEOUT), message="加题后选题器未关闭")
        self.wait.until(lambda d: int(self.js_text(self.L["meta_count"]) or 0) == before + added,
                        message="加题后卷头统计未同步（基准 %d）" % before)
        self.wait.until(lambda d: self.count(self.L["sheet_body"] + " .paper-q") == before + added,
                        message="加题后卷面未重渲染（基准 %d）" % before)
        return self


class ExamListPage(BasePage):
    """考试列表：统计卡 / 筛选 / 分页 / 行内操作 / 新建编辑弹窗。

    三个实测细节决定断言口径：
      1. 分页是 `#btn-prev` / `#btn-next` **按钮**，不是 `a[data-page]`；
         越界靠 `if (page < totalPages)` 直接 return，所以只能看"页码变没变"；
      2. 状态切换（发布/开始/结束/归档）**没有二次确认**，点了就生效；
      3. 只有「删除」有原生 `confirm()`。
    """
    path = "/exams/"
    ready = "#exam-body"

    L = {
        "rows": "#exam-body tr[data-id]",
        "new_btn": "#btn-new-exam",
        "modal": "#examModal",
        "modal_title": "#exam-modal-title",
        "title": "#e-title",
        "paper": "#e-paper",
        "desc": "#e-desc",
        "start": "#e-start",
        "end": "#e-end",
        "duration": "#e-duration",
        "pass": "#e-pass",
        "attempts": "#e-attempts",
        "switch": "#e-switch",
        "open_all": "#e-open-all",
        "save": "#btn-save-exam",
        "status": "#f-status",
        "keyword": "#f-keyword",
        "reset": "#btn-reset",
        "stat_total": "#stat-total",
        "stat_running": "#stat-running",
        "page_info": "#page-info",
        "prev": "#btn-prev",
        "next": "#btn-next",
    }

    def wait_rows(self):
        self.wait.until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "#exam-body tr[data-id]")) > 0
            or "没有" in (self.js_text("#exam-body") or "") or "暂无" in (self.js_text("#exam-body") or ""),
            message="考试列表未渲染出数据行")
        return self

    def row_count(self):
        self.wait_rows()
        return self.count(self.L["rows"])

    def titles(self):
        self.wait_rows()
        return self.js_texts("#exam-body tr[data-id] .exam-row-title")

    def row_index_of(self, title):
        return self.js(
            "const rows=[...document.querySelectorAll('#exam-body tr[data-id]')];"
            "return rows.findIndex(r=>r.innerText.includes(arguments[0]));", title)

    def status_of(self, index):
        """第 3 列的状态徽章文案。"""
        return self.js("const rows=[...document.querySelectorAll('#exam-body tr[data-id]')];"
                       "if(!rows[arguments[0]]) return '';"
                       "const b=rows[arguments[0]].querySelectorAll('td')[2];"
                       "return b? b.innerText.trim():'';", index)

    def paper_of(self, index):
        return self.js("const rows=[...document.querySelectorAll('#exam-body tr[data-id]')];"
                       "if(!rows[arguments[0]]) return '';"
                       "return rows[arguments[0]].querySelectorAll('td')[1].innerText.trim();", index)

    def stat_values(self):
        return {k: self.js_text(self.L[k]) for k in ("stat_total", "stat_running")}

    # ------------------------------------------------------------ 筛选
    def wait_table_stable(self, timeout=None):
        """等表格连续两次采样一致且不含「加载中」。

        为什么不用"内容变了"当判据：筛出来的结果可能和筛选前**完全一样**
        （比如列表里本来只有已发布的考试），那样等到超时也等不到变化。
        """
        import time as _t
        deadline = _t.time() + (timeout or config.WAIT_TIMEOUT)
        last = None
        while _t.time() < deadline:
            cur = self.js_text("#exam-body") or ""
            if cur and "加载中" not in cur and cur == last:
                return self
            last = cur
            _t.sleep(0.25)
        raise AssertionError("考试列表一直没有稳定下来（当前：%r）"
                             % (self.js_text("#exam-body") or "")[:80])

    def _wait_filter_applied(self, before):
        """筛选/搜索后先等列表**真的开始变**，再等它稳定。

        直接调 `wait_table_stable()` 会立刻通过——此时列表还是旧内容，
        断言就会读到未筛选的数据（搜索"命中 4 条"、筛选"仍有其它状态"都是这么来的）。
        """
        try:
            self.wait_for(
                lambda d: self.js_text("#exam-body") != before
                or "加载中" in (self.js_text("#exam-body") or ""),
                timeout=5, message="筛选未触发列表刷新")
        except Exception:                                # noqa: BLE001
            pass                                         # 结果与筛选前一致时属正常
        self.wait_table_stable()
        return self

    def set_status(self, value):
        before = self.js_text("#exam-body")
        self.select_by_value(self.L["status"], value)
        return self._wait_filter_applied(before)

    def keyword(self, text):
        """关键词是 **input + 防抖** 触发（无搜索按钮，后端参数名是 search）。"""
        before = self.js_text("#exam-body")
        self.js("const el=document.querySelector(arguments[0]);"
                "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                self.L["keyword"], text)
        return self._wait_filter_applied(before)

    def reset(self):
        before = self.js_text("#exam-body")
        self.click(self.L["reset"])
        return self._wait_filter_applied(before)

    def empty_state(self):
        body = self.js_text("#exam-body") or ""
        return "没有" in body or "暂无" in body

    # ------------------------------------------------------------ 分页
    def page_info(self):
        return self.js_text(self.L["page_info"])

    def page_no(self):
        import re
        m = re.search(r"第\s*(\d+)\s*/\s*(\d+)", self.page_info())
        return (int(m.group(1)), int(m.group(2))) if m else (-1, -1)

    def next_disabled(self):
        return self.attr(self.L["next"], "disabled") is not None

    def prev_disabled(self):
        return self.attr(self.L["prev"], "disabled") is not None

    def goto_next_page(self):
        before = self.page_no()
        self.click(self.L["next"])
        self.wait.until(lambda d: self.page_no() != before,
                        message="点「下一页」页码没变（%s）" % (before,))
        self.wait_rows()
        return self

    # ------------------------------------------------------------ 新建 / 编辑
    def open_new(self):
        self.click(self.L["new_btn"])
        Modal(self, self.L["modal"]).wait_open()
        # 试卷下拉是异步填充的，必须等它出现真实选项再操作
        self.wait.until(lambda d: self.count(self.L["paper"] + " option") > 1,
                        message="新建考试弹窗的试卷下拉没有加载出选项")
        return self

    def open_edit(self, index):
        self.row_action(index, "edit")
        Modal(self, self.L["modal"]).wait_open()
        self.wait_input_value(self.L["title"])
        return self

    def paper_options(self):
        return self.js_texts(self.L["paper"] + " option")

    def fill(self, title=None, paper_index=1, start=None, end=None,
             duration=None, attempts=None):
        """填表。paper_index 是下拉里的序号（0 是「请选择试卷」占位）。"""
        if title is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["title"], title)
        if paper_index is not None:
            self.js("const s=document.querySelector(arguments[0]);"
                    "s.selectedIndex=arguments[1];"
                    "s.dispatchEvent(new Event('change'));", self.L["paper"], paper_index)
        if start is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["start"], start)
        if end is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["end"], end)
        if duration is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["duration"], str(duration))
        if attempts is not None:
            self.js("const el=document.querySelector(arguments[0]);"
                    "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                    self.L["attempts"], str(attempts))
        return self

    def save(self):
        self.click(self.L["save"])
        return self

    def save_expect_created(self):
        """新建保存成功 → 弹窗关闭 + 提示「考试已创建」。"""
        self.save()
        self.wait_toast("已创建")
        self.wait.until(lambda d: not Modal(self, self.L["modal"]).is_open(
            timeout=config.SHORT_TIMEOUT), message="保存后弹窗未关闭")
        self.wait_rows()
        return self

    def save_expect_updated(self):
        self.save()
        self.wait_toast("已保存")
        self.wait.until(lambda d: not Modal(self, self.L["modal"]).is_open(
            timeout=config.SHORT_TIMEOUT), message="保存后弹窗未关闭")
        self.wait_rows()
        return self

    def modal_open(self):
        return Modal(self, self.L["modal"]).is_open(timeout=config.SHORT_TIMEOUT)

    # ------------------------------------------------------------ 行内操作
    def row_action(self, index, action, status=None):
        """点行内按钮：edit / status / delete / monitor。

        .act-status 是**无确认**的状态切换；.act-delete 有原生 confirm。
        全部用真实指针点击（列表重写会让 JS 触发的节点失效）。
        """
        if action == "monitor":
            sel = "a[href*='/monitor/']"
        elif action == "edit":
            sel = ".act-edit"
        elif action == "status":
            sel = '.act-status[data-status="%s"]' % status
        elif action == "delete":
            sel = ".act-delete"
        else:
            raise ValueError("未知操作：%s" % action)

        mark = "uiat-%s" % action
        found = self.js(
            "const rows=[...document.querySelectorAll('#exam-body tr[data-id]')];"
            "const row=rows[arguments[0]]; if(!row) return false;"
            "const el=row.querySelector(arguments[1]); if(!el) return false;"
            "document.querySelectorAll('[data-uiat-row]')"
            ".forEach(e=>e.removeAttribute('data-uiat-row'));"
            "el.setAttribute('data-uiat-row', arguments[2]); return true;",
            index, sel, mark)
        assert found, "第 %d 行没有「%s」操作（%s）" % (index, action, sel)
        try:
            self.click('[data-uiat-row="%s"]' % mark)
        finally:
            self.js("document.querySelectorAll('[data-uiat-row]')"
                    ".forEach(e=>e.removeAttribute('data-uiat-row'));")
        return self

    def change_status(self, index, status, confirm=False):
        self.row_action(index, "status", status)
        if confirm:
            self.accept_alert()
        self.wait.until(lambda d: "加载中" not in (self.js_text("#exam-body") or ""),
                        message="状态切换后列表未刷新")
        self.wait_rows()
        return self


class MonitorPage(BasePage):
    """考试监控页：概览卡 / 页签 / 只看嫌疑 / 刷新。

    「只看嫌疑」是**前端过滤**（`onlySuspicious` 变量 + rows.filter），
    不发新请求；页签切换才会重新拉数据。
    """
    path = "/exams/{exam_id}/monitor/"
    ready = "#exam-status"

    L = {
        "status": "#exam-status",
        "applicants": "#ov-applicants",
        "started": "#ov-started",
        "progress": "#ov-progress",
        "submitted": "#ov-submitted",
        "timeout": "#ov-timeout",
        "notstarted": "#ov-notstarted",
        "rows": "#attempt-body tr",
        "tabs": "#status-tabs button",
        "suspicious": "#btn-suspicious",
        "refresh": "#btn-refresh",
        "keyword": "#f-keyword",
    }

    KEYS = ("applicants", "started", "progress", "submitted", "timeout", "notstarted")

    def wait_loaded(self):
        """等**六张概览卡全部**填上数字。

        坑：这页有 `setInterval(load, 10000)` 自动刷新，每次刷新会先把卡片重置成
        「—」再填。只等某一张卡（或只读一次）很容易撞在重置窗口里读到「—」。
        """
        self.wait_for(
            lambda d: all((self.js_text(self.L[k]) or "").isdigit() for k in self.KEYS),
            timeout=config.WAIT_TIMEOUT,
            message="概览卡没有全部填上数字（当前 %s）"
                    % {k: self.js_text(self.L[k]) for k in self.KEYS})
        return self

    def overview(self):
        self.wait_loaded()
        return {k: self.js_text(self.L[k]) for k in self.KEYS}

    def row_count(self):
        return self.js(
            "const rows=[...document.querySelectorAll('#attempt-body tr')];"
            "if (rows.length === 1 && rows[0].innerText.includes('还没有人')) return 0;"
            "return rows.length;")

    def switch_tab(self, status):
        """切页签：data-status 为空表示「全部」。"""
        before = self.js_text("#attempt-body")
        self.js("const b=[...document.querySelectorAll('#status-tabs button')]"
                ".find(x=>x.dataset.status===arguments[0]);"
                "if(b) b.click();", status)
        self.wait.until(lambda d: self.js_text("#attempt-body") != before
                        or "加载中" not in (self.js_text("#attempt-body") or ""),
                        message="切页签后明细未刷新")
        return self

    def active_tab(self):
        return self.js("const b=document.querySelector('#status-tabs button.active');"
                       "return b? b.dataset.status : null;")

    def row_statuses(self):
        return self.js_texts("#attempt-body tr td:nth-child(2)")

    def toggle_suspicious(self):
        """切换「只看嫌疑」。

        注意：它不是纯前端过滤——点击后 `onlySuspicious` 翻转并**重新 load()**，
        所以不能点完立刻断言行数，要等列表内容真的变了。
        """
        before_rows = self.row_count()
        before_text = self.js_text("#attempt-body")
        self.click(self.L["suspicious"])
        self.wait.until(lambda d: self.js_text("#attempt-body") != before_text
                        or self.row_count() != before_rows,
                        message="点「只看嫌疑」后列表没有变化")
        return self

    def risk_rows(self):
        return self.count("#attempt-body tr.risk-row")

    def refresh(self):
        before = self.js_text("#attempt-body")
        self.click(self.L["refresh"])
        self.wait.until(lambda d: self.js_text("#attempt-body") != before
                        or "加载中" in (self.js_text("#attempt-body") or ""),
                        message="点刷新后明细没有开始重载")
        self.wait.until(lambda d: "加载中" not in (self.js_text("#attempt-body") or ""),
                        message="刷新后明细仍在加载")
        self.wait_loaded()
        return self

    def status_badge(self):
        """顶部的考试状态徽章文本。

        BUG-04 修复前：overview 没有 `computed_status_display`，前端 `|| ''` 把徽章
        写成空串。修复后后端补字段、前端兜底改「—」，这里应返回中文状态文案
        （进行中 / 已发布 / 已归档…）；`UI-EXM-08` 会把它与接口字段锁在一起。
        """
        return self.js(
            "const el=document.getElementById('exam-status');"
            "return el? (el.textContent||'').trim() : null;")


class GradingPage(BasePage):
    """批改台：选考试 → 队列 → 单份作答 → 判客观题 / 改主观分 / 出分。

    三个实测约束：
      1. `#btn-grade`（判客观题）**无确认**；`#btn-ai`、`#btn-finalize` 有原生 `confirm()`；
      2. 每个动作成功后都会 `refresh()` 重载面板 —— 按钮节点会被替换，不能缓存 element；
      3. 队列项点击是 `loadAttempt()`，面板内容全量重渲染。
    """
    path = "/grading/"
    ready = "#exam-select"

    L = {
        "exam_select": "#exam-select",
        "queue": "#queue-list",
        "queue_item": "#queue-list .queue-item",
        "panel": "#attempt-panel",
        "grade_btn": "#btn-grade",
        "ai_btn": "#btn-ai",
        "finalize_btn": "#btn-finalize",
        "cards": "#attempt-panel .grade-card",
        "scoreboard_link": "#btn-scoreboard",
        "only_pending": "#chk-all",
    }

    def wait_queue(self):
        """等队列渲染出条目或明确的空态。

        原实现只等「加载中」消失 —— 但 `loadQueue()` 根本没有加载中间态，
        首屏是「请先选择考试。」，条件会立刻成立；紧接着点队列时节点还没生成，
        而 `click()` 的 JS 兜底会静默点空，表现为「右侧一直停在引导文案」。
        """
        return self.wait_for(
            lambda d: self.count(self.L["queue_item"]) > 0
            or any(x in (self.js_text(self.L["queue"]) or "")
                   for x in ("全部批改完成", "还没有交卷记录",
                             "请先选择考试", "加载失败")),
            message="批改队列既没有条目也没有空态文案")

    def exam_options(self):
        return self.js_texts(self.L["exam_select"] + " option")

    def select_exam(self, exam_id):
        """按 exam_id 选考试（value 就是 id）。"""
        self.wait.until(lambda d: self.count(self.L["exam_select"] + " option") > 1,
                        message="批改台没有可选考试（下拉未填充）")
        self.js("const s=document.querySelector(arguments[0]);"
                "s.value=String(arguments[1]);"
                "s.dispatchEvent(new Event('change'));", self.L["exam_select"], exam_id)
        self.wait_queue()
        return self

    def select_exam_by_index(self, index=1):
        """按 option 下标选考试（L0 冒烟 `UI-GRD-01` 在用）。

        `loadExams()` 只渲染真实考试，**没有占位 option**，所以 index=1 是第二场考试；
        change 会触发 `loadQueue()` 异步重写队列，返回前要等队列出条目/空态。
        """
        self.wait.until(lambda d: self.count(self.L["exam_select"] + " option") > index,
                        message="批改台考试下拉没有第 %d 项" % index)
        self.js("const s=document.querySelector(arguments[0]);"
                "s.selectedIndex=arguments[1];s.dispatchEvent(new Event('change'));",
                self.L["exam_select"], index)
        return self.wait_queue()

    def select_first_exam(self):
        return self.select_exam_by_index(1)

    def queue_count(self):
        return self.count(self.L["queue_item"])

    def queue_text(self):
        return self.js_text(self.L["queue"])

    def queue_is_empty_hint(self):
        body = self.queue_text() or ""
        return any(x in body for x in ("还没有交卷", "全部批改完成", "请先选择考试"))

    def toggle_only_pending(self):
        """勾选/取消「含已批完」。"""
        before = self.js_text(self.L["queue"])
        self.click(self.L["only_pending"])
        self.wait.until(lambda d: self.js_text(self.L["queue"]) != before,
                        message="切换「含已批完」后队列没有刷新")
        return self

    def open_attempt(self, index=0):
        """点队列第 index 项，**等题目卡片真的渲染出来**，失败则重新标记重点。

        `loadQueue()` 会整体重写队列 DOM；页面 init() 里那次 loadQueue 可能晚于
        我们打标记，标记元素被替换后点击就落空。所以：
          1. 判据只认「题目卡片出现」，不认「面板不含加载中」（初始引导文案也满足）；
          2. 点击失败要整段重试（重新打标记 + 重新点），最多 4 次。
        """
        import time
        from selenium.common.exceptions import TimeoutException

        mark = "uiat-q-%d" % index
        last = None
        for _ in range(4):
            self.wait_for(lambda d: self.count(self.L["queue_item"]) > index,
                          message="批改队列里没有第 %d 项" % index)
            self.js("const items=[...document.querySelectorAll('#queue-list .queue-item')];"
                    "const it=items[arguments[0]]; if(!it) return false;"
                    "document.querySelectorAll('[data-uiat-q]')"
                    ".forEach(e=>e.removeAttribute('data-uiat-q'));"
                    "it.setAttribute('data-uiat-q', arguments[1]); return true;", index, mark)
            self.click('[data-uiat-q="%s"]' % mark, timeout=3)
            try:
                self.wait_for(lambda d: self.count(self.L["cards"]) > 0,
                              timeout=6, message="点队列后没有渲染出题目卡片")
                return self
            except TimeoutException as exc:
                last = exc
                time.sleep(0.3)
        raise AssertionError(
            "点了 4 次队列第 %d 项，答题详情仍未渲染；面板：%r"
            % (index, (self.panel_text() or "")[:120])) from last

    def panel_text(self):
        return self.js_text(self.L["panel"])

    def panel_score(self):
        """面板头部的「得分 / 总分」。返回 (score, total) 字符串。"""
        import re
        text = self.panel_text() or ""
        m = re.search(r"([\d.]+)\s*/\s*([\d.]+)", text)
        return (m.group(1), m.group(2)) if m else (None, None)

    def card_count(self):
        return self.count(self.L["cards"])

    def subjective_cards(self):
        """简答/论述题卡片（需要人工给分的）。"""
        return self.js(
            "return [...document.querySelectorAll('#attempt-panel .grade-card')]"
            ".filter(c=>{const t=c.querySelector('.type-chip');"
            "return t && ['简答','论述'].some(x=>t.innerText.includes(x));}).length;")

    def subjective_index(self):
        """第一张主观题（简答/论述）卡片的下标；找不到返回 -1。"""
        return self.js(
            "const cards=[...document.querySelectorAll('#attempt-panel .grade-card')];"
            "return cards.findIndex(c=>{const t=c.querySelector('.type-chip');"
            "return t && ['简答','论述'].some(x=>t.innerText.includes(x));});")

    def card_score(self, index):
        return self.js(
            "const cards=[...document.querySelectorAll('#attempt-panel .grade-card')];"
            "if(!cards[arguments[0]]) return null;"
            "return cards[arguments[0]].querySelector('.js-score').value;", index)

    def set_card_score(self, index, value):
        self.js("const cards=[...document.querySelectorAll('#attempt-panel .grade-card')];"
                "const el=cards[arguments[0]].querySelector('.js-score');"
                "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                index, str(value))
        return self

    def card_full_score(self, index):
        """该卡片题目满分（卡片 `data-full`），用于把改分值夹在合法区间。"""
        return float(self.js(
            "const cards=[...document.querySelectorAll('#attempt-panel .grade-card')];"
            "return cards[arguments[0]] ? cards[arguments[0]].dataset.full : 0;", index) or 0)

    def save_card(self, index):
        """保存单题评分，并等面板**真的重新渲染完成**。

        前端 `refresh()` = `loadQueue()` + `loadAttempt()` 两步异步重写面板。
        toast「已保存」出现时面板可能还是旧内容（分数 2/12），也可能正被清空成
        「加载中…」；只等「加载中消失」会在两种竞态下都读到旧分数 —— 实测
        UI-GRD-05 因此假红（2 → 2，而 API 实际已是 3）。
        这里保存前给面板首个子元素打标记，等标记消失（innerHTML 已被重写）
        + 题目卡片重新出现 + 头部得分重新出现，才算终态。
        """
        self.js("const host=document.getElementById('attempt-panel');"
                "if(host.firstElementChild) host.firstElementChild.setAttribute('data-uiat-old','1');"
                "const cards=[...document.querySelectorAll('#attempt-panel .grade-card')];"
                "cards[arguments[0]].querySelector('.js-save').click();", index)
        self.wait_toast("已保存")
        return self.wait_for(
            lambda d: not self.js(
                "return !!document.querySelector('#attempt-panel [data-uiat-old]');")
            and self.count(self.L["cards"]) > 0
            and self.panel_score()[0] is not None,
            message="保存评分后面板没有完成刷新（读到的可能是旧分数）")

    def grade_objective(self):
        """判客观题（无二次确认）。

        等待条件要求"有得分**且**与之前不同"：只比"不同"的话，面板重载中
        `panel_score()` 返回 None 也算"不同"，会提前通过并读到 None（踩过）。
        """
        before = self.panel_score()
        self.click(self.L["grade_btn"])
        self.wait_toast("客观题已判")
        self.wait.until(
            lambda d: self.panel_score()[0] is not None and self.panel_score() != before,
            message="判客观题后分数没有变化（%s）" % (before,))
        return self

    def finalize(self):
        """出分并公开成绩（有原生 confirm）。"""
        self.click(self.L["finalize_btn"])
        text = self.accept_alert()
        self.wait_toast("已出分")
        return text

    def finalize_btn_disabled(self):
        btn = self.elements(self.L["finalize_btn"])
        if not btn:
            return True
        return btn[0].get_attribute("disabled") is not None


class ScoreboardPage(BasePage):
    """成绩单（`/grading/exams/{id}/scoreboard/`）。

    注意：**没有分页**——一次拉全部行；关键词要**回车**才触发，班级选择是 change。
    """
    path = "/grading/exams/{exam_id}/scoreboard/"
    ready = "#score-body"

    L = {
        "rows": "#score-body tr",
        "keyword": "#f-keyword",
        "classroom": "#f-classroom",
        "reload": "#btn-reload",
        "s_applicants": "#s-applicants",
        "s_submitted": "#s-submitted",
        "s_graded": "#s-graded",
        "s_avg": "#s-avg",
        "s_passrate": "#s-passrate",
        "i_policy": "#i-policy",
        "i_total": "#i-total",
        "i_pass": "#i-pass",
        "i_pending": "#i-pending",
        "distribution": "#distribution",
    }

    def wait_loaded(self):
        self.wait.until(
            lambda d: all((self.js_text(self.L[k]) or "").strip() not in ("", "—")
                          for k in ("s_applicants", "s_submitted", "s_graded")),
            message="成绩单统计卡没有填上数值")
        return self

    def row_count(self):
        return self.js(
            "const rows=[...document.querySelectorAll('#score-body tr')];"
            "if (rows.length === 1 && rows[0].innerText.includes('暂无数据')) return 0;"
            "return rows.length;")

    def stats(self):
        self.wait_loaded()
        return {k: self.js_text(self.L[k]) for k in
                ("s_applicants", "s_submitted", "s_graded", "s_avg", "s_passrate")}

    def summary(self):
        return {k: self.js_text(self.L[k]) for k in ("i_policy", "i_total", "i_pass", "i_pending")}

    def row_students(self):
        return self.js(
            "return [...document.querySelectorAll('#score-body tr')]"
            ".filter(r=>r.querySelector('.js-grade')).map(r=>r.querySelector('td:nth-child(2)').innerText.trim());")

    def row_pass_badges(self):
        return self.js(
            "return [...document.querySelectorAll('#score-body tr')]"
            ".filter(r=>r.querySelector('.js-grade')).map(r=>r.querySelectorAll('td')[6].innerText.trim());")

    def search(self, keyword):
        """关键词搜索：**必须回车**才触发（只有 keydown Enter 监听）。"""
        before = self.row_count()
        self.js("const el=document.querySelector(arguments[0]);"
                "el.value=arguments[1];el.dispatchEvent(new Event('input'));",
                self.L["keyword"], keyword)
        self.js("const el=document.querySelector(arguments[0]);"
                "el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));",
                self.L["keyword"])
        self.wait.until(lambda d: self.row_count() != before
                        or "加载中" not in (self.js_text("#score-body") or ""),
                        message="回车搜索后成绩单未刷新")
        return self

    def filter_classroom(self, value):
        before = self.row_count()
        self.js("const s=document.querySelector(arguments[0]);"
                "s.value=arguments[1];s.dispatchEvent(new Event('change'));",
                self.L["classroom"], value)
        self.wait.until(lambda d: self.row_count() != before
                        or "加载中" not in (self.js_text("#score-body") or ""),
                        message="按班级筛选后成绩单未刷新")
        return self

    def classroom_options(self):
        return self.js(
            "return [...document.querySelectorAll('#f-classroom option')]"
            ".map(o=>[o.value,o.textContent.trim()]);")

    def reload(self):
        before = self.js_text("#score-body")
        self.click(self.L["reload"])
        self.wait.until(lambda d: self.js_text("#score-body") != before
                        or "加载中" not in (self.js_text("#score-body") or ""),
                        message="刷新后成绩单未更新")
        self.wait_loaded()
        return self
