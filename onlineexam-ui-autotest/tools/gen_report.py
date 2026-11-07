# -*- coding: utf-8 -*-
"""生成 Allure 静态报告（Python 版，PyCharm 里可直接右键 Run）。

实现主体在 `onlineexam_ui_autotest/common/report_builder.py`——
`conftest.py` 的自动触发（默认开启，`OE_AUTO_REPORT=0` 可关）用的是同一份代码，
这里只是加个命令行外壳，避免两处逻辑各改一半。正常跑完 pytest 报告就是最新的，
本脚本用于**手动补生成/兜底**（自动生成失败，或只想重算环境信息）。

用法（在 PyCharm 里打开本文件点绿色三角即可，无需配置参数）：
  D:/python/python.exe tools/gen_report.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "onlineexam_ui_autotest"))

from common.report_builder import build                      # noqa: E402


def main():
    info = build()
    if info["code"] != 0:
        print("[FAIL] %s" % info["msg"])
    return info["code"]


if __name__ == "__main__":
    raise SystemExit(main())
