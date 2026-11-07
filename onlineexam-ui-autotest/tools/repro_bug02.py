# -*- coding: utf-8 -*-
"""BUG-02 受控复现：前端把空选项行原样提交 → 后端 400 + 提示不可读。

两段证据：
    1. 前端：打开新增页，只填 A/B 两个选项，抓 `collect()` 实际会发出的 payload；
    2. 后端：用同一 payload 打 `POST /questions/`，看返回的错误结构。
只读操作，不会写入数据库（请求必然失败）。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(os.path.dirname(ROOT), "onlineexam_ui_autotest")
sys.path.insert(0, PROJ)

import config                                                       # noqa: E402
from common.api_client import ApiSession                            # noqa: E402
from common.driver_factory import create_driver                     # noqa: E402
from pages.teacher_pages import QuestionEditorPage                  # noqa: E402


def main():
    api = ApiSession(config.ACCOUNTS["teacher"])
    drv = create_driver()
    try:
        drv.get(config.BASE_URL + "/login/")
        drv.delete_all_cookies()
        drv.add_cookie({"name": "sessionid", "value": api.session_id,
                        "domain": "127.0.0.1", "path": "/"})

        page = QuestionEditorPage(drv).open()
        page.fill(stem=config.tag("BUG02复现题干"), subject="数据结构")
        page.fill_option(0, "甲", correct=True)
        page.fill_option(1, "乙")
        print("页面默认渲染选项行数：%d（A/B/C/D，其中 C/D 为空）"
              % page.option_count())

        # 等价于 collect()：不过滤空行
        payload = {
            "type": "single", "difficulty": 2, "score": 2,
            "stem": page.values()["stem"], "subject": "数据结构", "analysis": "",
            "is_active": True, "is_reviewed": True, "knowledge_point_ids": [],
            "options": [{"label": o["label"], "content": o["content"],
                         "is_correct": o["correct"]} for o in page.option_rows()],
        }
        print("前端实际提交的 options：%s"
              % json.dumps(payload["options"], ensure_ascii=False))

        # 还原"用户只填了 A/B"的场景：C/D 是空字符串
        r = api.session.post(config.API_URL + "/questions/", json=payload, timeout=30)
        body = r.json()
        print("后端响应：HTTP %s" % r.status_code)
        print("报文 code=%s message=%s" % (body.get("code"), body.get("message")))
        print("errors=%s" % json.dumps(body.get("errors") or body.get("data"),
                                       ensure_ascii=False)[:400])

        # 前端怎么显示：UI.errorText 对数组元素做 String()
        errs = (body.get("errors") or {})
        options_err = errs.get("options") if isinstance(errs, dict) else None
        if isinstance(options_err, list):
            shown = "；".join(str(x) for x in options_err)
            print("前端 toast 实际文案：options：%s" % shown)

        print()
        print("判定：默认 4 个空选项行被原样提交 → 后端每个空行返回一个错误对象 →")
        print("      前端对对象做 String() 得到「[object Object]」，用户无法理解。")
        print("      预期：只提交已填写的选项，或提示「第 3 行选项内容不能为空」。")
    finally:
        drv.quit()


if __name__ == "__main__":
    main()
