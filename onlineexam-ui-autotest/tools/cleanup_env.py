# -*- coding: utf-8 -*-
"""清理中间产物（可重复执行，幂等）。

清什么：
    - `log/*.log`：只留最近 5 个（失败现场要看最新的，老日志只会占地方）
    - `report/screenshots/*.png`：只留最近 20 张
    - `data/downloads/*`：导出/模板下载的落盘文件，留一个都嫌多
    - `runtime.json` 的 ids：清空，下一轮 seed 强制重建（避免指向已删记录）

**不清什么（重要）**：
    - 题库里 `UIAT` 前缀的题：服务端删除是**软删**，而且其中 288/292 条已被试卷引用，
      硬删会破坏试卷与成绩的可追溯性。它们留在库里是测试数据的自然沉淀，不是垃圾；
    - 已归档的考试/试卷：业务规则要求保留（审计），每轮 cleanup 已经处理过；
    - `.cache/chrome-profile`：保住磁盘缓存，全量能省 5 分钟以上。

用法：
    python tools/cleanup_env.py            # 只看不动
    python tools/cleanup_env.py --apply    # 真的删
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(os.path.dirname(ROOT), "onlineexam_ui_autotest")
sys.path.insert(0, PROJ)

import config                                                       # noqa: E402

KEEP_LOGS = 5
KEEP_SHOTS = 20


def _sorted_by_mtime(pattern):
    return sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)


def _size_of(paths):
    total = 0
    for p in paths:
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    return total


def main(apply=False):
    plan = []

    logs = _sorted_by_mtime(os.path.join(config.LOG_DIR, "*.log"))
    plan.append(("日志（保留最近 %d 个）" % KEEP_LOGS, logs[KEEP_LOGS:]))

    shots = _sorted_by_mtime(os.path.join(config.SCREENSHOT_DIR, "*.png"))
    plan.append(("报告截图（保留最近 %d 张）" % KEEP_SHOTS, shots[KEEP_SHOTS:]))

    downloads = glob.glob(os.path.join(config.DATA_DIR, "downloads", "*"))
    plan.append(("下载产物", downloads))

    total_files = 0
    total_bytes = 0
    for label, paths in plan:
        size = _size_of(paths)
        total_files += len(paths)
        total_bytes += size
        print("%-26s %4d 个 / %7.2f MB" % (label, len(paths), size / 1048576))
        if apply:
            for p in paths:
                try:
                    os.remove(p)
                except OSError as exc:
                    print("   删除失败 %s：%s" % (p, exc))

    print("-" * 52)
    print("合计可清理：%d 个文件 / %.2f MB" % (total_files, total_bytes / 1048576))

    if apply:
        # 清空 runtime 的 ids：这些记录本轮已被 cleanup 归档/删除，
        # 留着只会让下一轮 seed 误以为"还能复用"（踩过）。
        try:
            with open(config.RUNTIME_JSON, encoding="utf-8") as f:
                rt = json.load(f)
            rt["ids"] = {}
            rt["titles"] = {}
            rt["cleaned_at"] = "manual-cleanup"
            with open(config.RUNTIME_JSON, "w", encoding="utf-8") as f:
                json.dump(rt, f, ensure_ascii=False, indent=2)
            print("runtime.json：已清空 ids / titles（保留 bank 造数引用）")
        except (FileNotFoundError, ValueError) as exc:
            print("runtime.json 跳过：%s" % exc)
        print("\n已执行清理。")
    else:
        print("\n这是预演（dry-run）。加 --apply 才会真的删除。")

    print()
    print("说明：题库里 UIAT 前缀的题**不清理**——服务端只做软删，且多数已被试卷引用，")
    print("      硬删会破坏试卷/成绩的可追溯性；已归档的考试与试卷同样按业务规则保留。")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
