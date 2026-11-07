# -*- coding: utf-8 -*-
"""环境自检（测试计划 §7.1「进入标准」的可执行版本）。

只要有一项 FAIL，就不该开始跑用例——这一步的价值是把"环境问题"和"用例失败"分开，
避免把缺驱动、服务没起这类问题记成缺陷。

用法：
    python tools/check_env.py
    python tools/check_env.py --base http://127.0.0.1:8931
"""
import argparse
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(ROOT)
RESULTS = []

# 同 probe_locators：进程内清代理，否则 requests/Selenium 都会被沙箱代理吃掉
for _k in [k for k in os.environ if "proxy" in k.lower()]:
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("[%s] %-24s %s" % ("PASS" if ok else "FAIL", name, detail))
    return ok


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out.strip()
    except Exception as exc:                                   # noqa: BLE001
        return -1, repr(exc)


def chrome_paths():
    cands = [
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    ]
    return [c for c in cands if c and os.path.exists(c)]


def chrome_version():
    for exe in chrome_paths():
        base = os.path.dirname(exe)
        vers = [d for d in os.listdir(base)
                if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", d) and os.path.isdir(os.path.join(base, d))]
        if vers:
            vers.sort(key=lambda v: [int(x) for x in v.split(".")])
            return vers[-1], exe
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("OE_BASE", "http://127.0.0.1:8931"))
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print("=" * 78)
    print("OnlineExam UI 自动化 · 环境自检")
    print("=" * 78)

    # 1 Python
    v = sys.version_info
    check("Python 解释器", v >= (3, 9), "%d.%d.%d @ %s" % (v.major, v.minor, v.micro, sys.executable))

    # 2 依赖
    try:
        import selenium
        check("selenium", tuple(int(x) for x in selenium.__version__.split(".")[:2]) >= (4, 0),
              selenium.__version__)
    except ImportError:
        check("selenium", False, "未安装")
    for mod, label in [("pytest", "pytest"), ("allure_pytest", "allure-pytest"),
                       ("requests", "requests"), ("yaml", "PyYAML"), ("openpyxl", "openpyxl")]:
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "?")
            check(label, True, ver)
        except ImportError:
            check(label, False, "未安装")

    # 3 浏览器
    cver, cpath = chrome_version()
    check("Chrome 可执行文件", bool(cver), cpath or "未找到（候选路径均不存在）")
    if cver:
        print("      Chrome 版本 %s" % cver)

    # 4 驱动
    drv = os.path.join(ROOT, "chromedriver.exe")
    rc, out = run([drv, "--version"]) if os.path.exists(drv) else (-1, "文件不存在")
    m = re.search(r"ChromeDriver (\d+\.\d+\.\d+\.\d+)", out)
    dver = m.group(1) if m else None
    check("chromedriver（随工程）", bool(dver), dver or out[:60])
    if dver and cver:
        same = dver.split(".")[0] == cver.split(".")[0]
        check("浏览器/驱动主版本一致", same,
              "Chrome %s vs driver %s" % (cver, dver) if same
              else "不一致：Chrome %s vs driver %s（必须同主版本）" % (cver, dver))

    # 5 Allure CLI + Java
    allure_bat = os.path.join(ROOT, "allure-2.30.0", "bin", "allure.bat")
    rc, out = run([allure_bat, "--version"]) if os.path.exists(allure_bat) else (-1, "未安装")
    check("Allure CLI", rc == 0, out.splitlines()[0] if out else "未安装")
    rc, out = run(["java", "-version"])
    check("Java（Allure 依赖）", rc == 0, out.splitlines()[0] if out else "未找到 java")

    # 6 服务健康
    import requests
    try:
        r = requests.get(base + "/api/health/", timeout=10)
        check("服务健康检查", r.status_code == 200, "%s -> HTTP %s" % (base, r.status_code))
    except Exception as exc:                                    # noqa: BLE001
        check("服务健康检查", False, "%s 不可达（%s）" % (base, type(exc).__name__))

    # 7 三角色登录
    for user in ("student", "teacher", "admin"):
        try:
            s = requests.Session()
            s.trust_env = False
            page = s.get(base + "/login/", timeout=15)
            tok = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
            r = s.post(base + "/login/",
                       data={"csrfmiddlewaretoken": tok.group(1) if tok else "",
                             "username": user, "password": os.environ.get("OE_PASS", "Exam@123456"),
                             "next": ""},
                       headers={"Referer": base + "/login/"}, allow_redirects=False, timeout=15)
            ok = r.status_code in (301, 302) and "sessionid" in s.cookies
            check("登录 %s" % user, ok, "HTTP %s，sessionid %s" % (
                r.status_code, "有" if "sessionid" in s.cookies else "无"))
        except Exception as exc:                                # noqa: BLE001
            check("登录 %s" % user, False, repr(exc)[:60])

    failed = [r for r in RESULTS if not r[1]]
    print("-" * 78)
    print("检查 %d 项，通过 %d 项，失败 %d 项" % (len(RESULTS), len(RESULTS) - len(failed), len(failed)))
    if failed:
        print("未通过：" + "；".join(n for n, _, _ in failed))
        print("→ 先修环境（见 docs/04-环境搭建与元素定位.md §5 排查手册），再跑用例。")
        return 1
    print("环境就绪，可以执行 tools/probe_locators.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
