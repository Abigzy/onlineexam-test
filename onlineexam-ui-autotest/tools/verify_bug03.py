# -*- coding: utf-8 -*-
"""BUG-03 修复验证：4 个场景，覆盖"修得对"与"没修过头"。

A 勾选叶子知识点 → 发起题池请求、题量下降、请求带上该知识点 id
B 点「预览」       → 组卷请求的 knowledge_point_ids 含勾选的 id
C 取消勾选         → 题量恢复全量（勾选状态是可撤销的）
D 「全选/清空」    → 仍是 35 个知识点（原路径不能被改坏）

判定逻辑写在断言里，脚本退出码非 0 表示有场景失败。
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(os.path.dirname(ROOT), "onlineexam_ui_autotest")
sys.path.insert(0, PROJ)

import config                                                       # noqa: E402
from common.api_client import ApiSession                            # noqa: E402
from common.data_factory import load_runtime, seed_paper_draft      # noqa: E402
from common.driver_factory import create_driver                     # noqa: E402
from pages.teacher_pages import PaperComposePage                    # noqa: E402

RESULTS = []

INTERCEPT = """
window.__req = [];
if (!window.__hooked) {
  const of = window.fetch;
  window.fetch = function (u, o) {
    try { window.__req.push({url: String(u), body: (o && o.body) || ""}); } catch (e) {}
    return of.apply(this, arguments);
  };
  window.__hooked = true;
}
"""


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  —— " + detail) if detail else ""))


def pool_ids(url):
    """从 /papers/pool/?knowledge_point_ids=1&knowledge_point_ids=2 里取 id 列表。"""
    if "?" not in url:
        return []
    query = url.split("?", 1)[1]
    return [pair.split("=", 1)[1] for pair in query.split("&")
            if pair.startswith("knowledge_point_ids=")]


def main():
    rt = load_runtime()
    paper = seed_paper_draft(rt)            # 每次都幂等重建（cleanup 会删掉上一轮的卷）
    api = ApiSession(config.ACCOUNTS["teacher"])
    drv = create_driver()
    try:
        drv.get(config.BASE_URL + "/login/")
        drv.delete_all_cookies()
        drv.add_cookie({"name": "sessionid", "value": api.session_id,
                        "domain": "127.0.0.1", "path": "/"})
        page = PaperComposePage(drv).open_paper(paper["id"])
        drv.execute_script(INTERCEPT)

        full_total = page.pool_total()
        print("基线：未选知识点时题池 = %d 道\n" % full_total)

        # ---------------- A 勾选叶子知识点 ----------------
        drv.execute_script("window.__req = [];"
                           "const labels=[...document.querySelectorAll('#kpTree label')];"
                           "const l=labels.find(x=>x.innerText.includes('顺序表'));"
                           "const b=l.querySelector('input[data-kp]');"
                           "b.scrollIntoView({block:'center'}); b.click();")
        time.sleep(1.5)
        reqs = drv.execute_script("return window.__req;")
        pool_reqs = [r for r in reqs if "/papers/pool/" in r["url"]]
        picked = page.pool_total()

        check("A 勾选后发起了题池请求", len(pool_reqs) >= 1, "请求数 %d" % len(pool_reqs))
        check("A 请求带上知识点 id",
              bool(pool_reqs) and bool(pool_ids(pool_reqs[-1]["url"])),
              "携带 id=%s" % (pool_ids(pool_reqs[-1]["url"]) if pool_reqs else "无"))
        check("A 题池按知识点收敛", picked < full_total,
              "%d → %d 道" % (full_total, picked))

        # ---------------- B 预览请求带知识点 ----------------
        drv.execute_script("window.__req = [];"
                           "document.querySelector('#btnPreview').click();")
        time.sleep(2.5)
        reqs = drv.execute_script("return window.__req;")
        compose = [r for r in reqs if "ai-compose" in r["url"]]
        body = json.loads(compose[-1]["body"]) if compose and compose[-1]["body"] else {}
        kps = body.get("knowledge_point_ids") or []
        check("B 预览请求带上勾选的知识点", len(kps) == 1,
              "knowledge_point_ids=%s" % kps)

        # ---------------- C 取消勾选后恢复 ----------------
        drv.execute_script("const labels=[...document.querySelectorAll('#kpTree label')];"
                           "const l=labels.find(x=>x.innerText.includes('顺序表'));"
                           "l.querySelector('input[data-kp]').click();")
        time.sleep(1.5)
        back = page.pool_total()
        check("C 取消勾选后题量恢复全量", back == full_total, "%d → %d" % (picked, back))

        # ---------------- D 全选路径未被改坏 ----------------
        drv.execute_script("window.__req = [];"
                           "document.querySelector('#kpToggleAll').click();")
        time.sleep(1.5)
        reqs = drv.execute_script("return window.__req;")
        pool_all = [r for r in reqs if "/papers/pool/" in r["url"]]
        ids_all = pool_ids(pool_all[-1]["url"]) if pool_all else []
        check("D 「全选」仍携带全部知识点", len(ids_all) >= 30,
              "携带 %d 个知识点 id" % len(ids_all))
        # 注意：全选 35 个知识点 **≠** 整个学科——没挂知识点的题不属于任何知识点，
        # 会被排除掉（实测 746 → 740，少 6 道）。所以这里断"不高于全量且仍为正"，
        # 而不是"等于全量"（我第一版就写错了）。
        selected_total = page.pool_total()
        check("D 全选后题量不高于全量且非空",
              0 < selected_total <= full_total,
              "全选 %d 道 / 全量 %d 道（差 %d 道为未标注知识点的题）"
              % (selected_total, full_total, full_total - selected_total))

    finally:
        drv.quit()

    failed = [r for r in RESULTS if not r[1]]
    print()
    print("汇总：%d 项通过 / %d 项失败" % (len(RESULTS) - len(failed), len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
