# -*- coding: utf-8 -*-
"""BUG-03 受控复现：组卷页「单个知识点勾选」完全无效。

判定链（三段证据，缺一不可）：
    1. DOM：`<input ... data-kp>` 是**无值属性**，`dataset.kp === ""`（falsy）；
    2. 行为：真实点击勾选后，`/papers/pool/` **没有**重新请求；
    3. 后果：点「预览」发出的 `/papers/ai-compose/` 里 `knowledge_point_ids` 仍是空数组
       → 组卷按整个学科抽题，用户勾的知识点根本没参与。

对照组：「全选/清空」`#kpToggleAll` 直接操作 state，是生效的 —— 用它证明
"不是题池接口不认参数，而是单个勾选这一步根本没跑"。
"""
import json
import os
import sys
import time
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(os.path.dirname(ROOT), "onlineexam_ui_autotest")
sys.path.insert(0, PROJ)

import config                                                       # noqa: E402
from common.api_client import ApiSession                            # noqa: E402
from common.data_factory import load_runtime, seed_paper_draft      # noqa: E402
from common.driver_factory import create_driver                     # noqa: E402
from pages.teacher_pages import PaperComposePage                    # noqa: E402

INTERCEPT = """
window.__req = [];
const of = window.fetch;
window.fetch = function (u, o) {
    try { window.__req.push({url: String(u), body: (o && o.body) || ""}); } catch (e) {}
    return of.apply(this, arguments);
};
"""


def main():
    rt = load_runtime()
    # 必须每次都调：pytest 收尾的 cleanup 会删掉 UIAT_ 试卷，
    # 而 runtime.json 里还留着旧 id（踩过——直接取 id 会 404/回填不到标题）。
    paper = seed_paper_draft(rt)
    api = ApiSession(config.ACCOUNTS["teacher"])
    drv = create_driver()
    try:
        drv.get(config.BASE_URL + "/login/")
        drv.delete_all_cookies()
        drv.add_cookie({"name": "sessionid", "value": api.session_id,
                        "domain": "127.0.0.1", "path": "/"})
        page = PaperComposePage(drv).open_paper(paper["id"])
        drv.execute_script(INTERCEPT)

        # ---------- 1. DOM 证据 ----------
        info = drv.execute_script(
            "const b=document.querySelector('#kpTree input[data-kp]');"
            "return {attr: b.getAttribute('data-kp'), dataset: b.dataset.kp,"
            "        truthy: !!b.dataset.kp, value: b.value, text: b.parentElement.innerText.trim()};")
        print("① DOM：<input data-kp> 的 dataset.kp = %r（truthy=%s），知识点=%r"
              % (info["dataset"], info["truthy"], info["text"].split()[0]))

        # ---------- 2. 单个勾选 ----------
        drv.execute_script(
            "const b=document.querySelectorAll('#kpTree input[data-kp]')[1];"
            "b.scrollIntoView({block:'center'}); b.click();")
        time.sleep(1.5)
        reqs = drv.execute_script("return window.__req;")
        pool = [r for r in reqs if "/papers/pool/" in r["url"]]
        print("② 勾选后 /papers/pool/ 请求数 = %d（预期 ≥1，实际说明勾选没触发 loadPool）" % len(pool))
        print("   勾选状态 = %s（界面显示已勾选，但状态没进 selectedKps）"
              % drv.execute_script(
                  "return document.querySelectorAll('#kpTree input[data-kp]')[1].checked;"))

        # ---------- 3. 后果：预览请求里的知识点 ----------
        drv.execute_script("window.__req = [];")
        drv.execute_script("document.querySelector('#btnPreview').click();")
        time.sleep(2.0)
        reqs = drv.execute_script("return window.__req;")
        compose = [r for r in reqs if "ai-compose" in r["url"]]
        body = json.loads(compose[-1]["body"]) if compose and compose[-1]["body"] else {}
        kps = body.get("knowledge_point_ids")
        print("③ 预览请求 knowledge_point_ids = %s（应为已勾选的知识点 id）" % kps)

        # ---------- 对照组：全选 ----------
        drv.execute_script("window.__req = [];"
                           "document.querySelector('#kpToggleAll').click();")
        time.sleep(2.0)
        reqs = drv.execute_script("return window.__req;")
        pool2 = [r for r in reqs if "/papers/pool/" in r["url"]]
        print("④ 对照：「全选」后 /papers/pool/ 请求数 = %d" % len(pool2))
        if pool2:
            ids = [v for k, v in
                   [p.split("=", 1) for p in pool2[-1]["url"].split("?")[-1].split("&") if "=" in p]
                   if k == "knowledge_point_ids"]
            print("   全选请求携带 knowledge_point_ids 数量 = %d（说明接口本身支持按知识点过滤）"
                  % len(ids))

        print()
        if not pool and not kps and pool2:
            print("判定：BUG-03 成立。单个勾选因 `if (!event.target.dataset.kp) return;` 直接 return，")
            print("      `data-kp` 是无值属性 → dataset.kp 为 \"\"（falsy），条件恒成立。")
            print("      影响：教师按知识点组卷时，实际按整个学科抽题，且界面无任何提示。")
    finally:
        drv.quit()


if __name__ == "__main__":
    main()
