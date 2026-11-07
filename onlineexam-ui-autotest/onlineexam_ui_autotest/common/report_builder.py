# -*- coding: utf-8 -*-
"""生成 Allure 静态报告：写环境信息 → `allure generate` → 入口改名。

**为什么单独抽一个模块**：这份逻辑有两个调用方——手工跑的 `tools/gen_report.py`
与 `conftest.py::pytest_unconfigure`（默认就触发，`OE_AUTO_REPORT=0` 可关）。
两边各抄一份，迟早出现"手工生成的首页有环境信息、自动生成的没有"这种漂移。

只依赖标准库（不 import selenium / allure / config），因为 pytest 会话收尾时
调用本模块，任何多余依赖都可能让"生成报告"这一步把整个会话的退出码搞脏。

关键约定：
  - `environment.properties` **全 ASCII**。Allure 用 Java `Properties` 读取，
    中文会乱码成 `????`；报告界面本身的文案由 Allure 前端负责翻译，不需要我们写中文。
  - `Run` / `Scope` **不写死**，从 `*-result.json` 现算（时间窗 + 通过/跳过/失败数）。
    写死的后果很隐蔽：自动生成时每轮报告首页都显示同一个日期，看着像"没重新生成"。
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
ROOT = PROJ.parent
RESULTS = PROJ / "report" / "allure-results"
OUT = PROJ / "report" / "allure-report"
BIN = ROOT / "tools" / "allure-2.30.0" / "bin"

GENERATE_TIMEOUT = 300          # 秒。Allure 是 JVM 进程，卡住时不能让会话陪葬


def _pkg(name, default="?"):
    """取已安装包版本；取不到就给默认值，不让环境信息这一步失败。"""
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:                                    # noqa: BLE001
        return default


def chrome_major():
    """从 chromedriver 取浏览器大版本，避免写死（换机器不会骗人）。"""
    drv = ROOT / "tools" / "chromedriver.exe"
    if not drv.exists():
        return "unknown"
    try:
        out = subprocess.run([str(drv), "--version"], capture_output=True, text=True,
                             timeout=20).stdout
        return out.split()[1].split(".")[0]
    except Exception:                                    # noqa: BLE001
        return "unknown"


def scan(results=None):
    """扫一遍结果目录，返回 `(时间窗, 统计, 自动标签)`。

    读不动某个文件就跳过——报告生成不该因为一个坏掉的 json 整体失败。
    自动标签取时间窗起点，格式与 `config.RUN_TAG` 一致（`%m%d%H%M`），
    这样报告首页的 `Run` 与 `log/` 里的 `ui_<tag>.log` 能对上号。
    """
    results = Path(results or RESULTS)
    starts, stops, stat = [], [], {}
    for f in results.glob("*-result.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                # noqa: BLE001
            continue
        if d.get("start"):
            starts.append(d["start"])
        if d.get("stop"):
            stops.append(d["stop"])
        stat[d.get("status")] = stat.get(d.get("status"), 0) + 1

    total = sum(stat.values())
    if not starts:
        return "unknown", "%d items" % total, ""

    def fmt(ms, pattern="%Y-%m-%d %H:%M:%S"):
        return datetime.fromtimestamp(ms / 1000.0).strftime(pattern)

    begin, end = min(starts), max(stops or starts)
    window = "%s ~ %s" % (fmt(begin), fmt(end))
    scope = ("%d items: %d passed / %d skipped / %d failed"
             % (total, stat.get("passed", 0), stat.get("skipped", 0), stat.get("failed", 0)))
    return window, scope, fmt(begin, "%m%d%H%M")


def env_lines(results=None, run_tag=None):
    window, scope, auto_tag = scan(results)
    tag = run_tag or os.environ.get("OE_RUN_TAG") or auto_tag or "untagged"
    run = "%s  [tag %s]" % (window, tag) if window != "unknown" else "[tag %s]" % tag
    return [
        "System=OnlineExam (Django + MySQL, AI exam & analytics)",
        "Base.URL=%s" % os.environ.get("OE_BASE", "http://127.0.0.1:8931").rstrip("/"),
        "Browser=Chrome %s (headless=new)" % chrome_major(),
        "Runtime=Windows local, Python %d.%d.%d" % sys.version_info[:3],
        "Framework=pytest %s + selenium %s + allure-pytest %s"
        % (_pkg("pytest"), _pkg("selenium"), _pkg("allure-pytest")),
        "Database=MySQL 5.6.46 / online_exam",
        "Run=%s" % run,
        "Scope=%s" % scope,
    ]


def write_env(results=None, run_tag=None):
    """Allure 只认 results 目录下的 environment.properties；不写则首页 ENVIRONMENT 区为空。"""
    results = Path(results or RESULTS)
    text = "\n".join(env_lines(results, run_tag)) + "\n"
    (results / "environment.properties").write_text(text, encoding="ascii", errors="replace")
    return text


def build(results=None, out=None, run_tag=None, quiet=False):
    """执行完整生成流程。

    返回 dict：`{"code": 退出码, "count": 用例数, "out": 报告目录, "msg": 失败原因}`
    ——调用方（conftest）据此只打日志、不抛异常，永不改动 pytest 的退出码。
    """
    results = Path(results or RESULTS)
    out = Path(out or OUT)
    say = (lambda *a: None) if quiet else (lambda *a: print(*a))

    allure = BIN / ("allure.bat" if os.name == "nt" else "allure")
    if not allure.exists():
        return {"code": 2, "count": 0, "out": out, "msg": "找不到 Allure CLI: %s" % allure}
    if not results.is_dir() or not any(results.iterdir()):
        return {"code": 3, "count": 0, "out": out, "msg": "结果目录为空: %s" % results}

    say("[1/3] 写入环境信息 environment.properties")
    write_env(results, run_tag)

    say("[2/3] allure generate -> %s" % out)
    cmd = [str(allure), "generate", str(results), "-o", str(out), "--clean"]
    if os.name == "nt":                                  # .bat 需经 cmd 启动
        cmd = ["cmd", "/c"] + cmd
    kw = {"timeout": GENERATE_TIMEOUT}
    if quiet:                                            # 自动模式下别把 JVM 输出混进 pytest 汇总
        kw.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                  encoding="utf-8", errors="replace")
    try:
        proc = subprocess.run(cmd, **kw)
    except subprocess.TimeoutExpired:
        return {"code": 4, "count": 0, "out": out,
                "msg": "allure generate 超过 %ds 未结束" % GENERATE_TIMEOUT}
    if proc.returncode != 0:
        tail = ((proc.stdout or "").strip().splitlines() or ["（无输出）"])[-3:]
        return {"code": proc.returncode, "count": 0, "out": out,
                "msg": "allure generate 失败，退出码 %d：%s" % (proc.returncode, " / ".join(tail))}

    say("[3/3] 入口重命名 index.html -> uireport.html")
    src = out / "index.html"
    if src.exists():
        target = out / "uireport.html"
        if target.exists():
            target.unlink()
        src.rename(target)

    cases = out / "data" / "test-cases"
    count = len(list(cases.glob("*.json"))) if cases.is_dir() else 0
    say("[OK] 用例数 %d，入口: %s" % (count, out / "uireport.html"))
    return {"code": 0, "count": count, "out": out, "msg": ""}
