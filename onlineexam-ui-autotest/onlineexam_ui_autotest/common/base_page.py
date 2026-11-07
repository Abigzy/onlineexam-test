# -*- coding: utf-8 -*-
"""BasePage：把"等业务节点、点、读、断言"四件事封成一套，用例里不再出现 sleep。

三条纪律（对应 docs/04 §3.2/§3.3）：
    1. 进页面等 ready 选择器，不等 readyState；
    2. 内容依赖 fetch 的地方等"加载态消失"或"目标文本出现"；
    3. 判定可见性用 is_displayed()，不用 find_elements 非空（Modal 常驻 DOM）。
"""
import glob
import os
import time

from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config

LOADING_TEXTS = ("加载中", "载入中")


class BasePage:
    path = "/"                    # 路由模板，可含 {id} 占位
    ready = "body"                # 进入页面后等待的业务节点

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, config.WAIT_TIMEOUT, config.POLL_FREQUENCY)

    # ------------------------------------------------------------ 导航
    def open(self, **kwargs):
        url = config.BASE_URL + self.path.format(**kwargs)
        self.driver.get(url)
        self.wait_ready()
        return self

    def open_raw(self, path):
        """访问非本 PO 的路径（越权用例、错误态用例用）。"""
        self.driver.get(config.BASE_URL + path)

    def wait_ready(self, selector=None):
        sel = selector or self.ready
        self.wait.until(
            lambda d: d.execute_script(
                "return document.querySelectorAll(arguments[0]).length>0", sel),
            message="等不到业务节点 %s（%s）" % (sel, self.driver.current_url))
        return self

    # ------------------------------------------------------------ 元素
    def elements(self, css):
        return self.driver.find_elements(By.CSS_SELECTOR, css)

    def count(self, css):
        return len(self.elements(css))

    def texts(self, css):
        return [e.text.strip() for e in self.elements(css)]

    # ------------------------------------------------------------ 抗 Stale 读取
    # 列表页都是 fetch 后 innerHTML 重写：读的过程中 DOM 被替换就会 stale。
    # 逐元素 .text 尤其容易撞上，所以统一用「一次 JS 读完」的版本。
    def js_text(self, css):
        return (self.js("const e=document.querySelector(arguments[0]);"
                        "return e?(e.innerText||'').trim():'';", css) or "")

    def js_texts(self, css):
        return self.js("return [...document.querySelectorAll(arguments[0])]"
                       ".map(e=>(e.innerText||'').trim());", css) or []

    def element(self, css, visible=True, timeout=None):
        """等元素出现（且默认要求可见），返回元素。"""
        t = timeout or config.WAIT_TIMEOUT
        if visible:
            return WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, css)),
                message="等不到可见元素 %s" % css)
        return WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css)),
            message="等不到元素 %s" % css)

    def text(self, css, timeout=None):
        """读元素文本，撞上 DOM 刷新（stale）时重取一次。

        列表页的内容是 fetch 注入并整体重写 tbody 的，element 拿到了、
        取 text 的瞬间节点被替换 → StaleElementReference。这不是 flaky，
        是"读取时机与刷新竞态"，重试即可，重试后仍失败才是真问题。
        """
        sel = self.element(css, timeout=timeout)
        try:
            return sel.text.strip()
        except StaleElementReferenceException:
            return self.element(css, timeout=timeout).text.strip()

    def value(self, css):
        return self.element(css).get_attribute("value") or ""

    def attr(self, css, name):
        return self.element(css, visible=False).get_attribute(name)

    def click(self, css, timeout=None, real=False):
        """点击：整段"查找 → 点击"可重试。

        三次踩坑换来的策略：
          1. 原生 `element.click()` 自带**遮挡检测**——被遮罩挡住会抛
             ElementClickIntercepted，能第一时间暴露"有弹窗没关"，而不是静默点空；
          2. Bootstrap 的 `data-bs-dismiss` 委托只认真实指针序列，
             关弹窗必须用 ActionChains（`real=True`）；
          3. 列表页 tbody/pager 会被整体重写，**找元素与点击之间**节点就可能失效
             （StaleElementReference）——所以重试粒度必须是"重新查找 + 再点"，
             而不是换个点击方式重试同一个已失效的节点。
        """
        t = timeout or config.WAIT_TIMEOUT
        last = None
        for attempt in range(3):
            try:
                el = WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, css)),
                    message="元素不可点击：%s" % css)
                if real:
                    ActionChains(self.driver).move_to_element(el).pause(0.05).click().perform()
                else:
                    el.click()
                return self
            except StaleElementReferenceException as exc:
                last = exc
                time.sleep(0.2)                              # 等这一轮重渲染结束再重查
            except WebDriverException as exc:
                last = exc
                break
        if last is not None and real:
            raise last
        # 兜底：JS click（重新查 DOM，节点已换也不影响）
        self.js("const e=document.querySelector(arguments[0]);"
                "if(e) e.click();", css)
        return self

    def click_real(self, css, timeout=None):
        """真实鼠标点击（ActionChains）：用于 Bootstrap 委托（弹窗关闭等）。"""
        return self.click(css, timeout=timeout, real=True)

    def type(self, css, value, clear=True):
        el = self.element(css)
        if clear:
            el.clear()
        el.send_keys(value)
        return self

    def select_by_text(self, css, text):
        from selenium.webdriver.support.ui import Select
        Select(self.element(css)).select_by_visible_text(text)
        return self

    def select_by_value(self, css, value):
        from selenium.webdriver.support.ui import Select
        Select(self.element(css)).select_by_value(value)
        return self

    def visible(self, css):
        els = self.elements(css)
        return bool(els) and els[0].is_displayed()

    def js(self, script, *args):
        return self.driver.execute_script(script, *args)

    # ------------------------------------------------------------ 等待
    def wait_for(self, condition, timeout=None, message="条件未满足"):
        """自定义等待（`WebDriverWait.until` 不收 timeout 参数，这里包一层）。"""
        WebDriverWait(self.driver, timeout or config.WAIT_TIMEOUT,
                      config.POLL_FREQUENCY).until(condition, message=message)
        return self

    def wait_text(self, css, substring, timeout=None):
        t = timeout or config.WAIT_TIMEOUT
        try:
            WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
                lambda d: substring in (d.find_element(By.CSS_SELECTOR, css).text or ""),
                message="%s 未在 %ss 内出现文本「%s」" % (css, t, substring))
        except TimeoutException:
            actual = self.elements(css)
            raise AssertionError("等不到「%s」，实际文本：%r" % (
                substring, actual[0].text if actual else "<元素不存在>"))
        return self

    def wait_gone(self, css, timeout=None):
        t = timeout or config.WAIT_TIMEOUT
        WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
            lambda d: all(not e.is_displayed() for e in d.find_elements(By.CSS_SELECTOR, css)),
            message="%s 仍然可见" % css)
        return self

    def wait_count(self, css, n, timeout=None):
        t = timeout or config.WAIT_TIMEOUT
        WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, css)) >= n,
            message="%s 数量未达到 %d（当前 %d）" % (css, n, self.count(css)))
        return self

    def wait_loading_gone(self, timeout=None):
        """等页面不再出现「加载中」文案——fetch 注入内容完成的最低判据。"""
        t = timeout or config.WAIT_TIMEOUT
        WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
            lambda d: not any(x in (d.find_element(By.TAG_NAME, "body").text or "")
                              for x in LOADING_TEXTS),
            message="页面一直停在「加载中」")
        return self

    def wait_input_value(self, css, timeout=None):
        """等输入框被填上值。

        textarea 的 `.text` 恒为空（内容在 value 属性里），所以不能用 wait_value
        —— 编辑页回填断言就是这么失败的（一直"等不到数值"）。
        """
        t = timeout or config.WAIT_TIMEOUT
        WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
            lambda d: (d.find_element(By.CSS_SELECTOR, css).get_attribute("value") or "").strip() != "",
            message="%s 一直没有值（未回填）" % css)
        return self

    def wait_value(self, css, placeholders=("", "—", "-"), timeout=None):
        """等某个数值位被 JS 填上（统计卡/指标卡都是异步填充的）。"""
        t = timeout or config.WAIT_TIMEOUT

        def _ready(d):
            els = d.find_elements(By.CSS_SELECTOR, css)
            return bool(els) and els[0].text.strip() not in placeholders

        WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
            _ready, message="%s 一直是占位符（未加载出数值）" % css)
        return self

    def scroll_stable(self, timeout=3.0):
        """等页面滚动停下来。

        踩过的坑：切题时页面用 `scrollTo({behavior:'smooth'})` 平滑滚动，
        紧接着点「上一题/下一题」会按**旧坐标**点击，点到空白处——表现为
        "点了没反应"，而且偶发。先等 scrollY 连续两次采样不变再点。
        """
        deadline = time.time() + timeout
        last, stable = -1, 0
        while time.time() < deadline:
            y = self.js("return window.scrollY")
            if y == last:
                stable += 1
                if stable >= 2:
                    return self
            else:
                stable, last = 0, y
            time.sleep(0.15)
        return self

    # ------------------------------------------------------------ 下载
    def download(self, action, suffix="", timeout=None):
        """执行 action 并等文件落盘，返回文件路径。

        为什么要这么验：页面里的「导出 / 下载模板」都是
        `global.location.href = <url>`，浏览器把响应当附件下载 —— 页面 URL 不变、
        也不开新标签页。用 current_url 或句柄数判断都会误判，只有文件真的出现才算通过。
        """
        path = os.path.join(config.DATA_DIR, "downloads")
        os.makedirs(path, exist_ok=True)
        for old in glob.glob(os.path.join(path, "*")):
            try:
                os.remove(old)
            except OSError:
                pass

        try:
            self.driver.execute_cdp_cmd("Browser.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": path, "eventsEnabled": True})
        except WebDriverException:
            self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": path})

        action()
        deadline = time.time() + (timeout or config.WAIT_TIMEOUT)
        while time.time() < deadline:
            files = [f for f in glob.glob(os.path.join(path, "*"))
                     if not f.endswith(".crdownload")]
            if files and (not suffix or files[0].lower().endswith(suffix.lower())):
                time.sleep(0.3)                              # 等写盘收尾
                return files[0]
            time.sleep(0.3)
        raise AssertionError("下载未产生文件（目录 %s，期望后缀 %s）" % (path, suffix or "任意"))

    # ------------------------------------------------------------ 原生确认框 / 轻提示
    def accept_alert(self, timeout=None):
        """接受原生 confirm()。

        题库「停用」用的是 `confirm(...)`，不是 Bootstrap 弹窗——
        不处理它，后续所有命令都会被这个模态对话框阻塞（且报 unexpected alert）。
        """
        WebDriverWait(self.driver, timeout or config.SHORT_TIMEOUT,
                      config.POLL_FREQUENCY).until(
            EC.alert_is_present(), message="等不到原生确认框")
        text = self.driver.switch_to.alert.text
        self.driver.switch_to.alert.accept()
        return text

    def dismiss_alert(self, timeout=None):
        WebDriverWait(self.driver, timeout or config.SHORT_TIMEOUT,
                      config.POLL_FREQUENCY).until(
            EC.alert_is_present(), message="等不到原生确认框")
        text = self.driver.switch_to.alert.text
        self.driver.switch_to.alert.dismiss()
        return text

    def toast_text(self):
        """读 UI toast 区最近一条文案（toast 3.6s 后自动消失，要在窗口内读）。"""
        try:
            return self.js(
                "const c=document.getElementById('toast-container');"
                "if(!c||!c.lastElementChild) return '';"
                "return c.lastElementChild.innerText.trim();") or ""
        except WebDriverException:
            return ""

    def wait_toast(self, substring, timeout=None):
        t = timeout or config.SHORT_TIMEOUT
        WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
            lambda d: substring in (self.toast_text() or ""),
            message="等不到提示「%s」，当前提示：%r" % (substring, self.toast_text()))
        return self

    def wait_url(self, substring, timeout=None):
        t = timeout or config.WAIT_TIMEOUT
        WebDriverWait(self.driver, t, config.POLL_FREQUENCY).until(
            lambda d: substring in d.current_url,
            message="URL 未包含 %s（当前 %s）" % (substring, self.driver.current_url))
        return self

    # ------------------------------------------------------------ 现场
    @property
    def title(self):
        return self.driver.title

    @property
    def url(self):
        return self.driver.current_url

    def body_text(self):
        return self.driver.find_element(By.TAG_NAME, "body").text or ""

    def console_errors(self):
        try:
            return [e["message"] for e in self.driver.get_log("browser")
                    if e.get("level") == "SEVERE" and "favicon" not in e.get("message", "")]
        except Exception:                                    # noqa: BLE001
            return []

    def screenshot(self, name):
        path = os.path.join(config.SCREENSHOT_DIR, "%s_%s.png" % (name, time.strftime("%H%M%S")))
        self.driver.save_screenshot(path)
        return path
