# -*- coding: utf-8 -*-
"""从 04-测试用例.md 生成 OnlineExam接口测试思维导图.xmind。

同时写入 content.json（XMind 2020+）与 content.xml（XMind 8 兼容），
两个版本在同一 zip 内，任一版本打开都能看到同样的树。
"""
import json
import re
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "04-测试用例.md"
OUT = BASE / "OnlineExam接口测试思维导图.xmind"
MD_OUT = BASE / "OnlineExam接口测试思维导图-大纲.md"

MODULE_NAMES = {
    "GEN": "01 通用契约",
    "AUTH": "02 认证",
    "USER": "03 用户管理",
    "AI": "04 AI 适配层",
    "KP": "05 知识点",
    "QUES": "06 题库",
    "PAPER": "07 试卷与组卷",
    "EXAM": "08 考试配置",
    "ATT": "09 作答",
    "GRAD": "10 判分与成绩",
    "AN": "11 学情分析",
    "REC": "12 个性化推荐",
    "PRO": "13 作弊检测",
    "CLS": "14 班级管理",
    "SYS": "15 管理端",
}
ORDER = list(MODULE_NAMES)
POSITIVE_TYPES = {"功能", "一致性", "幂等", "可复现"}


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def parse_cases():
    cases = []
    for line in SRC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| API-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 9:
            continue
        cid, module, title, _, _, _, _, priority, ctype = cells
        abbr = cid.split("-")[1]
        cases.append({
            "id": cid,
            "abbr": abbr,
            "module": module,
            "title": title,
            "priority": priority,
            "type": ctype,
            "positive": ctype in POSITIVE_TYPES,
        })
    return cases


def group(cases, positive):
    buckets = {}
    for c in cases:
        if c["positive"] != positive:
            continue
        buckets.setdefault(c["abbr"], []).append(c)
    return [(abbr, buckets[abbr]) for abbr in ORDER if abbr in buckets]


def json_topic(title, children=None):
    node = {"id": new_id(), "class": "topic", "title": title}
    if children:
        node["children"] = {"attached": children}
    return node


def build_json(cases):
    pos = group(cases, True)
    neg = group(cases, False)

    def branch(name, groups):
        mods = []
        for abbr, items in groups:
            leaves = [
                json_topic(f"{c['id']} {c['title']}（{c['priority']}·{c['type']}）")
                for c in items
            ]
            mods.append(json_topic(f"{MODULE_NAMES[abbr]}（{len(items)}）", leaves))
        return json_topic(f"{name}（{sum(len(i) for _, i in groups)}）", mods)

    notes = json_topic("统计与约定", [
        json_topic(f"用例总数 {len(cases)} 条"),
        json_topic(f"正向 {sum(1 for c in cases if c['positive'])} / 反向 {sum(1 for c in cases if not c['positive'])}"),
        json_topic("P0 158 / P1 91 / P2 15"),
        json_topic("断言：HTTP 状态 + code 双断言，禁止 500"),
        json_topic("数据：at_ 前缀，只软删/归档/停用"),
        json_topic("时间：改 deadline_at 造超时，不 sleep"),
        json_topic("AI：默认 mock/降级，不真实联网"),
        json_topic("冒烟：33 条 P0，目标 5 分钟"),
    ])

    root = json_topic("OnlineExam 接口自动化测试（124 接口 / %d 用例）" % len(cases), [
        branch("正向", pos),
        branch("反向", neg),
        notes,
    ])
    root["structureClass"] = "org.xmind.ui.logic.right"

    sheet = {
        "id": "sheet-1",
        "class": "sheet",
        "title": "OnlineExam 接口测试",
        "rootTopic": root,
        "topicPositioning": "fixed",
    }
    return [sheet]


def xml_topic(node):
    children = node.get("children", {}).get("attached", [])
    inner = "".join(xml_topic(c) for c in children)
    kids = f'<children><topics type="attached">{inner}</topics></children>' if children else ""
    return (
        f'<topic id="{node["id"]}"><title>{escape(node["title"])}</title>{kids}</topic>'
    )


def build_xml(sheet):
    root = dict(sheet["rootTopic"])
    root_xml = xml_topic(root).replace(
        "<topic id=", '<topic structure-class="org.xmind.ui.logic.right" id=', 1
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        '<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" version="2.0">'
        '<sheet id="sheet-1">'
        f'{root_xml}'
        '<title>OnlineExam 接口测试</title>'
        '</sheet></xmap-content>'
    )


def build_markdown(cases):
    lines = ["# OnlineExam 接口测试思维导图（大纲版）", "",
             f"> 与 `OnlineExam接口测试思维导图.xmind` 同源；共 {len(cases)} 条用例。", ""]
    for name, positive in (("正向", True), ("反向", False)):
        groups = group(cases, positive)
        lines.append(f"## {name}（{sum(len(i) for _, i in groups)}）")
        lines.append("")
        for abbr, items in groups:
            lines.append(f"### {MODULE_NAMES[abbr]}（{len(items)}）")
            lines.append("")
            for c in items:
                lines.append(f"- {c['id']} {c['title']}（{c['priority']}·{c['type']}）")
            lines.append("")
    return "\n".join(lines)


def main():
    cases = parse_cases()
    if not cases:
        raise SystemExit("未解析到用例，检查 04-测试用例.md")

    sheets = build_json(cases)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", json.dumps(sheets, ensure_ascii=False))
        z.writestr("content.xml", build_xml(sheets[0]))
        z.writestr("metadata.json", json.dumps({
            "creator": {"name": "XMind", "version": "24.04"},
            "activeSheetId": "sheet-1",
        }, ensure_ascii=False))
        z.writestr("manifest.json", json.dumps({
            "file-entries": {
                "content.json": {},
                "content.xml": {},
                "metadata.json": {},
            }
        }, ensure_ascii=False))

    MD_OUT.write_text(build_markdown(cases), encoding="utf-8")
    pos = sum(1 for c in cases if c["positive"])
    print(f"cases={len(cases)} positive={pos} negative={len(cases)-pos}")
    print(f"xmind={OUT} ({OUT.stat().st_size} bytes)")
    print(f"outline={MD_OUT}")


if __name__ == "__main__":
    main()
