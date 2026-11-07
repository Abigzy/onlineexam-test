# -*- coding: utf-8 -*-
"""可复用组件：Modal / Toast / Pager。

Modal 的处理是本项目最容易假绿的地方——Bootstrap 的 Modal **常驻 DOM**，
`find_elements` 永远能拿到元素，所以只能断言可见性（docs/04 §3.3）。
"""
import config


class Modal:
    def __init__(self, page, root, confirm="", close="", title=""):
        self.page = page
        self.root = root
        self.btn_confirm = confirm
        self.btn_close = close
        self.title_sel = title

    def is_open(self, timeout=None):
        """等弹窗真正显示出来（Bootstrap 会加 .show 并把 display 置 block）。"""
        from selenium.webdriver.support.ui import WebDriverWait
        wait = WebDriverWait(self.page.driver, timeout or config.WAIT_TIMEOUT, config.POLL_FREQUENCY)
        try:
            wait.until(
                lambda d: d.execute_script(
                    "const el=document.querySelector(arguments[0]);"
                    "if(!el) return false;"
                    "const s=getComputedStyle(el);"
                    "return s.display!=='none' && s.visibility!=='hidden' && el.classList.contains('show');",
                    self.root),
                message="弹窗 %s 未打开" % self.root)
            return True
        except Exception:                                    # noqa: BLE001
            return False

    def wait_open(self):
        """等弹窗打开**且过渡动画结束**。

        只等 `.show` 不够：fade 动画期间遮罩还在半透明，按坐标点按钮会先命中遮罩，
        点击被吃掉（不报错、弹窗不关）——"点「继续检查」关不掉"就是这么来的。
        """
        assert self.is_open(), "弹窗 %s 未打开（当前 URL %s）" % (self.root, self.page.url)
        self.page.wait.until(
            lambda d: d.execute_script(
                "const el=document.querySelector(arguments[0]);"
                "if(!el) return false;"
                "return parseFloat(getComputedStyle(el).opacity) >= 0.99;", self.root),
            message="弹窗 %s 过渡动画未结束" % self.root)
        return self

    def wait_closed(self):
        assert not self.is_open(timeout=config.SHORT_TIMEOUT), "弹窗 %s 未关闭" % self.root
        return self

    def text(self):
        return self.page.body_text() if not self.page.visible(self.root) else \
            self.page.text(self.root)

    def title_text(self):
        return self.page.text(self.title_sel) if self.title_sel else ""

    def confirm(self):
        assert self.btn_confirm, "该弹窗未配置确认按钮"
        self.page.click(self.btn_confirm)
        return self

    def close(self):
        assert self.btn_close, "该弹窗未配置关闭按钮"
        self.page.click_real(self.btn_close)      # 必须真实指针，否则 data-bs-dismiss 不生效
        return self


class Toast:
    """成功/失败提示：站点统一容器 #toast-container。"""

    ROOT = "#toast-container"

    def __init__(self, page):
        self.page = page

    def wait_any(self, timeout=config.SHORT_TIMEOUT):
        self.page.wait.until(
            lambda d: d.execute_script(
                "const el=document.querySelector('%s');"
                "return !!el && el.innerText.trim().length>0;" % self.ROOT),
            message="等不到 toast 提示")
        return self

    def text(self):
        return self.page.js(
            "const el=document.querySelector('%s');return el?el.innerText.trim():'';" % self.ROOT)

    def wait_contains(self, substring, timeout=config.SHORT_TIMEOUT):
        self.page.wait.until(
            lambda d: substring in d.execute_script(
                "const el=document.querySelector('%s');return el?el.innerText:'';" % self.ROOT),
            message="提示中未出现「%s」" % substring)
        return self


class Pager:
    """分页：两种形态都存在——题库/试卷是 #pager + #page-info，考试列表是 #page-info + 上一页/下一页。"""

    def __init__(self, page, info, prev="", next_="", root=""):
        self.page = page
        self.info = info
        self.prev = prev
        self.next = next_
        self.root = root

    def info_text(self, timeout=None):
        return self.page.text(self.info, timeout=timeout)

    def is_disabled(self, which):
        css = self.prev if which == "prev" else self.next
        el = self.page.element(css, visible=False)
        return (el.get_attribute("disabled") is not None) or \
               ("disabled" in (el.get_attribute("class") or ""))

    def next_page(self):
        self.page.click(self.next)
        return self

    def prev_page(self):
        self.page.click(self.prev)
        return self
