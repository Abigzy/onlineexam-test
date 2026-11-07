# -*- coding: utf-8 -*-
"""浏览器工厂：只负责"造一个干净的 browser"，别的一概不管。"""
import os
import shutil

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

import config


def create_driver(headless=True, window=(1440, 900)):
    if config.FRESH_PROFILE:
        # 前端有改动时必须清缓存，否则页面加载的还是旧 js（详见 config.FRESH_PROFILE 注释）
        reset_profile()

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=%d,%d" % window)
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--lang=zh-CN")
    opts.add_argument("--disable-dev-shm-usage")
    # 「导出」是 window.open(url, "_blank")：不放开弹窗拦截，headless 下一个窗口都不会开
    opts.add_argument("--disable-popup-blocking")
    # 「导出」是 window.open(url, "_blank")：不放开弹窗拦截，headless 下一个窗口都不会开
    opts.add_argument("--disable-popup-blocking")
    # 固定 profile：命中 CDN 磁盘缓存，首屏从 9~35s 降到 0.5s（步骤 4 实测）
    opts.add_argument("--user-data-dir=" + config.PROFILE_DIR)
    # 失败现场需要控制台日志
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    drv = webdriver.Chrome(service=Service(config.DRIVER_PATH), options=opts)

    # 禁用 CSS 过渡/动画（**关键**）：headless 下 transitionend 往往不触发，
    # Bootstrap 关弹窗时会卡在"移除 .show 但 backdrop 没清"的中间态，
    # 遮罩永久挡住后续点击——表现为"点了没反应"，极难定位。
    # 注入到每个新文档，测试语义不受影响（我们断言的是最终状态，不是动画）。
    # 注意没有 `document.documentElement` 的兜底会**自己制造 JS 报错**：
    # addScriptToEvaluateOnNewDocument 在文档刚创建时执行，documentElement 可能还是 null，
    # 于是控制台出现 `Cannot read properties of null (reading 'appendChild')`。
    # 这条曾被我误判成"监控页产品缺陷"——查到底是自己的注入脚本。
    drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": (
            "(function(){var css='*,*::before,*::after{transition:none!important;"
            "animation:none!important}';"
            "function add(){var t=document.head||document.documentElement;"
            "if(!t){setTimeout(add,0);return;}"
            "var s=document.createElement('style');s.textContent=css;t.appendChild(s);}"
            "add();})();"
        )})
    drv.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    drv.implicitly_wait(0)          # 显式等待是唯一同步手段
    return drv


def reset_profile():
    """profile 被占用会报 DevToolsActivePort（步骤 4 §5.3），换机器/异常退出后调用。"""
    if os.path.isdir(config.PROFILE_DIR):
        shutil.rmtree(config.PROFILE_DIR, ignore_errors=True)
    os.makedirs(config.PROFILE_DIR, exist_ok=True)
