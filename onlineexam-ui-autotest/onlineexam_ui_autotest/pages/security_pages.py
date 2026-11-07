# -*- coding: utf-8 -*-
"""权限与可见性：通用越权访问检查页（不绑定某个业务页）。

实测口径（2026-11-05，用 `allow_redirects=False` 逐角色探测）：

- **403**：teacher → `/my-exams/`；student → `/question-bank/`、`/exams/{id}/monitor/`。
  浏览器里是 Django 默认 403 页，业务容器都不渲染。
- **302 → `/`**：student / teacher → `/manage/`、`/manage/users/`
  （`AdminConsoleMixin` 重定向回首页，**不是 403**）。用例断言要按这个区分，不能混。
- 导航下拉项是 `display:none`，WebDriver 的 `.text` 读不到；做「不含某入口」
  断言必须用 `textContent`，否则隐藏项会假绿。
"""
from common.base_page import BasePage


class AccessGuardPage(BasePage):
    path = "/"
    ready = "body"

    L = {
        "nav": "#mainNav",
        "exam_cards": "#exam-cards",
        "attempt_body": "#attempt-body",
        "user_filter": "#filter-form",
        "question_rows": "#question-rows",
    }

    def open_protected(self, path):
        """直接访问受保护路径（浏览器会自动跟随 302）。"""
        self.open_raw(path)
        return self

    def nav_text_content(self):
        """读全部导航文本（含折叠下拉项）。"""
        return self.js(
            "return (document.querySelector('#mainNav')||{}).textContent||'';") or ""

    def has(self, css):
        return self.count(css) > 0

    def wait_leave(self, fragment):
        return self.wait_for(
            lambda d: fragment not in d.current_url,
            message="访问受保护页后没有离开 %s（当前 %s）" % (fragment, self.url))
