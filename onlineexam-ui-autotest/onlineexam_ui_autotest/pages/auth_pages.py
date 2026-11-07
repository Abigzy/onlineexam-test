# -*- coding: utf-8 -*-
"""认证与账号相关页面：登录、注册、个人中心。"""
import config
from common.base_page import BasePage


class LoginPage(BasePage):
    path = "/login/"
    ready = "form"

    # 定位器集中区（改动只改这里）
    L = {
        "username": "input[name=username]",
        "password": "input[name=password]",
        "remember": "input[name=remember_me]",
        "submit": "button[type=submit]",
        "error": ".alert-danger",
        "toggle": "#toggle-password",
        "to_register": "a[href='/register/']",
    }

    def login(self, username, password=None, remember=False, next_path=None):
        """登录。`next_path` 用于验证"未登录被拦 → 登录后回跳原页"。

        带 `next` 时不能走 `open()`（它固定去 `/login/`），要自己拼地址，
        否则测的就不是回跳链路了。
        """
        if next_path:
            self.driver.get(config.BASE_URL + "/login/?next=" + next_path)
            self.wait_ready()
        else:
            self.open()
        self.type(self.L["username"], username)
        self.type(self.L["password"], password or config.PASSWORD)
        if remember:
            self.click(self.L["remember"])
        self.click(self.L["submit"])
        # 登录成功会离开 /login/；失败会原地渲染错误
        self.wait.until(lambda d: "/login/" not in d.current_url
                        or self.visible(self.L["error"]),
                        message="登录后既没跳转也没报错")
        return self

    def error_text(self):
        return self.text(self.L["error"]) if self.visible(self.L["error"]) else ""

    def wait_leave_login(self, timeout=None):
        """等离开 /login/（已登录访问登录页会被 302 回首页）。"""
        self.wait_for(lambda d: "/login/" not in d.current_url,
                      timeout=timeout, message="没有离开登录页（当前 %s）" % self.url)
        return self

    def password_input_type(self):
        return self.attr(self.L["password"], "type")


class RegisterPage(BasePage):
    path = "/register/"
    ready = "form"

    L = {
        "username": "input[name=username]",
        "email": "input[name=email]",
        "real_name": "input[name=real_name]",
        "grade_year": "select[name=grade_year]",
        "password": "input[name=password]",
        "password2": "input[name=password2]",
        "submit": "button[type=submit]",
        "errors": ".text-danger",
    }

    def submit_empty(self):
        self.open()
        self.click(self.L["submit"])
        return self

    def submit(self):
        """提交注册表单：要么离开 /register/，要么原地渲染错误。"""
        self.click(self.L["submit"])
        self.wait.until(lambda d: "/register/" not in d.current_url
                        or self.count(self.L["errors"]) > 0,
                        message="注册提交后既没跳转也没报错")
        return self

    def fill(self, username, email, real_name, password, grade_text=None):
        self.open()
        self.type(self.L["username"], username)
        self.type(self.L["email"], email)
        self.type(self.L["real_name"], real_name)
        if grade_text:
            self.select_by_text(self.L["grade_year"], grade_text)
        self.type(self.L["password"], password)
        self.type(self.L["password2"], password)
        return self

    def errors(self):
        return self.texts(self.L["errors"])

    def grade_value(self):
        """入学年级当前选中的值。

        实测：`grade_year` 的 choices 里**没有空选项**（`grade_year_choices()`
        只返回「2026级…2022级」），所以 select 默认就选中第一项，
        「空提交」时年级不会报必填错误——用例断言要按这个事实写。
        """
        return self.attr(self.L["grade_year"], "value")

    def field_errors(self):
        """按字段标签归集的错误文案：`{"用户名": ["该字段是必填项。"], ...}`。

        比 `errors()` 多一层定位信息——Django 的必填文案是通用的
        「该字段是必填项。」，只数条数无法证明**是哪个字段**没校验。
        """
        return self.js("""
            const out={};
            document.querySelectorAll('.mb-3, .col-md-6').forEach(box=>{
              const lb=((box.querySelector('label')||{}).innerText||'');
              const es=[...box.querySelectorAll('.text-danger.small')]
                .map(e=>(e.innerText||'').trim()).filter(Boolean);
              if (es.length) out[lb.replace('*','').trim()]=es;
            });
            return out;""") or {}


class ProfilePage(BasePage):
    """个人中心：资料表单 + 改密表单在**同一页**，且 base.html 的导航里还有
    「退出登录」的 POST 表单——所以 `button[type=submit]` 会先命中退出按钮
    （实测点了保存 = 点了退出，页面直接回登录页）。选择器必须锚定表单自身的
    `input[name=action]`，不能图省事用全局 `button[type=submit]`。
    """
    path = "/profile/"
    ready = "form"

    L = {
        "real_name": "input[name=real_name]",
        "email": "input[name=email]",
        # 学号 / 工号是只读展示（div.form-control，不是 input），见 student_no_text()
        "student_no_box": "div.form-control",
        "dispatch_note": ".form-text",
        "save": 'form:has(input[name="action"][value="profile"]) button[type="submit"]',
        "save_pwd": 'form:has(input[name="action"][value="password"]) button[type="submit"]',
        "success": ".alert-success",
        "error": ".alert-danger",
        "old_password": "input[name=old_password]",
        "new_password": "input[name=new_password]",
        "confirm_password": "input[name=confirm_password]",
    }

    def student_no_text(self):
        """「学号 / 工号」展示区的值（div.form-control 的文本）。"""
        return (self.js(
            "const box=[...document.querySelectorAll('div.form-control')]"
            ".map(e=>(e.innerText||'').trim())"
            ".filter(t=>/^\\d{8}$|^T\\d+$/.test(t));"
            "return box[0]||'';") or "").strip()

    def dispatch_note(self):
        return self.js(
            "const n=[...document.querySelectorAll('.form-text')]"
            ".map(e=>(e.innerText||'').trim())"
            ".filter(t=>t.indexOf('派发')>=0);"
            "return n[0]||'';") or ""

    def update_real_name(self, name):
        self.type(self.L["real_name"], name)
        self.click(self.L["save"])
        return self

    def save_success_text(self):
        return self.text(self.L["success"]) if self.visible(self.L["success"]) else ""
