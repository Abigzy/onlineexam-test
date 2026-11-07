# -*- coding: utf-8 -*-
"""造数与清理：所有 UI 用例依赖的数据都从这里来。

约定（docs/03 §4）：
    - 一切数据带 UIAT_ 前缀 + 运行标签，标题可检索、可精确清理；
    - 考试时间窗一律 **-5min ~ +3h**（接口自动化踩过 +60min 造数一小时后就过期的坑）；
    - 造数用 admin 会话：教师建的「面向全体」只覆盖自己可管理班级（FR-6-10），
      admin 建的才是全校可见，避免用例因为权限作用域而"看不到考试"；
    - 试卷是**题型确定**的（单选/多选/填空/简答各 1 题）：随机组卷无法保证题型覆盖，
      会让"多选能多选""填空有 textarea"这类断言变成碰运气。

四场考试各司其职：
    exam_ongoing    进行中，max_attempts=10 —— 绝大多数作答类用例共用
    exam_future     未开始 —— 卡片禁用态
    exam_exhausted  进行中但作答次数用尽（已有 1 次已交卷作答）—— 禁用态 + 结果页
    exam_hidden     已交卷但 show_score_immediately=False —— 成绩未公开态
"""
import json
import os
from datetime import datetime, timedelta, timezone

import config
from common.api_client import ApiError, ApiSession
from common.logger import get

log = get("data")

TZ = timezone(timedelta(hours=8))

# 题型确定的题目；题干统一以「UIAT 」开头，既方便断言也方便兜底清理
QUESTIONS = [
    {
        "type": "single",
        "stem": "UIAT 单选：1 + 1 等于几？",
        "difficulty": 1, "score": 2, "reference_answer": "B",
        "analysis": "基础算术：1 + 1 = 2。",
        "options": [{"label": "A", "content": "1"}, {"label": "B", "content": "2", "is_correct": True},
                    {"label": "C", "content": "3"}, {"label": "D", "content": "4"}],
    },
    {
        "type": "multiple",
        "stem": "UIAT 多选：下列哪些是偶数？",
        "difficulty": 2, "score": 3, "reference_answer": "BD",
        "analysis": "2 和 4 是偶数。",
        "options": [{"label": "A", "content": "1"}, {"label": "B", "content": "2", "is_correct": True},
                    {"label": "C", "content": "3"}, {"label": "D", "content": "4", "is_correct": True}],
    },
    {
        "type": "fill",
        "stem": "UIAT 填空：栈是一种 ____ 的线性表。",
        "difficulty": 2, "score": 2, "reference_answer": "后进先出",
        "analysis": "栈遵循后进先出（LIFO）。",
    },
    {
        "type": "short",
        "stem": "UIAT 简答：简述进程与线程的主要区别。",
        "difficulty": 3, "score": 5,
        "reference_answer": "进程是资源分配的基本单位，线程是 CPU 调度的基本单位；"
                            "同一进程内的线程共享地址空间。",
        "analysis": "从资源分配与调度两个角度回答即可。",
    },
]


def _now():
    return datetime.now(TZ)


def load_runtime():
    try:
        with open(config.RUNTIME_JSON, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def save_runtime(rt):
    with open(config.RUNTIME_JSON, "w", encoding="utf-8") as f:
        json.dump(rt, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 造数
def _create_questions(api, subject="数据结构"):
    """造题。

    `subject` 必须落在教师的学科域内：整套造数（题/卷/考试）都由 **teacher** 建，
    否则教师列表与监控页看不到自己"该看"的数据，用例会一片「找不到」。
    """
    ids = []
    for q in QUESTIONS:
        data = api.post("/questions/", json=dict(q, subject=subject, source="manual"))
        ids.append((data.get("question") or data)["id"])
    return ids


def _create_paper(api, question_ids, title, subject="数据结构"):
    data = api.post("/papers/", json={
        "title": title, "subject": subject, "duration_minutes": 30,
        "pass_score": 6,                 # 12 分卷：及格线 6；不传会用默认 60 直接 400
        "question_ids": question_ids,
    })
    pid = (data.get("paper") or data)["id"]
    api.post("/papers/%s/status/" % pid, json={"status": "published"})
    return pid


def _create_exam(adm, paper_id, title, start, end, attempts=10, show_score=True):
    data = adm.post("/exams/", json={
        "title": title, "paper_id": paper_id,
        "start_time": start.isoformat(), "end_time": end.isoformat(),
        "duration_minutes": 30, "open_to_all": True,
        "show_score_immediately": show_score,
        "max_attempts": attempts,
        "shuffle_questions": False,          # 题序固定，才能断言"刷新不换题"
        "shuffle_options": False,
    })
    eid = (data.get("exam") or data)["id"]
    adm.post("/exams/%s/status/" % eid, json={"status": "published"})
    return eid


def _student_attempt(student, exam_id):
    """学生开考，返回（attempt_id, 题目列表）。"""
    data = student.post("/exams/%s/start/" % exam_id, json={"confirm": True})
    attempt = data.get("attempt") or data
    aid = attempt["id"]
    state = student.get("/attempts/%s/paper/" % aid)
    return aid, (state.get("questions") or [])


def _submit(student, aid, questions, correct_labels=None):
    """交卷；correct_labels: {paper_question_id: "B"}，未给出的题留空。"""
    items = []
    for q in questions:
        pq = q.get("paper_question_id")
        items.append({
            "paper_question_id": pq,
            "selected_labels": (correct_labels or {}).get(pq, ""),
            "answer_text": "",
            "is_flagged": False,
            "time_spent_seconds": 3,
        })
    student.post("/attempts/%s/submit/" % aid, json={"reason": "manual", "items": items})


def seed(force=False):
    """造一套 UI 用例数据；已存在且仍然有效则复用。"""
    rt = load_runtime()
    adm = ApiSession(config.ACCOUNTS["admin"])

    if not force and rt.get("ids", {}).get("exam_ongoing") and rt["ids"].get("paper"):
        try:
            exam = adm.get("/exams/%s/" % rt["ids"]["exam_ongoing"])
            paper = adm.get("/papers/%s/" % rt["ids"]["paper"])
            # 试卷必须仍然「可被引用」：上一轮清理会把它归档，此时旧 runtime 已失效，
            # 复用会让 new_exam 全部 400「试卷不存在或已归档」——踩过一次。
            if ((exam.get("is_open") or exam.get("computed_status") in ("published", "ongoing"))
                    and paper.get("status") != "archived"):
                log.info("复用已有造数（exam=%s paper=%s）", exam.get("id"), rt["ids"].get("paper"))
                return rt
            log.info("旧造数的试卷已归档，重新造数")
        except Exception as exc:                            # noqa: BLE001
            log.warning("旧造数不可用（%s），重新造", exc)

    log.info("开始造数，运行标签 %s", config.RUN_TAG)
    # 全部造数走 **teacher**：教师只能看到自己建的题/卷/考试，
    # 用 admin 造会让"教师新建→列表查找""监控页概览"整条链断掉（踩过）。
    teacher_api = ApiSession(config.ACCOUNTS["teacher"])
    student = ApiSession(config.ACCOUNTS["student"])
    now = _now()

    # 1) 题型确定：4 道题 -> 1 份卷 -> 发布
    qids = _create_questions(teacher_api)
    pid = _create_paper(teacher_api, qids, config.tag("题型完整卷"))
    log.info("试卷 %s 已发布（%d 题：单选/多选/填空/简答）", pid, len(qids))

    # 2) 四场考试
    e_ongoing = _create_exam(teacher_api, pid, config.tag("考试_进行中"),
                             now - timedelta(minutes=5), now + timedelta(hours=3), attempts=10)
    e_future = _create_exam(teacher_api, pid, config.tag("考试_未开始"),
                            now + timedelta(hours=6), now + timedelta(hours=8))
    e_exhausted = _create_exam(teacher_api, pid, config.tag("考试_次数用尽"),
                               now - timedelta(minutes=5), now + timedelta(hours=3), attempts=1)
    e_hidden = _create_exam(teacher_api, pid, config.tag("考试_成绩未公开"),
                            now - timedelta(minutes=5), now + timedelta(hours=3),
                            attempts=1, show_score=False)

    # 3) 两场「已交卷」：一场单选答对（结果页统计用），一场成绩未公开
    aid_exhausted, qs = _student_attempt(student, e_exhausted)
    single_pq = next((q["paper_question_id"] for q in qs if q.get("question_type") == "single"), None)
    _submit(student, aid_exhausted, qs, {single_pq: "B"} if single_pq else {})

    aid_hidden, qs2 = _student_attempt(student, e_hidden)
    _submit(student, aid_hidden, qs2, {})

    # 4) 判客观题 + 出分：结果页要验「逐题对错徽章」，必须先有判分结果
    teacher = ApiSession(config.ACCOUNTS["teacher"])
    try:
        # 已出分：判客观题 + 出分（结果页才有逐题对错与分数）
        teacher.post("/grading/attempts/%s/grade/" % aid_exhausted, json={"with_ai": False})
        teacher.post("/grading/attempts/%s/finalize/" % aid_exhausted, json={})
    except Exception as exc:                                # noqa: BLE001
        log.warning("作答 %s 判分/出分失败：%s", aid_exhausted, exc)
    try:
        # 成绩未公开：只判客观题（auto_graded），**不出分**——finalize 等于公开，学生恒可见
        teacher.post("/grading/attempts/%s/grade/" % aid_hidden, json={"with_ai": False})
    except Exception as exc:                                # noqa: BLE001
        log.warning("作答 %s 判分失败：%s", aid_hidden, exc)

    rt = {
        "run_tag": config.RUN_TAG,
        "base_url": config.BASE_URL,
        "created_at": now.isoformat(),
        "ids": {
            "paper": pid,
            "questions": qids,
            "exam_ongoing": e_ongoing,
            "exam_future": e_future,
            "exam_exhausted": e_exhausted,
            "exam_hidden": e_hidden,
            "attempt_exhausted": aid_exhausted,
            "attempt_hidden": aid_hidden,
        },
        "titles": {k: config.tag(v) for k, v in {
            "paper": "题型完整卷", "exam_ongoing": "考试_进行中", "exam_future": "考试_未开始",
            "exam_exhausted": "考试_次数用尽", "exam_hidden": "考试_成绩未公开"}.items()},
    }
    save_runtime(rt)
    log.info("造数完成：paper=%s ongoing=%s future=%s exhausted=%s hidden=%s",
             pid, e_ongoing, e_future, e_exhausted, e_hidden)
    return rt


# ---------------------------------------------------------------- 题库造数
# 题库按「教师学科域」过滤，所以这批题必须用 teacher 账号建（admin 建的可能不在其域内）。
# 关键约束：题目删除是**软删**（is_active=False，记录永留），所以不能靠"每轮重建"，
# 只能按题干精确复用；被停用过的题在下一轮造数时恢复成启用态，避免题量无限增长。
BANK_PREFIX = "UIAT 题库"
BANK_QUESTIONS = [
    {
        "key": "single", "type": "single", "difficulty": 1, "score": 2,
        "stem": "UIAT 题库单选：HTTP 状态码 404 表示什么？",
        "analysis": "404 表示资源未找到。",
        "options": [{"label": "A", "content": "服务器内部错误"},
                    {"label": "B", "content": "资源未找到", "is_correct": True},
                    {"label": "C", "content": "永久重定向"},
                    {"label": "D", "content": "请求超时"}],
    },
    {
        "key": "multiple", "type": "multiple", "difficulty": 3, "score": 3,
        "stem": "UIAT 题库多选：下列哪些属于关系型数据库？",
        "analysis": "MySQL 与 PostgreSQL 是关系型；Redis 与 MongoDB 不是。",
        "options": [{"label": "A", "content": "MySQL", "is_correct": True},
                    {"label": "B", "content": "Redis"},
                    {"label": "C", "content": "PostgreSQL", "is_correct": True},
                    {"label": "D", "content": "MongoDB"}],
    },
    {
        "key": "judge", "type": "judge", "difficulty": 2, "score": 1,
        "stem": "UIAT 题库判断：TCP 是面向连接的传输层协议。",
        "analysis": "TCP 三次握手建立连接，属于面向连接协议。",
        "options": [{"label": "A", "content": "正确", "is_correct": True},
                    {"label": "B", "content": "错误"}],
    },
    {
        "key": "fill", "type": "fill", "difficulty": 2, "score": 2,
        "stem": "UIAT 题库填空：DNS 的主要作用是把域名解析为 ____。",
        "analysis": "解析为 IP 地址。", "reference_answer": "IP 地址",
    },
    {
        "key": "disable", "type": "single", "difficulty": 1, "score": 2,
        "stem": "UIAT 题库待停用：这条题用于验证停用流程。",
        "analysis": "仅用于 UI 停用用例，每轮造数会恢复为启用态。",
        "options": [{"label": "A", "content": "选项一", "is_correct": True},
                    {"label": "B", "content": "选项二"},
                    {"label": "C", "content": "选项三"},
                    {"label": "D", "content": "选项四"}],
    },
]


def seed_bank(rt=None, recreate_dead=True):
    """题库用例的造数：5 道题（覆盖 4 种题型 + 1 道停用靶子）。

    recreate_dead=True 时，把被停用的靶子题恢复成启用态——停用是软删，
    不恢复的话「点停用 → 状态变已停用」这条用例第二轮就没得可停。
    """
    rt = rt or load_runtime()
    teacher = ApiSession(config.ACCOUNTS["teacher"])
    subject = "数据结构"                      # teacher 账号的学科域（实测只有这一个）

    found = {}
    try:
        data = teacher.get("/questions/", params={"keyword": BANK_PREFIX, "page_size": 100})
        for q in data.get("results") or []:
            for spec in BANK_QUESTIONS:
                if q.get("stem") == spec["stem"]:
                    found.setdefault(spec["key"], q)
    except Exception as exc:                                # noqa: BLE001
        log.warning("查询已有题库造数失败：%s", exc)

    ids, created = {}, 0
    for spec in BANK_QUESTIONS:
        q = found.get(spec["key"])
        if q:
            ids[spec["key"]] = q["id"]
            if recreate_dead and not q.get("is_active"):
                try:
                    teacher.patch("/questions/%s/" % q["id"], json={"is_active": True})
                    log.info("题库造数 %s（id=%s）已恢复启用", spec["key"], q["id"])
                except Exception as exc:                    # noqa: BLE001
                    log.warning("恢复题目 %s 失败：%s", q["id"], exc)
            continue
        payload = {k: v for k, v in spec.items() if k != "key"}
        payload["subject"] = subject
        try:
            new = teacher.post("/questions/", json=payload)
            ids[spec["key"]] = new["id"]
            created += 1
        except Exception as exc:                            # noqa: BLE001
            log.error("创建题库造数 %s 失败：%s", spec["key"], exc)

    bank = {"ids": ids, "keyword": BANK_PREFIX,
            "stems": {s["key"]: s["stem"] for s in BANK_QUESTIONS},
            "subject": subject}
    rt["bank"] = bank
    save_runtime(rt)
    log.info("题库造数就绪：%s（新建 %d 条）", ids, created)
    return bank


def ensure_import_sample():
    """生成导入夹具：2 行，1 行合法 + 1 行缺正确答案（用于验证错误明细）。"""
    from openpyxl import Workbook

    path = os.path.join(config.DATA_DIR, "import_sample.xlsx")
    columns = ["知识点编号", "知识点", "学科", "题型", "难度", "分值", "题干",
               "选项A", "选项B", "选项C", "选项D", "选项E", "选项F", "正确答案", "解析"]
    good = {
        "学科": "数据结构", "题型": "单选题", "难度": "简单", "分值": "2",
        "题干": config.tag("导入题"), "选项A": "甲", "选项B": "乙",
        "选项C": "丙", "选项D": "丁", "正确答案": "A", "解析": "夹具生成的合法行。",
    }
    bad = {
        "学科": "数据结构", "题型": "单选题", "难度": "简单", "分值": "2",
        "题干": config.tag("导入缺答案"), "选项A": "甲", "选项B": "乙",
        "选项C": "丙", "选项D": "丁", "正确答案": "", "解析": "缺正确答案，应被拒。",
    }
    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    for row in (good, bad):
        ws.append([row.get(c, "") for c in columns])
    wb.save(path)
    return path


def cleanup_bank(rt=None):
    """题库造数不删除（软删无意义），只把靶子题恢复启用。"""
    try:
        seed_bank(rt=rt, recreate_dead=True)
    except Exception as exc:                                # noqa: BLE001
        log.warning("题库造数复位失败：%s", exc)


def seed_paper_draft(rt=None):
    """组卷用例的草稿卷（5 题）。

    只给**读类**用例用（回填、预览、导出）：写类用例（保存卷头 / 发布 / 复制 / 加题）
    一律用 `new_paper` 现造，否则上一轮把卷子发布掉，这一轮就打不开编辑按钮了。
    """
    rt = rt or load_runtime()
    teacher = ApiSession(config.ACCOUNTS["teacher"])
    title = "UIAT_组卷草稿"

    try:
        data = teacher.get("/papers/", params={"keyword": title, "page_size": 20})
        for p in data.get("results") or []:
            if p.get("title") == title and p.get("status") == "draft":
                paper = {"id": p["id"], "title": title, "questions": p.get("question_count")}
                rt["paper_draft"] = paper
                save_runtime(rt)
                log.info("复用组卷草稿卷 %s（%s 题）", p["id"], p.get("question_count"))
                return paper
    except Exception as exc:                                # noqa: BLE001
        log.warning("查询组卷草稿卷失败：%s", exc)

    data = teacher.post("/papers/random-compose/", json={
        "title": title, "total_count": 5, "target_difficulty": 2.0,
        "duration_minutes": 30,
    })
    paper = data.get("paper") or data
    log.info("组卷草稿卷已创建 %s（%s 题）", paper["id"], paper.get("question_count"))
    info = {"id": paper["id"], "title": title, "questions": paper.get("question_count")}
    rt["paper_draft"] = info
    save_runtime(rt)
    return info


def make_paper(title, total_count=3):
    """现造一份草稿卷（写类用例用），返回 {id, title}。"""
    teacher = ApiSession(config.ACCOUNTS["teacher"])
    data = teacher.post("/papers/random-compose/", json={
        "title": title, "total_count": total_count, "target_difficulty": 2.0,
        "duration_minutes": 30,
    })
    paper = data.get("paper") or data
    return {"id": paper["id"], "title": title,
            "questions": paper.get("question_count")}


def drop_paper(paper_id):
    """按业务规则清理试卷（draft 直接删；published 先退草稿）。"""
    teacher = ApiSession(config.ACCOUNTS["teacher"])
    for status in (None, "draft"):
        try:
            if status:
                teacher.post("/papers/%s/status/" % paper_id, json={"status": status})
            teacher.delete("/papers/%s/" % paper_id, expect=(200, 204))
            return True
        except Exception:                                   # noqa: BLE001
            continue
    return False


# ---------------------------------------------------------------- 清理
def cleanup(rt=None, keep=None):
    """删除本次造数；失败只记日志，不阻断报告产出。"""
    rt = rt or load_runtime()
    keep = config.KEEP_DATA if keep is None else keep
    if keep:
        log.info("保留造数（KEEP_DATA）")
        return
    adm = ApiSession(config.ACCOUNTS["admin"])
    ids = (rt.get("ids") or {})

    for key, val in ids.items():
        if key.startswith("exam") and isinstance(val, int):
            _delete_exam(adm, val)
    if ids.get("paper"):
        _delete_paper(adm, ids["paper"])

    # 兜底：按前缀扫描残留（只碰 UIAT_，绝不动演示数据）
    try:
        for exam in _all(adm, "/exams/"):
            if str(exam.get("title", "")).startswith(config.PREFIX):
                _delete_exam(adm, exam["id"])
        for paper in _all(adm, "/papers/"):
            if str(paper.get("title", "")).startswith(config.PREFIX):
                _delete_paper(adm, paper["id"])
        # 题库造数（bank）不参与清理：题目是软删，删了下一轮还要重建，
        # 反而让题库总量每轮抖动，影响"共 N 条"类断言的可比性。
        bank_ids = {str(v) for v in (rt.get("bank", {}).get("ids") or {}).values()}
        for q in _all(adm, "/questions/"):
            if (str(q.get("stem", "")).startswith("UIAT ")
                    and str(q.get("id")) not in bank_ids):
                adm.delete("/questions/%s/" % q["id"], expect=(200, 204, 400))
    except Exception as exc:                                # noqa: BLE001
        log.warning("兜底清理失败：%s", exc)

    # 清空 runtime 的 id：本轮数据已归档/删除，下一轮必须重造，不能复用失效引用
    try:
        rt["ids"] = {}
        rt["titles"] = {}
        rt["cleaned_at"] = _now().isoformat()
        save_runtime(rt)
    except Exception:                                       # noqa: BLE001
        pass


def _delete_exam(adm, eid):
    """考试有作答记录时不允许直接删，必须先归档（服务端规则）。"""
    try:
        adm.delete("/exams/%s/" % eid)
        log.info("已删除考试 %s", eid)
        return True
    except ApiError as exc:
        if "404" in str(exc):          # 已经不存在，等于清理完成
            return True
        if "10400" not in str(exc):
            log.warning("删除考试 %s 异常：%s", eid, exc)
    # 有作答记录的考试按业务规则「不可删、只能归档」，归档即为清理终点
    try:
        adm.post("/exams/%s/status/" % eid, json={"status": "archived"})
        log.info("考试 %s 有作答记录，已归档（业务规则不允许删除）", eid)
        return True
    except Exception as exc:                                # noqa: BLE001
        if "404" in str(exc):
            return True
        log.warning("归档考试 %s 失败：%s", eid, exc)
        return False


def _delete_paper(adm, pid):
    """试卷的清理终点是「归档」。

    业务规则：已发布的试卷不能直接删；被考试引用的试卷更是删不掉
    （BUG-01 修复后返回 13008）。而有作答记录的考试又不允许删除，
    所以一份卷子只要被考过，就只能归档——这属于审计要求，不是清理失败。
    """
    try:
        adm.delete("/papers/%s/" % pid)
        log.info("已删除试卷 %s", pid)
        return True
    except ApiError as exc:
        if "404" in str(exc):
            return True
        if "13008" in str(exc):        # 被考试引用：直接归档，别再走无效路径
            try:
                adm.post("/papers/%s/status/" % pid, json={"status": "archived"})
                log.info("试卷 %s 被考试引用（13008），已置为归档", pid)
            except ApiError as inner:
                log.warning("归档试卷 %s 失败：%s", pid, inner)
            return False

    for status in ("draft", "archived"):
        try:
            adm.post("/papers/%s/status/" % pid, json={"status": status})
        except ApiError:
            continue
        try:
            adm.delete("/papers/%s/" % pid)
            log.info("已置为 %s 并删除试卷 %s", status, pid)
            return True
        except ApiError:
            continue
    log.info("试卷 %s 保留为归档态（审计要求）", pid)
    return False


def _all(adm, path):
    """拉全量（分页接口统一走 page_size 大值）。"""
    data = adm.get(path + "?page_size=200")
    if isinstance(data, dict):
        return data.get("results") or []
    return data or []


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        cleanup()
    else:
        seed(force="--force" in sys.argv)
        print(open(config.RUNTIME_JSON, encoding="utf-8").read())
