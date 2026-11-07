# -*- coding: utf-8 -*-
"""BUG-02 修复验证：4 个场景，覆盖"修得对"与"没修过头"。

A 只填 2 个选项 → 保存成功，**入库选项正好 2 个**（不能只是"没报错"）
B 填满 4 个选项   → 保存成功，入库 4 个（原能力不能丢）
C 嵌套错误结构    → 前端 errorText 渲染出可读文案，不含 `[object Object]`
D 编辑已有题直接保存 → 成功（前端 filter 不能把已有选项误删）

验证完自行清理（题目是软删，只做停用）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(os.path.dirname(ROOT), "onlineexam_ui_autotest")
sys.path.insert(0, PROJ)

import config                                                       # noqa: E402
from common.api_client import ApiSession                            # noqa: E402
from common.driver_factory import create_driver                     # noqa: E402
from pages.teacher_pages import QuestionBankPage, QuestionEditorPage  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  —— " + detail) if detail else ""))


def new_editor(drv):
    page = QuestionEditorPage(drv).open()
    page.fill(stem=config.tag("BUG02验证"), subject="数据结构")
    return page


def find_question(api, stem):
    data = api.get("/questions/", params={"keyword": stem, "page_size": 10})
    for q in data.get("results") or []:
        if q["stem"] == stem:
            return q["id"]
    return None


def main():
    api = ApiSession(config.ACCOUNTS["teacher"])
    drv = create_driver()
    created = []
    try:
        drv.get(config.BASE_URL + "/login/")
        drv.delete_all_cookies()
        drv.add_cookie({"name": "sessionid", "value": api.session_id,
                        "domain": "127.0.0.1", "path": "/"})

        # ---------------- A 只填 2 个选项 ----------------
        page = new_editor(drv)
        page.fill_option(0, "甲", correct=True)
        page.fill_option(1, "乙")
        stem_a = page.values()["stem"]
        page.save_expect_list()
        qid_a = find_question(api, stem_a)
        if qid_a:
            created.append(qid_a)
        detail = api.get("/questions/%s/" % qid_a) if qid_a else {}
        opts = detail.get("options") or []
        check("A 只填 2 个选项可保存", qid_a is not None,
              "题目已创建 id=%s" % qid_a)
        check("A 入库选项正好 2 个", len(opts) == 2,
              "实际 %d 个：%s" % (len(opts), [o.get("content") for o in opts]))
        check("A 正确答案仍为 A",
              [o["label"] for o in opts if o.get("is_correct")] == ["A"],
              "实际 %s" % [o.get("label") for o in opts if o.get("is_correct")])

        # ---------------- B 填满 4 个选项 ----------------
        page = new_editor(drv)
        for i, text in enumerate(("甲", "乙", "丙", "丁")):
            page.fill_option(i, text, correct=(i == 0))
        stem_b = page.values()["stem"]
        page.save_expect_list()
        qid_b = find_question(api, stem_b)
        if qid_b:
            created.append(qid_b)
        opts_b = (api.get("/questions/%s/" % qid_b).get("options") if qid_b else []) or []
        check("B 填满 4 个选项可保存", qid_b is not None, "id=%s" % qid_b)
        check("B 入库选项仍是 4 个", len(opts_b) == 4, "实际 %d 个" % len(opts_b))

        # ---------------- C 嵌套错误结构可读 ----------------
        render = drv.execute_script("""
            return UI.errorText({data: {options: [{}, {},
                {content: ['该字段不能为空。']}, {content: ['该字段不能为空。']}]}});
        """)
        check("C 嵌套错误不含 [object Object]", "[object Object]" not in (render or ""),
              "渲染结果：%r" % (render or "")[:120])
        check("C 嵌套错误能读出原文", "该字段不能为空" in (render or ""),
              "渲染结果：%r" % (render or "")[:120])

        # ---------------- D 编辑已有题直接保存 ----------------
        page = QuestionEditorPage(drv).open_edit(qid_b)
        before_opts = page.option_count()
        page.save_in_place()
        opts_d = (api.get("/questions/%s/" % qid_b).get("options") or [])
        check("D 编辑保存不误删选项", len(opts_d) == before_opts,
              "编辑前 %d 个，保存后 %d 个" % (before_opts, len(opts_d)))

    finally:
        for qid in created:
            try:
                api.delete("/questions/%s/" % qid, expect=(200, 204))
            except Exception as exc:                                # noqa: BLE001
                print("清理 %s 失败：%s" % (qid, exc))
        drv.quit()

    failed = [r for r in RESULTS if not r[1]]
    print()
    print("汇总：%d 项通过 / %d 项失败" % (len(RESULTS) - len(failed), len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
