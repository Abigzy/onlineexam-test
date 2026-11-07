# -*- coding: utf-8 -*-
"""定位器实测探针：在真实浏览器里逐条验证 tools/locators.yaml。

做什么
    1. 用表单登录（Django 表单 POST + CSRF）分别拿到 student / teacher / admin 的 sessionid；
    2. 把 sessionid 注入 Chrome，逐页打开；
    3. 等"业务节点"（YAML 的 wait），再对每条定位器统计命中数 / 是否可见 / 首元素文本；
    4. 结果写 tools/locator_report.json，控制台打印可读表格，任一低于 min 直接退出码 1。

不做什么
    - 不点按钮、不建数据（那是步骤 6 的执行脚本干的）；
    - 不修改被测项目。

用法
    python tools/check_env.py            # 先确认环境
    python tools/probe_locators.py       # 再跑定位器实测
    python tools/probe_locators.py --only teacher-question-bank,student-take
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse

import requests
import yaml
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(ROOT)
DRIVER = os.path.join(ROOT, "chromedriver.exe")
SPEC = os.path.join(ROOT, "locators.yaml")
REPORT = os.path.join(ROOT, "locator_report.json")

# 环境坑（踩过，别再犯）：运行环境注入了 HTTP_PROXY/HTTPS_PROXY（沙箱代理），
# Selenium 会把「驱动命令」也走代理，导致每条命令都返回 "unhandled request"，
# 表现为 session 建得出来但 get/execute_script 全失败。必须在进程内清掉。
for _k in [k for k in os.environ if "proxy" in k.lower()]:
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

COUNT_JS = """
const el = document.querySelectorAll(arguments[0]);
const first = el[0];
let visible = false, text = '';
if (first) {
  const r = first.getBoundingClientRect();
  visible = r.width > 0 && r.height > 0;
  text = (first.innerText || first.value || first.textContent || '').trim();
}
return [el.length, visible, text];
"""


def load_spec():
    with open(SPEC, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fill_ids(path, ids):
    def rep(m):
        key = m.group(1)
        if key not in ids:
            raise KeyError("locators.yaml ids 缺少 %s" % key)
        return str(ids[key])
    return re.sub(r"\{(\w+)\}", rep, path)


def login_session(base, username, password):
    """表单登录，返回 (session, 状态说明)。"""
    s = requests.Session()
    s.trust_env = False          # 绕开系统代理，否则会假 404
    r = s.get(base + "/login/", timeout=20)
    if r.status_code != 200:
        return s, "GET /login/ -> %s" % r.status_code
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
    token = m.group(1) if m else s.cookies.get("csrftoken")
    r2 = s.post(base + "/login/",
                data={"csrfmiddlewaretoken": token, "username": username,
                      "password": password, "next": ""},
                headers={"Referer": base + "/login/"}, allow_redirects=False, timeout=20)
    ok = r2.status_code in (301, 302) and "sessionid" in s.cookies
    return s, ("登录成功" if ok else "登录失败 HTTP %s" % r2.status_code)


def build_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1440,900")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--lang=zh-CN")
    opts.add_argument("--user-data-dir=" + os.path.join(ROOT, ".chrome-profile"))
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    drv = webdriver.Chrome(service=Service(DRIVER), options=opts)
    drv.set_page_load_timeout(60)
    return drv


def set_session_cookie(drv, base, session):
    drv.get(base + "/login/")
    drv.delete_all_cookies()
    host = urllib.parse.urlparse(base).hostname
    for c in session.cookies:
        if c.name == "sessionid":
            drv.add_cookie({"name": c.name, "value": c.value,
                            "domain": host, "path": "/"})
            return True
    return False


def probe_page(drv, base, page, ids, session):
    path = fill_ids(page["path"], ids)
    url = base + path
    try:
        status = session.get(url, timeout=30, allow_redirects=False).status_code
    except Exception:                                     # noqa: BLE001
        status = -1
    wait_sel = page.get("wait")
    wait_ok, wait_err = True, ""
    t0 = time.time()
    try:
        drv.get(url)
    except TimeoutException:
        pass
    if wait_sel:
        try:
            WebDriverWait(drv, 20).until(
                lambda d: d.execute_script(
                    "return document.querySelectorAll(arguments[0]).length>0", wait_sel))
        except TimeoutException:
            wait_ok, wait_err = False, "等待 %s 超时（20s）" % wait_sel
    time.sleep(0.4)          # 给 fetch 后二段渲染留一点时间，非固定等待业务逻辑
    rows = []
    for loc in page.get("locators", []):
        css = loc["css"]
        min_n = loc.get("min", 1)
        try:
            count, visible, text = drv.execute_script(COUNT_JS, css)
        except WebDriverException as exc:
            count, visible, text = -1, False, "JS 异常: %s" % str(exc)[:80]
        ok = count >= min_n
        rows.append({"name": loc["name"], "css": css, "min": min_n, "count": count,
                     "visible": bool(visible), "text": (text or "")[:40].replace("\n", " "),
                     "ok": ok, "note": loc.get("note", "")})
    errs = []
    try:
        for e in drv.get_log("browser"):
            if e.get("level") == "SEVERE" and "favicon" not in e.get("message", ""):
                errs.append(e["message"][:120])
    except Exception:                                     # noqa: BLE001
        pass
    return {"id": page["id"], "role": page["role"], "path": path, "status": status,
            "wait": wait_sel, "wait_ok": wait_ok, "wait_err": wait_err,
            "elapsed": round(time.time() - t0, 2), "console_errors": errs,
            "locators": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑指定页面 id，逗号分隔")
    ap.add_argument("--headful", action="store_true")
    args = ap.parse_args()

    spec = load_spec()
    base = os.environ.get("OE_BASE", spec["base_url"]).rstrip("/")
    ids = spec.get("ids", {})
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    print("被测地址 : %s" % base)
    print("驱动     : %s" % DRIVER)
    sessions, login_msg = {}, {}
    for role, cred in spec["accounts"].items():
        s, msg = login_session(base, cred["username"], cred["password"])
        sessions[role] = s
        login_msg[role] = msg
        print("登录 %-8s: %s" % (role, msg))
    if any("失败" in m for m in login_msg.values()):
        print("\n有角色登录失败，先修环境再跑定位器。")
        return 2

    if args.headful:
        os.environ["OE_HEADFUL"] = "1"

    drv = build_driver()
    print("浏览器   : Chrome %s / driver %s" % (
        drv.capabilities.get("browserVersion"),
        getattr(drv.capabilities.get("chrome", {}), "get", lambda *_: "?")("chromedriverVersion", "?").split(" ")[0]))
    results, current_role = [], None
    try:
        for page in spec["pages"]:
            if only and page["id"] not in only:
                continue
            role = page["role"]
            if role != current_role:
                if not set_session_cookie(drv, base, sessions[role]):
                    print("!! 角色 %s 的 session 注入失败" % role)
                current_role = role
            res = probe_page(drv, base, page, ids, sessions[role])
            results.append(res)
            passed = sum(1 for r in res["locators"] if r["ok"])
            total = len(res["locators"])
            flag = "OK  " if passed == total and res["wait_ok"] else "FAIL"
            print("[%s] %-28s %-42s HTTP %-3s 定位器 %d/%d  %.1fs" % (
                flag, res["id"], res["path"], res["status"], passed, total, res["elapsed"]))
            if not res["wait_ok"]:
                print("       ! %s" % res["wait_err"])
            for r in res["locators"]:
                if not r["ok"]:
                    print("       ! %s  (%s)  命中 %s < %s  %s" % (
                        r["name"], r["css"], r["count"], r["min"], r["note"]))
            if res["console_errors"]:
                print("       · 控制台 SEVERE: %s" % res["console_errors"][0])
    finally:
        drv.quit()

    bad = [r for r in results
           if not r["wait_ok"] or any(not x["ok"] for x in r["locators"])]
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "base_url": base,
        "login": login_msg,
        "pages_total": len(results),
        "pages_with_issue": len(bad),
        "locators_total": sum(len(r["locators"]) for r in results),
        "locators_ok": sum(1 for r in results for x in r["locators"] if x["ok"]),
        "pages": results,
    }
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n===== 汇总 =====")
    print("页面 %d 个，定位器 %d 条，通过 %d 条，问题页面 %d 个" % (
        report["pages_total"], report["locators_total"],
        report["locators_ok"], report["pages_with_issue"]))
    print("报告：%s" % REPORT)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
