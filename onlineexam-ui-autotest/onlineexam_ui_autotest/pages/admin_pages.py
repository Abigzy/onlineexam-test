# -*- coding: utf-8 -*-
"""管理端页面：数据总览、用户管理、用户表单。

实测约束（2026-11-05，读模板 + 浏览器探测）：

1. 列表与表单都是 **Django 服务端渲染**（不是 fetch + innerHTML）。筛选、新建、
   编辑保存都会**整页导航**，提交后必须等 URL 变化，否则读到旧页面（探测踩过：
   以为「筛选没生效」，其实是没等导航）。
2. 新建 / 编辑保存都跳 ``/manage/users/?search=<username>``；校验失败则停留在
   ``/manage/users/new/``，错误文案在 ``.text-danger`` / ``.alert-danger``。
3. 停用 / 重置密码是 Bootstrap modal + ``static/js/manage.js`` 的异步 POST：
   停用确认后 600ms ``location.reload()``；重置密码把明文写进 ``#pwd-result-text``。
4. **停用弹窗正文是固定文案，不含目标用户名**（用例 UI-ADM-04 原预期含用户名，
   实测不符，已登记 OBS-12）；目标身份靠行按钮的 ``data-username`` 精确定位。
5. 固定 ``user-data-dir`` 下不能同时开两个 Chrome（DevToolsActivePort 冲突），
   跨账号验证用同一 driver「清 cookie → 表单登录 → 重新注入 admin session」。
"""
from common.base_page import BasePage
from common.components import Modal


class ManageDashboardPage(BasePage):
    path = "/manage/"
    ready = ".page-head"

    L = {
        "page_head": ".page-head",
        "stat_cards": ".stat-card",
        "stat_values": ".stat-value",
        "new_user": "a.btn-brand",
        "console_banner": ".alert-warning",
    }

    def open_delegated(self, path="/question-bank/"):
        """管理员代管教师页：顶部会出现黄色提示条。"""
        self.open_raw(path)
        return self.wait_ready(self.L["console_banner"])

    def banner_text(self):
        return self.js_text(self.L["console_banner"])

    def banner_links(self):
        return self.js(
            "return [...document.querySelectorAll('.alert-warning a')]"
            ".map(a=>a.getAttribute('href'));") or []


class ManageUserPage(BasePage):
    path = "/manage/users/"
    ready = "#filter-form"

    L = {
        "filter": "#filter-form",
        "search": "#filter-form input[name=search]",
        "role": "#filter-form select[name=role]",
        "filter_submit": "#filter-form button[type=submit]",
        "rows": "table tbody tr",
        "role_cell": "table tbody tr td:nth-child(3)",
        "toggle_modal": "#toggleModal",
        "toggle_text": "#toggleModalText",
        "toggle_title": "#toggleModalTitle",
        "toggle_confirm": "#toggleConfirm",
        "reset_modal": "#resetModal",
        "reset_target": "#resetModalTarget",
        "reset_confirm": "#resetConfirm",
        "pwd_text": "#pwd-result-text",
        "pwd_copy": "#pwd-copy",
    }

    def row_count(self):
        return self.count(self.L["rows"])

    def role_cells(self):
        return self.js_texts(self.L["role_cell"])

    def first_row_text(self):
        return self.js_text(self.L["rows"])

    def row_text(self, username):
        return self.js(
            "const r=[...document.querySelectorAll('table tbody tr')]"
            ".find(x=>x.innerText.includes(arguments[0]));"
            "return r?r.innerText.trim():'';", username) or ""

    def wait_row_contains(self, username, text, timeout=None):
        return self.wait_for(
            lambda d: text in self.row_text(username), timeout=timeout,
            message="用户 %s 的行里没出现「%s」" % (username, text))

    def filter_role(self, text="学生"):
        self.select_by_text(self.L["role"], text)
        self.click(self.L["filter_submit"])
        return self.wait_url("role=")          # 整页导航，别读旧表

    def filter_value(self):
        return self.attr(self.L["role"], "value")

    def search_user(self, username):
        self.type(self.L["search"], username)
        self.click(self.L["filter_submit"])
        return self.wait_url("search=")

    def row_action(self, username, action):
        """按 data-username 精确定位行内按钮，避免「点错人」。"""
        return self.click('[data-action="%s"][data-username="%s"]' % (action, username))

    def disable_modal(self):
        return Modal(self, self.L["toggle_modal"], confirm=self.L["toggle_confirm"],
                     title=self.L["toggle_text"])

    def reset_modal(self):
        return Modal(self, self.L["reset_modal"], confirm=self.L["reset_confirm"])

    def toggle_text(self):
        return self.js_text(self.L["toggle_text"])

    def toggle_title(self):
        return self.js_text(self.L["toggle_title"])

    def reset_password_for(self, username):
        """点行内「重置密码」→ 确认 → 返回明文新密码。"""
        self.row_action(username, "reset-password")
        self.reset_modal().wait_open()
        self.click(self.L["reset_confirm"])
        self.wait_for(lambda d: bool((self.js_text(self.L["pwd_text"]) or "").strip()),
                      message="重置密码后弹窗没有显示明文新密码")
        return self.js_text(self.L["pwd_text"])

    def copy_password(self):
        return self.click(self.L["pwd_copy"])


class ManageUserFormPage(BasePage):
    path = "/manage/users/new/"
    ready = "#user-form"

    L = {
        "form": "#user-form",
        "username": "input[name=username]",
        "email": "input[name=email]",
        "real_name": "input[name=real_name]",
        "role": "select[name=role]",
        "grade_year": "select[name=grade_year]",
        "password": "input[name=password]",
        "password2": "input[name=password2]",
        "gen_password": "#btn-gen-password",
        "submit": "#user-form button[type=submit]",
        "errors": ".text-danger, .alert-danger",
    }

    def open_edit(self, user_id):
        self.open_raw("/manage/users/%s/edit/" % user_id)
        return self.wait_ready()

    def fill_create(self, username, email, real_name, grade_text=None,
                    role_text="学生", password=None):
        """填新建表单。password=None 时点「生成密码」拿 12 位强密码。"""
        self.open()
        self.type(self.L["username"], username)
        self.type(self.L["email"], email)
        self.type(self.L["real_name"], real_name)
        if role_text:
            self.select_by_text(self.L["role"], role_text)
        if grade_text:
            self.select_by_text(self.L["grade_year"], grade_text)
        if password:
            self.type(self.L["password"], password)
            self.type(self.L["password2"], password)
        else:
            self.click(self.L["gen_password"])
        return self

    def generated_password(self):
        return self.attr(self.L["password"], "value")

    def submit(self):
        return self.click(self.L["submit"])

    def errors(self):
        """过滤掉必填星号与导航里的噪音文本。"""
        return [t for t in self.js_texts(self.L["errors"])
                if t and t.strip() not in ("*",)]

    def set_real_name(self, name):
        self.type(self.L["real_name"], name)
        return self.submit()

    def create_student(self, username, email, real_name, grade_text=None):
        """旧版简化入口（保留兼容）：不填密码会校验失败，正式用例请用 fill_create。"""
        self.open()
        self.type(self.L["username"], username)
        self.type(self.L["email"], email)
        self.type(self.L["real_name"], real_name)
        if grade_text:
            self.select_by_text(self.L["grade_year"], grade_text)
        self.click(self.L["submit"])
        return self
