# -*- coding: utf-8 -*-
"""学生侧页面：首页、我的考试、答题、结果、练习、错题本、班级。"""
import re

import config
from common.base_page import BasePage
from common.components import Modal


class HomePage(BasePage):
    path = "/"
    ready = ".navbar-brand"

    L = {
        "nav_items": "#mainNav .nav-link, #mainNav .dropdown-item",
        "stat_card": ".stat-card",
        "stat_value": ".stat-value",
        "user_dropdown": "#mainNav .nav-item.dropdown > a",
        "logout_btn": "#mainNav form[action='/logout/'] button",
        "greeting": "h1, h2, h3, h4",
    }

    def nav_texts(self):
        return " | ".join(self.texts(self.L["nav_items"]))

    def stat_values(self):
        return self.texts(self.L["stat_value"])

    def logout(self):
        self.click(self.L["user_dropdown"])
        self.click(self.L["logout_btn"])
        self.wait.until(lambda d: "/logout/" not in d.current_url,
                        message="退出登录后仍在 /logout/")
        return self

    def has_nav(self, substring):
        return substring in self.nav_texts()


class MyExamsPage(BasePage):
    path = "/my-exams/"
    ready = "#exam-cards"

    L = {
        "cards": "#exam-cards .card",
        "card_titles": "#exam-cards .card h6",
        "tabs": "#tabs button[data-tab]",
        "refresh": "#btn-refresh",
        "start_btn": "#exam-cards .act-start",
        "result_link": "#exam-cards a[href*='/result/']",
        "badges": "#exam-cards .badge-soft",
    }

    def wait_cards(self):
        self.wait_loading_gone()
        self.wait_count(self.L["cards"], 1)
        return self

    def titles(self):
        self.wait_cards()
        return self.texts(self.L["card_titles"])

    def switch_tab(self, label):
        for btn in self.elements(self.L["tabs"]):
            if btn.text.strip() == label:
                btn.click()
                return self
        raise AssertionError("找不到页签「%s」，当前页签：%s" % (label, self.texts(self.L["tabs"])))

    def active_tab(self):
        for btn in self.elements(self.L["tabs"]):
            if "active" in (btn.get_attribute("class") or ""):
                return btn.text.strip()
        return ""

    def card_button(self, title):
        """返回某张考试卡片上主按钮的（文案, 是否禁用）。"""
        return self.js(
            "const cards=[...document.querySelectorAll('#exam-cards .card')];"
            "const card=cards.find(c=>c.innerText.includes(arguments[0]));"
            "if(!card) return ['', null];"
            "const b=card.querySelector('button.act-start, a.btn, button.btn');"
            "if(!b) return ['', null];"
            "return [(b.innerText||'').trim(), b.disabled===true || b.classList.contains('disabled')];",
            title)

    def card_by_title(self, title):
        for card in self.elements(self.L["cards"]):
            if title in card.text:
                return card
        return None

    def start_exam(self, title=None):
        """点「开始考试」；指定 title 时点该卡片上的按钮。"""
        if title:
            card = self.card_by_title(title)
            assert card is not None, "列表里没有标题含「%s」的考试，现有：%s" % (title, self.titles())
            card.find_element("css selector", ".act-start").click()
        else:
            self.click(self.L["start_btn"])
        self.wait_url("/take/")
        return self


class ExamTakePage(BasePage):
    path = "/exams/{exam_id}/take/"
    ready = "#exam-body"

    L = {
        "questions": "#question-host .question-block",
        "stems": "#question-host .q-stem",
        "options": "#question-host .option-row",
        "picked": "#question-host .option-row.is-picked",
        "sheet_cells": "#q-sheet .q-cell",
        "answered_cells": "#q-sheet .q-cell.is-answered",
        "flagged_cells": "#q-sheet .q-cell.is-flagged",
        "progress": "#progress-text",
        "save_flag": "#save-flag",
        "timer": "#timer",
        "btn_submit": "#btn-submit",
        "btn_confirm": "#btn-confirm-submit",
        "btn_flag": "#btn-flag",
        "btn_next": "#btn-next",
        "btn_prev": "#btn-prev",
        "btn_mode": "#btn-mode",
        "submit_modal": "#submitModal",
        "submit_summary": "#submit-summary",
        "shield": "#shield",
    }

    def wait_questions(self, timeout=None):
        """等题目真正渲染出来（JS 拉取题目后才会有 .question-block）。"""
        self.wait_gone("#loading-box", timeout=timeout)
        self.wait_count(self.L["questions"], 1, timeout=timeout)
        return self

    def question_count(self):
        return self.count(self.L["questions"])

    def progress(self):
        return self.text(self.L["progress"])

    def answered_ratio(self):
        text = self.progress()
        done, total = text.split("/")
        return int(done), int(total)

    def save_flag(self):
        return self.text(self.L["save_flag"])

    def timer(self):
        return self.text(self.L["timer"])

    def answer_first_option(self):
        """点第 1 题的第一个选项，等保存完成。"""
        self.elements(self.L["options"])[0].click()
        self.wait_text(self.L["save_flag"], "已保存")
        return self

    def picked_count(self):
        return self.count(self.L["picked"])

    # ---------------------------------------------------------- 扩展：L1 用
    def stems(self):
        self.wait_questions()
        return self.texts(self.L["stems"])

    def index_of_stem(self, substring):
        """按题干片段找题号（0 基）；找不到返回 -1。"""
        return self.js(
            "const stems=[...document.querySelectorAll('#question-host .q-stem')];"
            "return stems.findIndex(e=>e.innerText.includes(arguments[0]));", substring)

    def goto(self, index):
        self.js("document.querySelector('#q-sheet .q-cell[data-index=\"%d\"]').click();" % index)
        self.wait.until(lambda d: self.current_index() == index,
                        message="点答题卡后没有切到第 %d 题" % index)
        return self

    def current_index(self):
        return self.js(
            "const c=document.querySelector('#q-sheet .q-cell.is-current');"
            "return c?Number(c.dataset.index):-1;")

    def picked_labels(self):
        return self.texts("#question-host .option-row.is-picked .option-label")

    def answer_labels(self, *labels):
        for label in labels:
            self.js("document.querySelector('#question-host .option-row[data-label=\"%s\"]').click();"
                    % label)
        return self

    def fill_answer(self, text):
        area = self.element("#question-host textarea[data-pq]")
        area.clear()
        area.send_keys(text)
        return self

    def flag(self):
        self.click(self.L["btn_flag"])
        return self

    def flagged_count(self):
        return self.count(self.L["flagged_cells"])

    def ensure_no_modal(self):
        """防御：有弹窗挡着就先关掉。

        踩过的坑：某次点击误触「交卷」，弹窗打开后遮罩拦住后续所有点击，
        表现成"上一题点了没反应"——排查半天才发现是遮罩。
        """
        if self.visible("#submitModal") and "show" in (self.attr("#submitModal", "class") or ""):
            self.click_real("#submitModal .modal-footer button.btn-outline-secondary")
            Modal(self, "#submitModal").wait_closed()
        return self

    def _pager_click(self, css, delta):
        """分页按钮用 JS 触发 click。

        为什么不用真实指针：headless 下 Bootstrap 的 modal backdrop 偶尔残留
        （transitionend 不触发），会把这几个按钮的点击吃掉；而分页按钮只挂了
        一个普通 click 监听（无 Bootstrap 委托），JS click 与真人点击对被测逻辑
        完全等价。真实指针留给"必须验交互语义"的地方（弹窗关闭等）。
        """
        self.ensure_no_modal()
        before = self.current_index()
        self.js("document.querySelector(arguments[0]).click();", css)
        if delta:
            self.wait.until(lambda d: self.current_index() == before + delta,
                            message="分页按钮没有按预期切换题目")
        return self

    def go_next(self, expect_move=True):
        return self._pager_click(self.L["btn_next"], 1 if expect_move else 0)

    def go_prev(self, expect_move=True):
        return self._pager_click(self.L["btn_prev"], -1 if expect_move else 0)

    def next_disabled(self):
        el = self.element(self.L["btn_next"], visible=False)
        return (el.get_attribute("disabled") is not None) or \
               ("disabled" in (el.get_attribute("class") or ""))

    def prev_disabled(self):
        el = self.element(self.L["btn_prev"], visible=False)
        return (el.get_attribute("disabled") is not None) or \
               ("disabled" in (el.get_attribute("class") or ""))

    def enter_all_mode(self):
        """切到全卷模式（此时全部题目都渲染在 DOM 里，才能按题干定位题号）。"""
        if not self.pager_hidden():
            self.toggle_all_mode()
            self.wait.until(lambda d: self.pager_hidden(), message="未进入全卷模式")
        return self

    def goto_by_stem(self, substring):
        """按题干片段跳到某题，返回题号（0 基）。

        单题模式只渲染当前 1 题，直接找 .q-stem 会找不到；先切全卷拿全量 DOM，
        再点答题卡格子（全卷模式下点格子会自动切回单题模式）。
        """
        self.enter_all_mode()
        idx = self.js(
            "const blocks=[...document.querySelectorAll('#question-host .question-block')];"
            "return blocks.findIndex(b=>b.innerText.includes(arguments[0]));", substring)
        if idx < 0:
            raise AssertionError("全卷模式里也找不到含「%s」的题目" % substring)
        # 必须用「模式按钮」切回单题：它一定会 renderQuestion()；
        # 而点答题卡格子时，若点的正是当前题，gotoQuestion 会提前 return，
        # 页面既没切回单题也没重渲染（产品小瑕疵，见 OBS-06）。
        self.toggle_all_mode()
        self.wait.until(lambda d: not self.pager_hidden(), message="没切回单题模式")
        self.goto(idx)
        self.wait.until(lambda d: self.current_index() == idx, message="跳题失败：%s" % idx)
        return idx

    def toggle_all_mode(self):
        self.click(self.L["btn_mode"])
        return self

    def pager_hidden(self):
        return "d-none" in (self.attr("#pager", "class") or "")

    def timer_seconds(self):
        text = self.timer().strip()
        parts = [int(p) for p in re.findall(r"\d+", text)]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return -1

    def confirm_submit(self):
        self.click(self.L["btn_confirm"])
        self.wait_url("/result/")
        return self

    def open_submit_modal(self):
        self.click(self.L["btn_submit"])
        modal = Modal(self, self.L["submit_modal"], confirm=self.L["btn_confirm"])
        modal.wait_open()
        return modal

    def submit_summary(self):
        return self.text(self.L["submit_summary"])

    def close_submit_modal(self):
        # 「继续检查」是弹窗里的次要按钮（无 id），用真实点击，别用 JS click
        # （Bootstrap 的 data-bs-dismiss 依赖真实事件冒泡，JS click 在这里不生效）
        self.click_real("#submitModal .modal-footer button.btn-outline-secondary")
        Modal(self, self.L["submit_modal"]).wait_closed()
        return self


class ExamResultPage(BasePage):
    path = "/exams/{exam_id}/result/"
    ready = "#result-host"

    L = {
        "cards": "#result-host .card",
        "badges": "#result-host .badge-soft",
        "body_text": "#result-host",
    }

    def wait_loaded(self):
        """结果页内容也是 fetch 注入的：先等「加载中」消失，再断言文案。"""
        self.wait_loading_gone()
        return self

    def text_all(self):
        self.wait_loaded()
        return self.text(self.L["body_text"])

    def badge_counts(self):
        self.wait_loaded()
        """逐题徽章按文案计数：{'正确': n, '错误': n, '未作答': n, '已判分': n}"""
        return self.js(
            "const out={};"
            "document.querySelectorAll('#result-host .badge-soft').forEach(b=>{"
            "  const k=(b.innerText||'').trim(); out[k]=(out[k]||0)+1;});"
            "return out;")

    def has_score_text(self):
        """页面是否出现"数字分"（未公开成绩时不应出现）。"""
        return self.js(
            "const t=document.querySelector('#result-host').innerText;"
            "return /\\d+(\\.\\d+)?\\s*分/.test(t);")


class PracticePage(BasePage):
    """每日练习页（`/practice/`）。

    三个实测口径（2026-11-05）：
      1. 题型是**混合**的：入门练习一次给 6 题，可能全是主观题（`short` / `essay` /
         `fill`），没有 `.option-row`。凡是要「点选项」的用例，必须先用
         `first_objective_index()` 挑出**带选项的卡**，不能默认第一张就是选择题。
      2. 提交后 `[data-submit]` **整块消失**（结果区自带「查看答案与解析 / 再做一次」），
         不是 disabled——断言不能写「按钮变灰」。
      3. 结论文案是「答对了 / 答错了」，不是用例原文的「回答正确 / 回答错误」。
    """
    path = "/practice/"
    ready = "#practice-host"

    L = {
        "cards": ".practice-card",
        "submits": ".practice-card [data-submit]",
        "options": ".practice-card .option-row",
        "subject_select": "#subject-select",
        "shuffle": "#btn-shuffle",
        "empty_select": "#empty-subject-select",
        "ai_reason": "#btn-ai-reason",
        "ai_banner": "#ai-banner-host",
        "more": "#btn-more",
        "host": "#practice-host",
    }

    def wait_cards(self, timeout=None):
        self.wait_loading_gone()
        return self

    def wait_settled(self, timeout=None):
        """等到「有卡片」或「明确空态」，两者都不出现就是页面卡死。"""
        self.wait_for(
            lambda d: self.count(self.L["cards"]) > 0
            or any(k in (self.js_text(self.L["host"]) or "")
                   for k in ("没有可推荐", "还没有加入任何学科班", "暂时没有", "不在你加入的学科")),
            timeout=timeout, message="练习页既没有题卡也没有空态（仍停在加载中？）")
        return self

    def card_count(self):
        return self.count(self.L["cards"])

    def qids(self):
        return self.js(
            "return [...document.querySelectorAll('.practice-card')]"
            ".map(c=>String(c.dataset.qid));") or []

    def first_objective_index(self):
        """第一张**有选项**的卡的下标；全是主观题时返回 -1。"""
        return self.js("""
            const cards=[...document.querySelectorAll('.practice-card')];
            const i=cards.findIndex(c=>c.querySelector('.option-row'));
            return i;""")

    def _card_js(self, index, expr):
        return "const card=[...document.querySelectorAll('.practice-card')][%d];%s" % (index, expr)

    def pick_option(self, index, option_index=0):
        self.js(self._card_js(index, "card.querySelectorAll('.option-row')[%d].click();"
                              % option_index))
        self.wait_for(lambda d: self.js(self._card_js(
            index, "return card.querySelectorAll('.option-row.is-picked').length;")) == 1,
            message="点选项后没有出现选中态")
        return self

    def submit(self, index):
        self.js(self._card_js(index, "card.querySelector('[data-submit]').click();"))
        self.wait_for(lambda d: (self.js(self._card_js(
            index, "return (card.querySelector('[data-result]')||{}).innerText||'';")) or "")
            .strip() != "", message="提交后没有出现判分结论")
        return self

    def result_text(self, index):
        return (self.js(self._card_js(
            index, "return (card.querySelector('[data-result]')||{}).innerText||'';")) or "").strip()

    def submit_count(self, index):
        return self.js(self._card_js(
            index, "return card.querySelectorAll('[data-submit]').length;"))

    def toggle_answer(self, index):
        self.js(self._card_js(index, "card.querySelector('[data-toggle-answer]').click();"))
        return self

    def answer_visible(self, index):
        return self.js(self._card_js(
            index,
            "const a=card.querySelector('[data-answer]');"
            "return !!a && getComputedStyle(a).display!=='none';"))

    def answer_text(self, index):
        return (self.js(self._card_js(
            index,
            "const a=card.querySelector('[data-answer]');"
            "return a?(a.innerText||''):'';")) or "").strip()

    def toggle_label(self, index):
        return (self.js(self._card_js(
            index,
            "const b=card.querySelector('[data-toggle-answer]');"
            "return b?b.innerText.trim():'';")) or "").strip()

    def redo(self, index):
        self.js(self._card_js(index, "card.querySelector('[data-redo]').click();"))
        self.wait_for(lambda d: self.result_text(index) == "" and self.submit_count(index) == 1,
                      message="「再做一次」没有恢复成未作答状态")
        return self

    def picked_count(self, index):
        return self.js(self._card_js(
            index, "return card.querySelectorAll('.option-row.is-picked').length;"))

    def shuffle(self):
        before = self.qids()
        self.click(self.L["shuffle"])
        self.wait_for(lambda d: self.qids() != before and self.card_count() > 0,
                      message="「换一批」后题卡没有变化")
        return before, self.qids()

    def ai_reason(self):
        """点「AI 优化推荐理由」。

        实测会先弹 `window.confirm`（提示可能产生费用），不拦截的话 driver 直接抛
        `UnexpectedAlertPresentException`——这里用 JS 覆盖 confirm 再点，
        和「下载/新窗口」拦截同一套做法。
        """
        self.js("window.confirm = function () { return true; };")
        self.click(self.L["ai_reason"])
        self.wait_for(lambda d: (self.js_text(self.L["ai_banner"]) or "").strip() != "",
                      timeout=config.WAIT_TIMEOUT, message="AI 理由没有渲染出内容")
        return (self.js_text(self.L["ai_banner"]) or "").strip()

    def ai_button_state(self):
        return self.js("""
            const b=document.getElementById('btn-ai-reason');
            return b ? {text: b.innerText.trim(), disabled: !!b.disabled} : {};""") or {}

    def host_text(self):
        return self.js_text(self.L["host"]) or ""

    def shuffle_disabled(self):
        return self.js("return !!document.getElementById('btn-shuffle').disabled;")

    def subject_options(self):
        return self.js("return [...document.querySelectorAll('#subject-select option')]"
                       ".map(o=>o.value);") or []


class WrongBookPage(BasePage):
    """错题本（`/my-wrong-book/`）。

    实测（2026-11-05）：
      - 200 条错题首次渲染要 **3.5s 左右**，等 `#summary` 不再是「加载中…」才算加载完；
      - **没有「展开/收起」入口**（卡片里没有任何 button），参考答案与解析在
        `.ref-box` 里默认展开，`我的作答` 在 `.mine-box`——用例按这个事实写，
        不要照着「点展开」的原文去点。
      - 学科下拉只列**有错题**的学科：选中后 `#summary` 与卡片数同步变化。
    """
    path = "/my-wrong-book/"
    ready = "#wrong-list"

    L = {
        "subject": "#f-subject",
        "summary": "#summary",
        "list": "#wrong-list",
        "cards": ".wrong-card",
        "ref": ".wrong-card .ref-box",
        "mine": ".wrong-card .mine-box",
    }

    def wait_loaded(self, timeout=None):
        self.wait_for(lambda d: "加载中" not in (self.js_text(self.L["summary"]) or ""),
                      timeout=timeout or config.WAIT_TIMEOUT, message="错题本统计一直停在加载中")
        return self

    def summary_text(self):
        return (self.js_text(self.L["summary"]) or "").strip()

    def card_count(self):
        return self.count(self.L["cards"])

    def summary_number(self):
        nums = re.findall(r"\d+", self.summary_text())
        return int(nums[0]) if nums else 0

    def subject_options(self):
        return self.js("return [...document.querySelectorAll('#f-subject option')]"
                       ".map(o=>o.value);") or []

    def filter_subject(self, value):
        before = self.summary_text()
        self.js("const s=document.getElementById('f-subject');"
                "s.value=arguments[0];s.dispatchEvent(new Event('change'));", value)
        self.wait_for(lambda d: self.summary_text() != before and "加载中" not in self.summary_text(),
                      message="切换学科后统计没有刷新")
        return self

    def ref_text(self, index=0):
        return (self.js_texts(self.L["ref"])[index] if index < len(self.js_texts(self.L["ref"]))
                else "").strip()

    def mine_text(self, index=0):
        boxes = self.js_texts(self.L["mine"])
        return (boxes[index] if index < len(boxes) else "").strip()

    def has_toggle(self):
        return self.js("return document.querySelectorAll('.wrong-card button').length;") > 0


class MyAnalyticsPage(BasePage):
    """学生「我的学情」（`/analytics/me/`）。

    图表是 ECharts 画在 `.chart-box` 里的 canvas，`canvas` 数量是最稳的「图真的画出来了」证据；
    `#report-host` 文本里出现「加载中」说明还没渲完。
    """
    path = "/analytics/me/"
    ready = "#report-host"

    L = {
        "host": "#report-host",
        "kpi_labels": ".kpi-label",
        "section_titles": ".chart-head h6",
        "chart_boxes": ".chart-box",
        "canvas": "canvas",
        "weak_card": ".chart-card",
    }

    def wait_loaded(self, timeout=None):
        self.wait_for(lambda d: "加载中" not in (self.js_text(self.L["host"]) or "")
                      and (self.count(self.L["canvas"]) > 0
                           or "还没有已判分的答题记录" in (self.js_text(self.L["host"]) or "")),
                      timeout=timeout or config.WAIT_TIMEOUT,
                      message="学情页没渲染完（仍停在加载中或没有图表）")
        return self

    def canvas_count(self):
        return self.count(self.L["canvas"])

    def kpi_labels(self):
        return [t.strip() for t in (self.js_texts(self.L["kpi_labels"]) or []) if t.strip()]

    def section_titles(self):
        return [t.strip() for t in (self.js_texts(self.L["section_titles"]) or []) if t.strip()]

    def section_text(self, keyword):
        """含 `keyword` 的那张卡片整段文本（薄弱知识点、学情诊断都用它）。"""
        return self.js("""
            const card=[...document.querySelectorAll('.chart-card')]
              .find(c=>(c.innerText||'').indexOf(arguments[0])>=0);
            return card?(card.innerText||''):'';""", keyword) or ""

    def host_text(self):
        return self.js_text(self.L["host"]) or ""

    def scroll_metrics(self):
        return self.js("""
            return {scrollW: document.documentElement.scrollWidth,
                    clientW: document.documentElement.clientWidth};""") or {}

    def chart_boxes_visible(self):
        return self.js("""
            return [...document.querySelectorAll('.chart-box')]
              .filter(e=>{const r=e.getBoundingClientRect();
                          return r.width>100 && r.height>100;}).length;""")


class ClassroomPage(BasePage):
    """班级列表（`/classrooms/`）。学生只看自己加入的班，没有「新建班级」按钮。

    实测（2026-11-05）：新建弹窗里 **年级是 `input` 不是 `select`**（所以没有可读的
    年级选项），类型用 `#ct-admin` / `#ct-subject` 两个 radio 切换；名称为空时
    不写内联错误，而是弹 toast「请填写班级名称」，弹窗保持打开。
    """
    path = "/classrooms/"
    ready = "#class-list"

    L = {
        "cards": "#class-list .class-card",
        "create": "#btn-create",
        "modal": "#classModal",
        "name": "#f-name",
        "grade": "#f-grade",
        "desc": "#f-desc",
        "type_admin": "#ct-admin",
        "type_subject": "#ct-subject",
        "save": "#btn-save",
        "member_list": "#member-list",
        "member_count": "#member-count",
        "perm_modal": "#permModal",
        "add_btn": "#btn-add",
        "c_name": "#c-name",
        "delete_class": "#btn-delete-class",
    }

    def card_count(self):
        self.wait_loading_gone()
        return self.count(self.L["cards"])

    def card_names(self):
        return self.js("""
            return [...document.querySelectorAll('#class-list .class-card')]
              .map(c=>(c.innerText||'').split('\\n')[0].trim());""") or []

    def open_by_id(self, classroom_id):
        """打开班级详情，并等**详情接口回来**再断言。

        `#c-name` 的模板初值就是「加载中…」，`wait_ready` 只保证元素存在，
        直接读名字会读到占位文案（首轮 4 条红里有 2 条就是这个）。
        越权时名字会被改写成「权限不足」，两种终态都算加载完成。
        """
        self.driver.get(config.BASE_URL + "/classrooms/%s/" % classroom_id)
        self.wait_ready("#c-name")
        self.wait_for(lambda d: (self.js_text("#c-name") or "").strip() not in ("", "加载中…"),
                      message="班级详情一直停在加载中")
        return ClassroomDetailPage(self.driver)

    def create(self, name, grade="2026", admin_type=True):
        """新建班级。成功信号是 toast「班级已创建」，**不是**弹窗关闭：
        Bootstrap 的 fade 退场有延迟，只看弹窗会读到中间态。"""
        self.click(self.L["create"])
        Modal(self, self.L["modal"]).wait_open()
        self.type(self.L["name"], name)
        if grade:
            self.type(self.L["grade"], grade)
        self.click(self.L["type_admin"] if admin_type else self.L["type_subject"])
        self.click(self.L["save"])
        self.wait_toast("班级已创建")
        Modal(self, self.L["modal"]).wait_closed()
        self.wait_for(lambda d: name in self.card_names(), message="新建后列表里没有「%s」" % name)
        return self

    def submit_empty_name(self):
        self.click(self.L["create"])
        Modal(self, self.L["modal"]).wait_open()
        before = self.card_count()
        self.click(self.L["save"])
        self.wait_toast("请填写班级名称")
        return before


class ClassroomDetailPage(BasePage):
    """班级详情（`/classrooms/{id}/`）。

    越权时不是 404，而是**弹 `#permModal`**：标题 `#c-name` 被改写成「权限不足」，
    正文说明「你不是这个班级的任课教师或班主任」，底部按钮是「返回班级列表」
    （不是「知道了」，用例原文需按此修订），点它回 `/classrooms/`。
    """
    path = "/classrooms/"
    ready = "#c-name"

    L = {
        "name": "#c-name",
        "member_count": "#member-count",
        "member_list": "#member-list",
        "perm_modal": "#permModal",
        "add_btn": "#btn-add",
        "add_modal": "#addModal",
        "add_nos": "#a-nos",
        "add_save": "#btn-save-add",
        "delete_class": "#btn-delete-class",
    }

    def name_text(self):
        return (self.js_text(self.L["name"]) or "").strip()

    def member_count(self):
        raw = (self.js_text(self.L["member_count"]) or "").strip()
        nums = re.findall(r"\d+", raw)
        return int(nums[0]) if nums else 0

    def member_rows(self):
        """数据行数（`#member-list tr` 含表头，减 1）。"""
        return max(0, self.count(self.L["member_list"] + " tr") - 1)

    def member_texts(self):
        return self.js_texts(self.L["member_list"] + " tr") or []

    def wait_members(self, timeout=None):
        """等成员区就绪，返回 `(count, rows)`。

        详情页的班级信息与成员列表是**两个接口**：`#c-name` 就绪只代表
        `/classrooms/{id}/` 回来了，`#member-count` 与 `#member-list` 由
        `/classrooms/{id}/students/` 单独填充。名字一出来就读成员区，会拿到
        「共 0 人 + 空表」的中间态——UI-CLS-02 在 2026-11-06 全量里就这样挂过
        一次（接口返回 24 人，页面读到 0 人，报"成员数为 0（前置不成立）"）。
        按「计数 ↔ 名单」双视图一致的判据等（README 纪律 10）：两个都 > 0 且
        相等才算就绪。超时不返回 0 掩盖问题——wait_for 会抛出带 message 的
        AssertionError，测试报告里能直接看出是等不到还是真为 0。
        """
        def ready(_d):
            count, rows = self.member_count(), self.member_rows()
            return count > 0 and count == rows
        self.wait_for(ready, timeout=timeout,
                      message="班级成员区未就绪（人数与名单行数不等）")
        return self.member_count(), self.member_rows()

    def perm_modal_visible(self):
        return self.js("""
            const m=document.getElementById('permModal');
            return !!m && getComputedStyle(m).display!=='none'
                   && m.className.indexOf('show')>=0;""")

    def perm_modal_text(self):
        return (self.js_text(self.L["perm_modal"]) or "").strip()

    def leave_by_perm_button(self):
        """点权限弹窗底部的「返回班级列表」。"""
        self.js("""
            const b=[...document.querySelectorAll('#permModal button, #permModal a')]
              .find(x=>(x.innerText||'').indexOf('返回班级列表')>=0);
            if (b) b.click();""")
        self.wait_url("/classrooms/")
        return ClassroomPage(self.driver)

    def add_student_by_no(self, student_no):
        before = self.member_count()
        self.click(self.L["add_btn"])
        Modal(self, self.L["add_modal"]).wait_open()
        self.type(self.L["add_nos"], student_no)
        self.click(self.L["add_save"])
        self.wait_toast("已加入")
        Modal(self, self.L["add_modal"]).wait_closed()
        self.wait_for(lambda d: self.member_count() == before + 1,
                      message="加学生后人数没有 +1（%d → %d）" % (before, self.member_count()))
        return self

    def delete_class(self, confirm=True):
        """删除班级：前端用原生 `window.confirm` 二次确认，必须先拦截再点。

        注意**不能**用 `wait_url("/classrooms/")`：详情页 URL 是
        `/classrooms/173/`，子串天然命中，会立刻通过。要等的是「回到列表页」
        这个精确形态（末尾没有 id），而且产品是 600ms 后才跳。
        """
        self.js("window.confirm = function () { return %s; };"
                % ("true" if confirm else "false"))
        self.click(self.L["delete_class"])
        if confirm:
            self.wait_for(lambda d: re.fullmatch(r".*/classrooms/?", d.current_url) is not None,
                          message="删除后没有跳回班级列表（当前 %s）" % self.url)
        return ClassroomPage(self.driver)
