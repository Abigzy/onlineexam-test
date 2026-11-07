# -*- coding: utf-8 -*-
"""由 cases_data.py 同源生成三件产物：

    docs/03-测试用例.md
    docs/OnlineExam UI测试思维导图.xmind
    docs/OnlineExam UI测试思维导图-大纲.md

用法：python docs/assets/build_cases.py
纪律：任何条数/分布不符预期直接 AssertionError，不产出半成品。
"""
import hashlib
import json
import os
import sys
import zipfile
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cases_data import CASES  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.dirname(HERE)

MODULE_ORDER = [
    "01 认证与账号", "02 学生·考试闭环", "03 学生·学情练习", "04 学生·班级",
    "05 教师·题库与知识点", "06 教师·试卷与组卷", "07 教师·考试管理与监控",
    "08 教师·判分与成绩", "09 教师·学情与作弊", "10 管理端", "11 权限与可见性",
]
EXPECT_MODULE = {
    "01 认证与账号": (18, 4, 8, 6), "02 学生·考试闭环": (24, 8, 10, 6),
    "03 学生·学情练习": (14, 2, 8, 4), "04 学生·班级": (7, 1, 4, 2),
    "05 教师·题库与知识点": (21, 3, 11, 7), "06 教师·试卷与组卷": (15, 2, 8, 5),
    "07 教师·考试管理与监控": (13, 2, 7, 4), "08 教师·判分与成绩": (12, 2, 6, 4),
    "09 教师·学情与作弊": (8, 0, 4, 4), "10 管理端": (8, 2, 3, 3),
    "11 权限与可见性": (10, 2, 5, 3),
}
CHAIN_ORDER = ["S-1", "S-2", "S-3", "S-4", "S-5", "T-1", "T-2", "T-3",
               "T-4", "T-5", "T-6", "A-1", "A-2"]
CHAIN_NAME = {
    "S-1": "注册→登录→首页角色分流", "S-2": "我的考试→开考→作答→交卷→结果",
    "S-3": "答题页刷新不换题（断网续考）", "S-4": "错题本→我的学情→每日练习",
    "S-5": "班级可见性（本班/非本班）", "T-1": "题库新增→列表→编辑→停用",
    "T-2": "题库导入与导出", "T-3": "组卷：勾知识点→试算→生成→列表",
    "T-4": "教师建考试→学生端可见", "T-5": "判分→改分→定稿→成绩单",
    "T-6": "作弊看板→证据链", "A-1": "管理员建号→新号可登录", "A-2": "管理员代管教学功能",
}
PRI_ORDER = ["P0", "P1", "P2"]


# ---------------------------------------------------------------- 校验
def validate():
    assert len(CASES) == 150, "用例总数应为 150，实际 %d" % len(CASES)
    ids = [c["id"] for c in CASES]
    assert len(set(ids)) == len(ids), "存在重复用例编号"
    pri = Counter(c["pri"] for c in CASES)
    assert pri == {"P0": 28, "P1": 74, "P2": 48}, "优先级分布不符：%s" % pri
    assert sum(1 for c in CASES if c["smoke"]) == 15, "冒烟条数应为 15"
    for mod, (total, p0, p1, p2) in EXPECT_MODULE.items():
        got = [c for c in CASES if c["mod"] == mod]
        assert len(got) == total, "%s 条数 %d≠%d" % (mod, len(got), total)
        cnt = Counter(c["pri"] for c in got)
        assert (cnt["P0"], cnt["P1"], cnt["P2"]) == (p0, p1, p2), "%s 优先级分布不符 %s" % (mod, cnt)
    for c in CASES:
        assert c["steps"] and c["expect"], "%s 步骤/预期为空" % c["id"]
        if c["pri"] == "P0" and not c["smoke"]:
            pass
    # 13 条主链路必须都有用例
    for ch in CHAIN_ORDER:
        assert any(c["chain"] == ch for c in CASES), "主链路 %s 无用例覆盖" % ch


def layer_of(c):
    if c["smoke"]:
        return "L0 冒烟"
    if c["pri"] == "P2":
        return "L2 边界与交互"
    return "L1 主链路"


# ---------------------------------------------------------------- Markdown
def esc(t):
    return str(t).replace("|", "\\|")


def cell_list(items):
    if isinstance(items, str):
        return esc(items)
    if len(items) == 1:
        return esc(items[0])
    return "<br>".join("%d. %s" % (i + 1, esc(x)) for i, x in enumerate(items))


def build_md():
    pri = Counter(c["pri"] for c in CASES)
    typ = Counter(c["type"] for c in CASES)
    smoke = [c for c in CASES if c["smoke"]]

    L = []
    A = L.append
    A("# 步骤 3 · UI 自动化测试用例")
    A("")
    A("> 被测系统：《基于 Django 的 AI 在线考试与学情分析系统》（`OnlineExam`）")
    A("> 用例版本：**v1.0**（2026-11-03）　｜　**150 条**（P0 28 / P1 74 / P2 48）")
    A("> 依据：`02-测试计划与策略.md` §5 模块分配表、`01-需求分析与自动化可行性评估.md` §4 主链路")
    A("> 同源产物：`OnlineExam UI测试思维导图.xmind`（模块视图 / 分层视图 / 主链路追溯三个画布）")
    A("> 维护纪律：**只改用例数据源** `docs/assets/cases_data.py`，再执行 `python docs/assets/build_cases.py` 重新生成，")
    A("> 不要手改本文件或 xmind——三者条数由生成器断言保证一致。")
    A("")
    A("---")
    A("")
    A("## 0. 一页摘要")
    A("")
    A("| 项 | 内容 |")
    A("|---|---|")
    A("| 用例总数 | **150 条**（覆盖 26 条页面路由 / 11 个业务域） |")
    A("| 优先级 | P0 **28** / P1 **74** / P2 **48** |")
    A("| 分层 | L0 冒烟 **15** / L1 主链路 **87** / L2 边界与交互 **48** |")
    A("| 用例类型 | 功能 88 / 交互 26 / 校验 15 / 权限 12 / 数据一致性 5 / 异常 3 / 兼容性 1 |")
    A("| 主链路覆盖 | 13/13（S-1~S-5、T-1~T-6、A-1~A-2），每条 ≥1 条用例，S-2 最多 6 条 |")
    A("| 设计方法 | 场景法（主链路）+ 等价类/边界值（分页、题量、必填）+ 判定表（角色×状态×操作）+ 状态迁移（attempt 五态） |")
    A("| 数据策略 | 接口造数 + `UIAT_` 前缀 + 精确清理；仅 T-1/T-4/A-1 三条链路用 UI 真数据 |")
    A("")
    A("**一句话**：这套用例守的是「点了之后业务有没有按预期变化」，不是「页面能不能打开」——")
    A("后者已由 `UI走查清单` 的 251 个检查点覆盖，本套不重复。")
    A("")
    A("---")
    A("")
    A("## 1. 编号与字段约定")
    A("")
    A("**编号规则**：`UI-<模块缩写>-<序号>`，缩写与模块一一对应：")
    A("")
    A("| 缩写 | 模块 | 条数 | 缩写 | 模块 | 条数 |")
    A("|---|---|---|---|---|---|")
    pairs = [
        ("AUTH", "01 认证与账号"), ("EXAM", "02 学生·考试闭环"), ("STU", "03 学生·学情练习"),
        ("CLS", "04 学生·班级"), ("QB", "05 教师·题库与知识点"), ("PAP", "06 教师·试卷与组卷"),
        ("EXM", "07 教师·考试管理与监控"), ("GRD", "08 教师·判分与成绩"), ("ANA", "09 教师·学情与作弊"),
        ("ADM", "10 管理端"), ("SEC", "11 权限与可见性"),
    ]
    for i in range(0, len(pairs), 2):
        left = pairs[i]
        right = pairs[i + 1] if i + 1 < len(pairs) else ("", "")
        lt = str(len([c for c in CASES if c["mod"] == left[1]])) if left[0] else ""
        rt = str(len([c for c in CASES if c["mod"] == right[1]])) if right[0] else ""
        A("| `UI-%s` | %s | %s | %s | %s | %s |" % (
            left[0], left[1], lt,
            ("`UI-%s`" % right[0]) if right[0] else "", right[1] if right[0] else "", rt))
    A("")
    A("**优先级口径**（沿用测试计划 §7.2 的准出标准）：")
    A("")
    A("| 优先级 | 含义 | 执行时机 | 失败后果 |")
    A("|---|---|---|---|")
    A("| P0 | 主链路的「能通」与角色分流；15 条另打 `smoke` 标记进 L0 | 每次提交 | 阻断提测 |")
    A("| P1 | 主链路的细节正确性、数据一致性、跨页面状态流转 | 每次提测 | 阻断上线 |")
    A("| P2 | 边界、空态、校验文案、兼容性 | 版本级 | 可带风险上线 |")
    A("")
    A("**用例类型**：功能 / 交互 / 校验 / 权限 / 数据一致性 / 异常 / 兼容性。")
    A("")
    A("**步骤写法**：`#id` 表示元素 id 定位器，`.class` 表示 class 定位器，")
    A("`[data-xxx]` 表示属性定位器——这些都是步骤 4 要落进 PO 常量区的真实定位依据，不是示意。")
    A("")
    A("---")
    A("")
    A("## 2. 覆盖分析")
    A("")
    A("### 2.1 模块 × 优先级")
    A("")
    A("| # | 模块 | P0 | P1 | P2 | 小计 | 对应用例段 |")
    A("|---|---|---|---|---|---|---|")
    for idx, mod in enumerate(MODULE_ORDER, 1):
        got = [c for c in CASES if c["mod"] == mod]
        cnt = Counter(c["pri"] for c in got)
        A("| %d | %s | %d | %d | %d | **%d** | §3.%d |" % (
            idx, mod, cnt["P0"], cnt["P1"], cnt["P2"], len(got), idx))
    A("| | **合计** | **28** | **74** | **48** | **150** | |")
    A("")
    A("### 2.2 主链路追溯")
    A("")
    A("| 链路 | 说明 | 覆盖用例 | 条数 |")
    A("|---|---|---|---|")
    for ch in CHAIN_ORDER:
        got = [c for c in CASES if c["chain"] == ch]
        A("| %s | %s | %s | %d |" % (
            ch, CHAIN_NAME[ch], "<br>".join(c["id"] for c in got), len(got)))
    A("")
    A("### 2.3 与既有测试资产的重叠剔除")
    A("")
    A("| 易被重复覆盖的点 | 已有覆盖 | 本套处理 |")
    A("|---|---|---|")
    A("| 接口参数校验 / 状态码 | 接口自动化 229 条 | **不写**；只在「页面是否给出提示」层面写 15 条校验类用例 |")
    A("| 页面可达性 / 375px / 控制台 | UI 走查 251 检查点 | **不写**；只在 1280×800 保留 1 条兼容性用例 |")
    A("| 判分算法、掌握度公式 | 单测 1184 条 + 接口用例 | **不比数值**，只比「页面显示与自身汇总是否自洽」（如答对徽章数 = 汇总数） |")
    A("| 答案防泄漏字段 | 接口契约横切黑名单 | **不重复断言字段**，只在结果页写「未公开时不显示分数」1 条 |")
    A("")
    A("---")
    A("")
    A("## 3. 用例明细")
    A("")
    for idx, mod in enumerate(MODULE_ORDER, 1):
        got = [c for c in CASES if c["mod"] == mod]
        cnt = Counter(c["pri"] for c in got)
        A("### 3.%d %s（%d 条：P0 %d / P1 %d / P2 %d）" % (
            idx, mod, len(got), cnt["P0"], cnt["P1"], cnt["P2"]))
        A("")
        A("| 用例编号 | 所属模块 | 用例标题 | 前置条件 | 测试步骤 | 测试数据 | 预期结果 | 优先级 | 用例类型 |")
        A("|---|---|---|---|---|---|---|---|---|")
        for c in got:
            A("| %s | %s | %s | %s | %s | %s | %s | %s%s | %s |" % (
                c["id"], c["mod"], esc(c["title"]), esc(c["pre"]),
                cell_list(c["steps"]), esc(c["data"]), cell_list(c["expect"]),
                c["pri"], "·冒烟" if c["smoke"] else "", c["type"]))
        A("")
    A("---")
    A("")
    A("## 4. 数据准备清单")
    A("")
    A("> 原则：**接口造数、UI 校验**。造数脚本在步骤 5 落地为 `scripts/seed_ui_data.py`，")
    A("> 所有数据带 `UIAT_` 前缀或固定标题，`data/runtime.json` 记录实际 ID，清理阶段按清单精确删除。")
    A("")
    A("| # | 数据 | 数量 | 造法（接口） | 被哪些用例依赖 | 清理方式 |")
    A("|---|---|---|---|---|---|")
    rows = [
        ("1", "学生账号", "2（UIAT_STU_01/02）", "`POST /auth/register/`", "AUTH/EXAM/STU/CLS/SEC 共 60+ 条", "按用户名 DELETE"),
        ("2", "无学科学生 / 无错题学生", "各 1", "注册后不加班级", "STU-11 / STU-12", "按用户名 DELETE"),
        ("3", "教师账号（自建）", "1（UIAT_TEA_01）", "管理员建号接口", "CLS/QB/PAP/EXM 造数归属", "按用户名 DELETE"),
        ("4", "知识点", "1 树（父 1 + 子 2）", "`POST /knowledge-points/`", "QB-14/18/19、PAP-02", "DELETE 子树"),
        ("5", "题目", "6 题型各 1（UIAT题干<ts>）", "`POST /questions/`", "QB-02/04/08/09/10、PAP-06", "DELETE（软删）"),
        ("6", "试卷", "2（纯客观 / 含主观）", "`POST /papers/` + `random-compose`", "PAP-03/09/10/13、EXM-02", "DELETE"),
        ("7", "考试", "3（进行中 / 未开始 / 无作答）", "`POST /exams/`，时间窗 **+1h~+3h**", "EXAM-03~24、EXM-08~12、GRD-12", "DELETE"),
        ("8", "作答与成绩", "2（待批改 / 已批改）", "`POST /attempts/{id}/save/` + `finalize`", "GRD-03~06、EXAM-17/18、ANA-05", "DELETE attempt"),
        ("9", "班级", "2（本班 / 他班 UIAT_CLS_OTHER）", "`POST /classrooms/`", "CLS-02~07", "DELETE"),
        ("10", "导入夹具", "1 个 xlsx（2 行：1 合法 1 缺答案）", "仓库固定文件", "QB-13", "不清理（仓库资产）"),
        ("11", "学生行为埋点", "若干（切屏/粘贴）", "`POST /attempts/{id}/behavior/`", "ANA-04~07", "随 attempt 删除"),
    ]
    for r in rows:
        A("| %s | %s | %s | %s | %s | %s |" % r)
    A("")
    A("### 4.1 `data/runtime.json` 结构（步骤 5 落地）")
    A("")
    A("```json")
    A(json.dumps({
        "run_tag": "UIAT_20261103_2310",
        "base_url": "http://127.0.0.1:8931",
        "accounts": {"student": "UIAT_STU_01", "student2": "UIAT_STU_02",
                     "teacher_new": "UIAT_TEA_01", "password": "Exam@123456"},
        "ids": {"knowledge_points": [101, 102, 103], "questions": [9001, 9002],
                "paper_objective": 301, "paper_mixed": 302,
                "exam_ongoing": 401, "exam_future": 402, "exam_empty": 403,
                "attempt_pending": 501, "attempt_graded": 502,
                "classroom_mine": 601, "classroom_other": 602},
        "created_at": "2026-11-03T23:10:00+08:00"
    }, ensure_ascii=False, indent=2))
    A("```")
    A("")
    A("---")
    A("")
    A("## 5. 执行分组")
    A("")
    A("| 分组 | 选择方式 | 条数 | 用途 |")
    A("|---|---|---|---|")
    A("| L0 冒烟 | `pytest -m smoke` | 15 | 提交级，≤3 min，失败即阻断提测 |")
    A("| 回归 | `pytest -m \"p0 or p1\"` | 102 | 提测级，≤22 min |")
    A("| 全量 | `pytest` | 150 | 版本级，≤35 min，两轮一致才算准出 |")
    A("")
    A("**执行顺序**（同层内按此顺序，减少造数次数）：认证 → 权限 → 学生考试闭环 → 学生学情/班级 →")
    A("教师题库/组卷 → 考试管理与监控（跨角色 T-4 放最后）→ 判分成绩 → 学情作弊 → 管理端。")
    A("")
    A("---")
    A("")
    A("## 6. 与计划的偏差说明")
    A("")
    A("| 项 | 计划（02 §3.1） | 定稿（本文件） | 原因 |")
    A("|---|---|---|---|")
    A("| 分层条数 | L0 15 / L1 74 / L2 61 | L0 15 / L1 87 / L2 48 | 层与优先级是**两个维度**：13 条 P0 属主链路但不进冒烟，归 L1；L2 只装 P2。总数不变 |")
    A("| 用例总数 | 150（允许 ±10%） | 150 | 与计划一致，11 个模块的分配逐项对齐 |")
    A("")
    A("---")
    A("")
    A("## 7. 评审要点（步骤 3 的 Gate G1）")
    A("")
    A("1. **条数与分布**：150 条、P0 28 / P1 74 / P2 48、冒烟 15，与计划 §5 逐模块一致（生成器已断言）。")
    A("2. **可执行性**：每条步骤都落到具体 URL 与定位器；无「验证功能正常」这类不可执行描述。")
    A("3. **可判定性**：每条预期都是可观察事实（数量、class、文案、URL、可见性），无「界面友好」类主观表述。")
    A("4. **去重**：与接口自动化、UI 走查、单测的重叠已在 §2.3 逐项剔除。")
    A("5. **数据安全**：所有造数带 `UIAT_` 前缀，依赖清单与清理方式齐备（§4）。")
    A("6. **待确认**：UI-QB-13 的导入夹具需按真实模板生成；UI-EXAM-18 依赖 `show_score_immediately=false` 的考试配置，步骤 5 造数时需显式设置。")
    A("")
    md = "\n".join(L) + "\n"
    path = os.path.join(DOCS, "03-测试用例.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path, len(L)


# ---------------------------------------------------------------- Xmind 树
def tid(key):
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:16]


def topic(title, kids=None, key=""):
    t = {"id": tid(key or title), "class": "topic", "title": title}
    if kids:
        t["children"] = {"attached": kids}
    return t


def case_title(c):
    chain = (" [%s]" % c["chain"]) if c["chain"] else ""
    return "%s %s（%s·%s%s）" % (c["id"], c["title"], c["pri"], c["type"], chain)


def build_trees():
    # 画布 1：模块视图
    mod_kids = []
    for mod in MODULE_ORDER:
        got = [c for c in CASES if c["mod"] == mod]
        cnt = Counter(c["pri"] for c in got)
        title = "%s（%d 条：P0 %d / P1 %d / P2 %d）" % (mod, len(got), cnt["P0"], cnt["P1"], cnt["P2"])
        mod_kids.append(topic(title, [topic(case_title(c), key=c["id"]) for c in got], key="m-" + mod))
    root1 = topic("OnlineExam UI 自动化测试（150 条 · P0 28 / P1 74 / P2 48）", mod_kids, key="root-mod")

    # 画布 2：分层视图
    layer_kids = []
    for layer in ["L0 冒烟", "L1 主链路", "L2 边界与交互"]:
        got = [c for c in CASES if layer_of(c) == layer]
        sub = []
        for mod in MODULE_ORDER:
            gm = [c for c in got if c["mod"] == mod]
            if gm:
                sub.append(topic("%s（%d）" % (mod, len(gm)),
                                 [topic(case_title(c), key=c["id"]) for c in gm],
                                 key="l-%s-%s" % (layer, mod)))
        layer_kids.append(topic("%s（%d 条）" % (layer, len(got)), sub, key="l-" + layer))
    root2 = topic("分层执行视图（L0 15 / L1 87 / L2 48）", layer_kids, key="root-layer")

    # 画布 3：主链路追溯
    chain_kids = []
    for ch in CHAIN_ORDER:
        got = [c for c in CASES if c["chain"] == ch]
        chain_kids.append(topic("%s %s（%d 条）" % (ch, CHAIN_NAME[ch], len(got)),
                                [topic("%s %s（%s）" % (c["id"], c["title"], c["pri"]), key=c["id"]) for c in got],
                                key="c-" + ch))
    root3 = topic("13 条业务主链路追溯", chain_kids, key="root-chain")

    sheets = [
        {"id": "sheet-1", "class": "sheet", "title": "模块视图", "rootTopic": root1},
        {"id": "sheet-2", "class": "sheet", "title": "分层视图", "rootTopic": root2},
        {"id": "sheet-3", "class": "sheet", "title": "主链路追溯", "rootTopic": root3},
    ]
    return sheets


def xml_topic(t):
    s = '<topic id="%s"><title>%s</title>' % (t["id"], xml_esc(t["title"]))
    kids = t.get("children", {}).get("attached")
    if kids:
        s += "<children><topics type=\"attached\">" + "".join(xml_topic(k) for k in kids) + "</topics></children>"
    return s + "</topic>"


def xml_esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def build_xmind(sheets):
    path = os.path.join(DOCS, "OnlineExam UI测试思维导图.xmind")
    content = json.dumps(sheets, ensure_ascii=False, separators=(",", ":"))
    metadata = json.dumps({"creator": {"name": "XMind", "version": "24.04"},
                           "activeSheetId": "sheet-1"}, ensure_ascii=False)
    manifest = json.dumps({"file-entries": {"content.json": {}, "content.xml": {},
                                            "metadata.json": {}}}, ensure_ascii=False)
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
           '<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" version="2.0">'
           + "".join('<sheet id="%s">%s</sheet>' % (s["id"], xml_topic(s["rootTopic"])) for s in sheets)
           + "</xmap-content>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", content)
        z.writestr("content.xml", xml)
        z.writestr("metadata.json", metadata)
        z.writestr("manifest.json", manifest)
    return path


# ---------------------------------------------------------------- 大纲
def build_outline():
    L = []
    A = L.append
    A("# OnlineExam UI 测试思维导图 · 大纲（同源）")
    A("")
    A("> 与 `OnlineExam UI测试思维导图.xmind`、`03-测试用例.md` 同源（`docs/assets/cases_data.py`）。")
    A("> 本文件用于代码评审 / 检索，容量比 xmind 更友好。")
    A("")
    A("## 一、模块视图")
    A("")
    for mod in MODULE_ORDER:
        got = [c for c in CASES if c["mod"] == mod]
        cnt = Counter(c["pri"] for c in got)
        A("- **%s**（%d 条：P0 %d / P1 %d / P2 %d）" % (mod, len(got), cnt["P0"], cnt["P1"], cnt["P2"]))
        for c in got:
            tag = ""
            if c["smoke"]:
                tag += " `L0`"
            if c["chain"]:
                tag += " `%s`" % c["chain"]
            A("  - %s %s（%s·%s）%s" % (c["id"], c["title"], c["pri"], c["type"], tag))
    A("")
    A("## 二、分层视图")
    A("")
    for layer in ["L0 冒烟", "L1 主链路", "L2 边界与交互"]:
        got = [c for c in CASES if layer_of(c) == layer]
        A("- **%s**（%d 条）" % (layer, len(got)))
        for mod in MODULE_ORDER:
            gm = [c for c in got if c["mod"] == mod]
            if not gm:
                continue
            A("  - %s（%d）：%s" % (mod, len(gm), "、".join(c["id"] for c in gm)))
    A("")
    A("## 三、主链路追溯")
    A("")
    for ch in CHAIN_ORDER:
        got = [c for c in CASES if c["chain"] == ch]
        A("- **%s %s**（%d 条）：%s" % (ch, CHAIN_NAME[ch], len(got),
                                        "、".join(c["id"] for c in got)))
    path = os.path.join(DOCS, "OnlineExam UI测试思维导图-大纲.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


if __name__ == "__main__":
    validate()
    md, lines = build_md()
    xm = build_xmind(build_trees())
    ol = build_outline()
    print("用例总数      : %d" % len(CASES))
    print("优先级分布    : P0 %d / P1 %d / P2 %d" % (
        sum(1 for c in CASES if c["pri"] == "P0"),
        sum(1 for c in CASES if c["pri"] == "P1"),
        sum(1 for c in CASES if c["pri"] == "P2")))
    print("冒烟（L0）    : %d" % sum(1 for c in CASES if c["smoke"]))
    print("分层          : L0 %d / L1 %d / L2 %d" % tuple(
        sum(1 for c in CASES if layer_of(c) == l) for l in ["L0 冒烟", "L1 主链路", "L2 边界与交互"]))
    print("Markdown      : %s（%d 行）" % (md, lines))
    print("Xmind         : %s" % xm)
    print("大纲          : %s" % ol)
