# -*- coding: utf-8 -*-
"""第 1 步（可行性评估）用的一次性探针：验证 Chrome + Selenium 能否登录并连续点击。

不属于交付工程，结论写进 docs/01-需求分析与自动化可行性评估.md 后即可删除。
运行：env -u HTTP_PROXY -u HTTPS_PROXY D:/python/python.exe tmp/probe_feasibility.py
"""
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

# PATH 上的 chromedriver 是 143，与 Chrome 156 不匹配；显式指定 156 驱动
DRIVER = os.environ.get(
    "OE_CHROMEDRIVER",
    os.path.join(os.environ.get("OE_PROJECT", "D:/OnlineExam"), "scripts", "drivers", "chromedriver.exe"),
)

BASE = os.environ.get("OE_BASE", "http://127.0.0.1:8931")
USERNAME = "student"
PASSWORD = "Exam@123456"

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--window-size=1400,1000")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-gpu")
opts.add_argument("--lang=zh-CN")

t0 = time.time()
drv = webdriver.Chrome(service=Service(DRIVER), options=opts)
print("[1] 浏览器启动 OK  %.2fs  version=%s" % (time.time() - t0, drv.capabilities.get("browserVersion")))
drv.set_page_load_timeout(60)

wait = WebDriverWait(drv, 20)

drv.get(BASE + "/login/")
print("[2] 打开登录页 OK  title=%r  status_hint=%s" % (drv.title, drv.execute_script("return document.readyState")))
print("    表单字段: username=%s password=%s submit=%s" % (
    len(drv.find_elements(By.CSS_SELECTOR, "input[name='username']")),
    len(drv.find_elements(By.CSS_SELECTOR, "input[name='password']")),
    len(drv.find_elements(By.CSS_SELECTOR, "button[type='submit']")),
))

drv.find_element(By.CSS_SELECTOR, "input[name='username']").send_keys(USERNAME)
drv.find_element(By.CSS_SELECTOR, "input[name='password']").send_keys(PASSWORD)
t1 = time.time()
drv.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
wait.until(lambda d: "/login/" not in d.current_url)
print("[3] 登录成功 OK  %.2fs  url=%s  title=%r" % (time.time() - t1, drv.current_url, drv.title))

# 连续两次真实点击（Edge headless 已知在此崩溃，验证 Chrome 是否稳定）
links = drv.find_elements(By.CSS_SELECTOR, "a.nav-link, .navbar a")
print("[4] 导航链接数=%d" % len(links))

drv.get(BASE + "/my-exams/")
wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
print("[5] 我的考试页 OK  title=%r" % drv.title)

# 点一次 tab（我的考试页的三个页签），再点一次刷新
try:
    tabs = drv.find_elements(By.CSS_SELECTOR, "#tabs .nav-link, #tabs button")
    print("    页签数=%d" % len(tabs))
    if len(tabs) > 1:
        tabs[1].click()
        time.sleep(1)
        print("[6] 第一次点击 OK  当前激活=%r" % tabs[1].get_attribute("class"))
    btn = drv.find_element(By.CSS_SELECTOR, "#btn-refresh")
    btn.click()
    time.sleep(1)
    print("[7] 第二次点击 OK（Chrome 连点未崩）")
except Exception as exc:  # noqa: BLE001
    print("[7] 连点异常: %r" % exc)

# 页面是否渲染出卡片（JS 渲染，验证等待策略必要）
cards = drv.find_elements(By.CSS_SELECTOR, "#exam-cards > *")
print("[8] 卡片节点数=%d  body_text_len=%d" % (len(cards), len(drv.find_element(By.TAG_NAME, "body").text)))

drv.get(BASE + "/analytics/me/")
time.sleep(3)
print("[9] 我的学情页 title=%r  canvas/echarts=%d" % (
    drv.title, len(drv.find_elements(By.CSS_SELECTOR, "canvas, div[_echarts_instance_]"))))

drv.save_screenshot(os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_my_exams.png"))
drv.quit()
print("[done] 总耗时 %.2fs" % (time.time() - t0))
