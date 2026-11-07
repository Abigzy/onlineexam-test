# -*- coding: utf-8 -*-
"""全局配置与常量。

**注意**：本模块第一件事就是清掉代理环境变量——运行环境注入的 HTTP_PROXY
会让 Selenium 把「发给 chromedriver 的命令」也走代理，表现为 session 建得出来
但所有命令报 "unhandled request"（步骤 4 §5.1 记录过）。任何 import 本模块的
脚本都会自动获得这个保护，所以 conftest / 用例 / 造数脚本都必须先 import config。
"""
import os
import time

# ------------------------------------------------------------------ 代理清理
for _k in [k for k in os.environ if "proxy" in k.lower()]:
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

# ------------------------------------------------------------------ 路径
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))          # onlineexam_ui_autotest/
WORKSPACE = os.path.dirname(PROJECT_DIR)                          # D:/onlineexam-ui-autotest
TOOLS_DIR = os.path.join(WORKSPACE, "tools")

DATA_DIR = os.path.join(PROJECT_DIR, "data")
LOG_DIR = os.path.join(PROJECT_DIR, "log")
REPORT_DIR = os.path.join(PROJECT_DIR, "report")
SCREENSHOT_DIR = os.path.join(REPORT_DIR, "screenshots")
RUNTIME_JSON = os.path.join(DATA_DIR, "runtime.json")
PROFILE_DIR = os.path.join(WORKSPACE, ".cache", "chrome-profile")

# 固定 profile 是为了命中磁盘缓存（首屏 0.5s vs 9~35s），代价是**前端改版后
# 浏览器仍用旧 js/css**：开发已修好、脚本却验证不过（BUG-02 回归就撞上了）。
# 只要本轮验证涉及前端改动，就用 OE_FRESH_PROFILE=1 跑，强制全新 profile。
FRESH_PROFILE = os.environ.get("OE_FRESH_PROFILE") == "1"

for _d in (DATA_DIR, LOG_DIR, REPORT_DIR, SCREENSHOT_DIR, PROFILE_DIR):
    os.makedirs(_d, exist_ok=True)

# ------------------------------------------------------------------ 被测系统
BASE_URL = os.environ.get("OE_BASE", "http://127.0.0.1:8931").rstrip("/")
API_URL = BASE_URL + "/api/v1"

# 驱动随工程入库（PATH 上的 143 与 Chrome 156 不匹配，必须显式指定）
DRIVER_PATH = os.environ.get("OE_CHROMEDRIVER", os.path.join(TOOLS_DIR, "chromedriver.exe"))
ALLURE_BIN = os.path.join(TOOLS_DIR, "allure-2.30.0", "bin",
                          "allure.bat" if os.name == "nt" else "allure")

# ------------------------------------------------------------------ 超时（秒）
PAGE_LOAD_TIMEOUT = 60        # CDN 首屏可能 9~35s
WAIT_TIMEOUT = 20             # 业务节点等待上限
SHORT_TIMEOUT = 8             # 局部刷新（弹窗、局部列表）
POLL_FREQUENCY = 0.2

WINDOW_SIZE = (1440, 900)     # 兼容性用例会另开 1280×800

# ------------------------------------------------------------------ 账号
PASSWORD = os.environ.get("OE_PASS", "Exam@123456")
ACCOUNTS = {
    "student": os.environ.get("OE_STUDENT", "student"),
    "teacher": os.environ.get("OE_TEACHER", "teacher"),
    "admin": os.environ.get("OE_ADMIN", "admin"),
}

# ------------------------------------------------------------------ 造数
PREFIX = "UIAT_"
RUN_TAG = os.environ.get("OE_RUN_TAG") or time.strftime("%m%d%H%M")
KEEP_DATA = os.environ.get("OE_KEEP_DATA", "").lower() in ("1", "true", "yes")

# ------------------------------------------------------------------ 报告
# 跑完自动生成 Allure 报告，由 `conftest.py::pytest_unconfigure` 消费。
#
# **默认开启**：`pytest.ini` 的 `--clean-alluredir` 每次启动都会清空 results，
# 忘了重新生成就会留下「页面能开、数字过期」的旧报告，比报错更误导。默认开着，
# 直接 `pytest` 跑完就有最新报告，不用记第二条命令。
#
# 关闭用 `OE_AUTO_REPORT=0`（`false` / `no` / `off` 同义），只在两种场景需要：
#   - 反复调试单条用例，不想每次都等 Allure 那 5~12s；
#   - 只要 results 给 CI 收集，报告由流水线统一生成。
# 用环境变量而非 `--` 命令行开关，是因为 CI 里加个环境变量比改命令行参数省事。
AUTO_REPORT = os.environ.get("OE_AUTO_REPORT", "1").strip().lower() \
    not in ("0", "false", "no", "off")


def tag(name):
    """造数命名：UIAT_<名称>_<运行标签>，便于精确定位与清理。"""
    return "%s%s_%s" % (PREFIX, name, RUN_TAG)
