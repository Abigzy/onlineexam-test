# -*- coding: utf-8 -*-
"""pytest 全局夹具。

设计要点：
    - 登录只做一次（session 级缓存 Cookie），每条用例用 add_cookie 注入，
      省掉每条 1.6s 的表单登录；但登录用例（UI-AUTH-01/02/03）必须走真实表单。
    - 造数 session 级做一次，跑完统一清理；失败现场自动挂 Allure 三件套。
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                                            # noqa: E402  (先 import，内部清代理)
from common.api_client import ApiSession                 # noqa: E402
from common.data_factory import (                            # noqa: E402
    _delete_exam,
    _submit,
    cleanup,
    drop_paper,
    make_paper,
    seed,
    seed_bank,
    seed_paper_draft,
)
from common.driver_factory import create_driver          # noqa: E402
from common.logger import get                            # noqa: E402
from pages.auth_pages import LoginPage                   # noqa: E402

log = get("conftest")


def pytest_addoption(parser):
    parser.addoption("--headed", action="store_true", default=False,
                     help="有头模式运行（调试用）")
    parser.addoption("--keep-data", action="store_true", default=False,
                     help="保留 UIAT_ 造数，便于排查现场")
    parser.addoption("--reseed", action="store_true", default=False,
                     help="强制重新造数")


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """把 `--alluredir` 的相对路径钉到本目录下，避免换个工作目录就跑错地方。

    `pytest.ini` 写的是 `--alluredir=report/allure-results`，pytest 不会把它
    解析成相对 rootdir，而是原样交给 allure 插件、由后者按**当前工作目录**
    建目录。于是 `cd onlineexam-ui-autotest && pytest` 会把结果写到
    `onlineexam-ui-autotest/report/`，而收尾的自动生成报告读的是
    `onlineexam_ui_autotest/report/allure-results`——读到上一轮旧结果，或者
    没结果可读直接跳过，两种情况都不报错，只是报告悄悄过期。

    `tryfirst=True` 是必须的：allure 插件在自己的 `pytest_configure` 里就用
    这个值初始化文件写入器（`--clean-alluredir` 的删目录也在那一步），晚改无效。
    """
    opt = getattr(config.option, "allure_report_dir", None)
    if opt and not os.path.isabs(opt):
        config.option.allure_report_dir = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), opt))


@pytest.fixture(scope="session")
def runtime(request):
    """造数：试卷 + 进行中考试 + 未开始考试。"""
    rt = seed(force=request.config.getoption("--reseed"))
    yield rt
    keep = request.config.getoption("--keep-data") or config.KEEP_DATA
    cleanup(rt, keep=keep)


@pytest.fixture(scope="session")
def bank(runtime):
    """题库造数：5 道题（4 种题型 + 1 道停用靶子），按题干精确复用。"""
    return seed_bank(runtime)


@pytest.fixture(scope="session")
def paper_draft(runtime):
    """组卷读类用例的草稿卷（5 题）；写类用例用 new_paper，别动它。"""
    return seed_paper_draft(runtime)


@pytest.fixture()
def new_paper(sessions, request):
    """给写类用例现造一份草稿卷，用完按业务规则清理。"""
    info = make_paper(config.tag("临时卷_%s" % request.node.name[:20]), total_count=3)
    yield info
    drop_paper(info["id"])


@pytest.fixture()
def new_question(sessions, request):
    """给写类用例现造一条题；用例结束软删（服务端只支持停用，记录会保留）。"""
    teacher = sessions["teacher"]
    stem = config.tag("临时题_%s" % request.node.name[:22])
    data = teacher.post("/questions/", json={
        "type": "single", "stem": stem, "difficulty": 2, "score": 2,
        "reference_answer": "A", "analysis": "临时造数，用例结束停用。",
        "subject": "数据结构",
        "options": [{"label": "A", "content": "甲", "is_correct": True},
                    {"label": "B", "content": "乙"},
                    {"label": "C", "content": "丙"},
                    {"label": "D", "content": "丁"}],
    })
    yield {"id": data["id"], "stem": stem}
    try:
        teacher.delete("/questions/%s/" % data["id"])
    except Exception:                                            # noqa: BLE001
        pass


@pytest.fixture(scope="session")
def sessions():
    """每种角色的登录会话（拿 sessionid 用）。"""
    return {role: ApiSession(user) for role, user in config.ACCOUNTS.items()}


@pytest.fixture()
def driver(request):
    drv = create_driver(headless=not request.config.getoption("--headed"))
    yield drv
    try:
        drv.quit()
    except Exception:                                    # noqa: BLE001
        pass


def _inject(drv, api):
    """把已登录的 sessionid 塞进浏览器，免去每条用例都走表单。"""
    drv.get(config.BASE_URL + "/login/")
    drv.delete_all_cookies()
    host = config.BASE_URL.split("//")[1].split(":")[0]
    drv.add_cookie({"name": "sessionid", "value": api.session_id,
                    "domain": host, "path": "/"})


@pytest.fixture()
def as_student(driver, sessions):
    _inject(driver, sessions["student"])
    return driver


@pytest.fixture()
def as_teacher(driver, sessions):
    _inject(driver, sessions["teacher"])
    return driver


@pytest.fixture()
def as_admin(driver, sessions):
    _inject(driver, sessions["admin"])
    return driver


@pytest.fixture()
def as_student_isolated(driver):
    """独立的学生会话：给「退出登录」这类会销毁 session 的用例用。

    不能复用 as_student——它的 sessionid 被整个会话共享，退出登录会把
    后面的学生用例全部打回登录页（第一轮跑就踩到了）。
    """
    _inject(driver, ApiSession(config.ACCOUNTS["student"]))
    return driver


@pytest.fixture()
def new_exam(runtime, sessions, request):
    """给单条用例造一场干净的考试（默认 max_attempts=1）。

    为什么需要：作答状态会互相污染——共享一场考试时，"上一题答过没有"
    会让"点选项后应恰好选中 1 个"这类断言变成碰运气。用例结束归档（有作答
    记录的考试按业务规则不可删），归档是清理终点。
    """
    created = []
    # 必须用 **teacher** 建考试：教师列表只显示自己创建的考试
    # （admin 建的考试教师根本看不到，用 admin 造数会让"新建→列表查找"整条链断掉）。
    teacher = sessions["teacher"]
    adm = sessions["admin"]

    def _teacher_paper():
        """优先用 seed 造的那份**4 题**卷（题数可控，考试闭环用例依赖它）。

        seed 现在也用 teacher 建，所以这份卷教师本来就可见；只有当它缺失/不可见时，
        才退回到"教师可见的第一份已发布卷"（题数不可控，仅作兜底）。
        """
        pid = runtime["ids"].get("paper")
        if pid:
            try:
                paper = teacher.get("/papers/%s/" % pid)
                # 必须确认是 seed 那份 **4 题**卷（单选/多选/填空/简答）：
                # 简答题是"改主观题分数"用例的前提，退回到随机卷会直接测不了。
                if paper.get("question_count") == 4:
                    return pid
            except Exception:                          # noqa: BLE001
                pass
        data = teacher.get("/papers/", params={"status": "published", "page_size": 5})
        rows = data.get("results") or []
        if rows:
            return rows[0]["id"]
        made = teacher.post("/papers/random-compose/", json={
            "title": config.tag("考试用卷"), "total_count": 3,
            "target_difficulty": 2.0, "duration_minutes": 30})
        pid = (made.get("paper") or made)["id"]
        teacher.post("/papers/%s/status/" % pid, json={"status": "published"})
        return pid

    def _make(attempts=1, show_score=True, offset_minutes=-5, publish=True):
        now = datetime.now(timezone(timedelta(hours=8)))
        title = config.tag("临时_%s" % request.node.name[:24])
        data = teacher.post("/exams/", json={
            "title": title, "paper_id": _teacher_paper(),
            "start_time": (now + timedelta(minutes=offset_minutes)).isoformat(),
            "end_time": (now + timedelta(hours=3)).isoformat(),
            "duration_minutes": 30, "open_to_all": True,
            "show_score_immediately": show_score,
            "max_attempts": attempts,
            "shuffle_questions": False, "shuffle_options": False,
        })
        eid = (data.get("exam") or data)["id"]
        if publish:
            teacher.post("/exams/%s/status/" % eid, json={"status": "published"})
        created.append(eid)
        return eid

    yield _make
    for eid in created:
        _delete_exam(adm, eid)


@pytest.fixture()
def exam_with_attempt(sessions, new_exam):
    """教师建的、且**已有学生开考**的考试（监控页要看真实数据）。

    为什么必须由教师建：管理员建的考试教师列表/监控页根本看不到
    （权限作用域），用 admin 造数会让监控页概览全是「—」。
    """
    eid = new_exam(publish=True)
    student = sessions["student"]
    data = student.post("/exams/%s/start/" % eid, json={"confirm": True})
    attempt = data.get("attempt") or data
    yield {"exam_id": eid, "attempt_id": attempt["id"]}


@pytest.fixture()
def proctor_scene(sessions, new_exam):
    """模块 09 专用：一场考试里放两份作答 —— 一份高风险（已判分）、一份正常对照。

    为什么不复用库里的历史数据：`/proctoring/exams/` 现在有 274 场带埋点的
    `at_*` 考试，页面默认选中 rows[0]，用历史数据等于把用例绑在别人的数据上；
    而且风险等级不确定，「只看嫌疑」过滤就验不出「过滤后每行都 ≥ MEDIUM」。

    造数链路（实测）：教师建考试(max_attempts=3) → 学生 start →
    `POST /attempts/{id}/behavior/` 上报 6 次 switch + 1 次 paste
    （默认 `max_switch_count=5`、`auto_submit_on_limit=False`，只记违规不强制交卷）
    → 交卷 → 教师判客观题；再开一次不上报行为 → 交卷，作为正常对照。
    """
    teacher, student = sessions["teacher"], sessions["student"]
    eid = new_exam(publish=True, attempts=3)

    def _attempt(with_behavior):
        data = student.post("/exams/%s/start/" % eid, json={"confirm": True})
        aid = (data.get("attempt") or data)["id"]
        if with_behavior:
            student.post("/attempts/%s/behavior/" % aid, json={
                "events": [{"type": "switch"}] * 6 + [{"type": "paste"}]})
        state = student.get("/attempts/%s/paper/" % aid)
        questions = state.get("questions") or []
        single = next((q for q in questions if q.get("question_type") == "single"), None)
        _submit(student, aid, questions,
                {single["paper_question_id"]: "B"} if single else {})
        return aid

    flagged = _attempt(True)
    clean = _attempt(False)
    teacher.post("/grading/attempts/%s/grade/" % flagged, json={})
    rows = teacher.get("/exams/%s/attempts/" % eid).get("results") or []
    assert rows, "造数后考试里没有作答记录"
    return {
        "exam_id": eid,
        "flagged_attempt": flagged,
        "clean_attempt": clean,
        "student_id": rows[0]["student_id"],
    }


@pytest.fixture()
def user_cleanup(sessions):
    """登记本条用例创建的用户名，收尾按用户名**真删**（`DELETE /users/{id}/`）。

    管理端页面写着「本期不提供删除」，但 API 的 `UserViewSet.destroy()` 支持删除
    （只拦「删自己」和「删超级管理员」）。不清理会往 52 个演示账号里持续灌垃圾。
    """
    names = []
    yield names
    adm = sessions["admin"]
    for name in names:
        try:
            rows = adm.get("/users/", params={"search": name}).get("results") or []
            for row in rows:
                if row.get("username") == name:
                    adm.delete("/users/%s/" % row["id"])
        except Exception:                                    # noqa: BLE001
            pass


@pytest.fixture()
def admin_user(sessions, user_cleanup, request):
    """管理员用 API 现造一个学生靶子（编辑 / 停用 / 重置密码用例共用）。"""
    adm = sessions["admin"]
    uname = config.tag("adm_tgt_%s" % request.node.name[:16])
    email = uname.lower() + "@example.com"
    data = adm.post("/users/", json={
        "username": uname, "email": email, "real_name": "UIAT靶子",
        "role": "student", "grade_year": "2026",
        "password": config.PASSWORD,
    })
    user_cleanup.append(uname)
    return {
        "id": data["id"], "username": uname, "email": email,
        "password": config.PASSWORD, "real_name": "UIAT靶子",
    }


@pytest.fixture()
def bare_student(sessions, user_cleanup, request):
    """一个**没有加入任何学科班**的学生：练习页与错题本的空态场景。

    为什么不复用演示账号 student：它已经有 2000+ 条作答、200 条错题，
    空态根本走不到；而退出登录/改数据都会污染共享会话。
    """
    adm = sessions["admin"]
    uname = config.tag("bare_%s" % request.node.name[:14])
    data = adm.post("/users/", json={
        "username": uname, "email": uname.lower() + "@test.local",
        "real_name": "UIAT空态生", "role": "student", "grade_year": "2026",
        "password": config.PASSWORD,
    })
    user_cleanup.append(uname)
    return {"id": data["id"], "username": uname, "password": config.PASSWORD}


@pytest.fixture()
def practice_student(sessions, user_cleanup, request):
    """有题可练的学生：现造账号 + 现造学科班（数据结构）并加入。

    关键约束：每日练习一次只给 6 题，题型**混合**（可能全是主观题）。
    「点选项」类用例必须有带 `.option-row` 的卡，所以这里按接口预检——
    抽到的 6 题里没有客观题就换一个新生（最多 4 次），避免用例层去赌题型。
    """
    adm, teacher = sessions["admin"], sessions["teacher"]
    objective = {"single", "multiple", "judge"}
    last = None
    for attempt in range(4):
        uname = config.tag("prac%d%s" % (attempt, request.node.name[:10]))
        data = adm.post("/users/", json={
            "username": uname, "email": uname.lower() + "@test.local",
            "real_name": "UIAT练习生", "role": "student", "grade_year": "2026",
            "password": config.PASSWORD,
        })
        user_cleanup.append(uname)
        cls = teacher.post("/classrooms/", json={
            "name": config.tag("pcls%d%s" % (attempt, request.node.name[:10])),
            "class_type": "subject", "subject": "数据结构", "grade_year": "2026",
        })
        teacher.post("/classrooms/%s/students/" % cls["id"], json={"student_ids": [data["id"]]})

        api = ApiSession(uname, config.PASSWORD)
        payload = api.get("/recommend/students/%s/practice/" % data["id"],
                          params={"size": 6})
        types = {item["type"] for item in (payload.get("items") or [])}
        last = {"id": data["id"], "username": uname, "password": config.PASSWORD,
                "classroom_id": cls["id"], "types": sorted(types)}
        if types & objective:
            break
    yield last
    # 清理：先解散学科班（教师），再删账号（管理员）
    try:
        teacher.delete("/classrooms/%s/" % last["classroom_id"])
    except Exception:                                        # noqa: BLE001
        pass


@pytest.fixture()
def new_classroom(sessions, request):
    """教师现建一个行政班（写类用例的靶子），收尾按 id 删除。

    为什么不用演示库里那 52 个班：它们大多来自更早的用例、命名不可控，
    删除/加人会污染别人的数据；现建现删最干净。
    """
    teacher = sessions["teacher"]
    name = config.tag("CLS_%s" % request.node.name[:16])
    data = teacher.post("/classrooms/", json={
        "name": name, "class_type": "admin", "grade_year": "2026",
        "description": "UIAT 临时班级",
    })
    yield {"id": data["id"], "name": name}
    try:
        teacher.delete("/classrooms/%s/" % data["id"])
    except Exception:                                        # noqa: BLE001
        pass


@pytest.fixture()
def class_student(sessions, user_cleanup, request):
    """待加入班级的学生（返回学号，供「按学号导入」用）。"""
    adm = sessions["admin"]
    uname = config.tag("clsstu_%s" % request.node.name[:14])
    data = adm.post("/users/", json={
        "username": uname, "email": uname.lower() + "@test.local",
        "real_name": "UIAT班级生", "role": "student", "grade_year": "2026",
        "password": config.PASSWORD,
    })
    user_cleanup.append(uname)
    detail = adm.get("/users/%s/" % data["id"])
    return {"id": data["id"], "username": uname, "real_name": "UIAT班级生",
            "student_no": detail.get("student_no") or ""}


@pytest.fixture()
def pending_attempt(sessions, new_exam):
    """教师建的、学生**已交卷但未判分**的作答（批改台的主场景）。

    每条批改用例都现造一份：判客观题/改主观分/出分都会改状态，
    共用一份会让"待批 N 道"这类断言互相污染。
    """
    eid = new_exam(publish=True)
    student = sessions["student"]
    data = student.post("/exams/%s/start/" % eid, json={"confirm": True})
    attempt = data.get("attempt") or data
    aid = attempt["id"]
    state = student.get("/attempts/%s/paper/" % aid)
    questions = state.get("questions") or []
    # 至少答对一道单选（正确答案 B）：全留空的话客观题判完还是 0 分，
    # "判分后分数应变化"这条断言就永远不成立（踩过）。
    single = next((q for q in questions if q.get("question_type") == "single"), None)
    correct = {single["paper_question_id"]: "B"} if single else {}
    _submit(student, aid, questions, correct)
    return {"exam_id": eid, "attempt_id": aid}


@pytest.fixture()
def extra_driver(request):
    """第二个浏览器会话：跨角色联动用例（教师建 → 学生看）需要同时挂两个身份。

    不用 `driver` 是因为它已经被 as_teacher 占用了 cookie，同一 driver
    切身份会把教师的登录态顶掉。

    ⚠ **当前不可用（2026-11-05 实测）**：`create_driver()` 使用固定的
    `--user-data-dir`，同一进程再开一个 Chrome 会因 profile 锁冲突报
    `SessionNotCreatedException: DevToolsActivePort file doesn't exist`。
    跨账号验证请改用「同一 driver 清 cookie → 表单登录 → 完成后重新注入
    原 session」（见 `scripts/test_l1_admin.py`）；确实需要双会话时，
    先给 `create_driver` 增加独立 `profile_dir` 参数再启用本夹具。
    """
    drv = create_driver(headless=not request.config.getoption("--headed"))
    yield drv
    try:
        drv.quit()
    except Exception:                                    # noqa: BLE001
        pass


@pytest.fixture()
def anonymous(driver):
    driver.get(config.BASE_URL + "/login/")
    driver.delete_all_cookies()
    return driver


# ---------------------------------------------------------------- 失败现场
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return
    drv = item.funcargs.get("driver")
    if drv is None:
        return
    name = item.name.replace("[", "_").replace("]", "")
    try:
        import allure
        shot = os.path.join(config.SCREENSHOT_DIR, "%s_%s.png" % (name, time.strftime("%H%M%S")))
        drv.save_screenshot(shot)
        allure.attach.file(shot, name="失败截图", attachment_type=allure.attachment_type.PNG)
        allure.attach(drv.page_source, name="页面源码", attachment_type=allure.attachment_type.HTML)
        logs = drv.get_log("browser")
        text = "\n".join("%s %s" % (e.get("level"), e.get("message")) for e in logs) or "（空）"
        allure.attach(text, name="控制台日志", attachment_type=allure.attachment_type.TEXT)
        allure.attach(drv.current_url, name="失败时 URL", attachment_type=allure.attachment_type.TEXT)
    except Exception as exc:                             # noqa: BLE001
        log.warning("挂载失败现场失败：%s", exc)


# ---------------------------------------------------------------- 自动出报告
def pytest_unconfigure(config):
    """跑完自动重新生成 Allure 报告（`config.AUTO_REPORT`，**默认开启**）。

    为什么默认开启：`--clean-alluredir` 每次启动都把 results 清空，忘了生成就
    会留下一份「页面能开、数字过期」的旧报告，比直接报错更误导。默认开着，
    直接 `pytest` 跑完就是最新报告，不必再记一条命令。
    关掉用 `OE_AUTO_REPORT=0`（false / no / off 同义），只在「反复调单条用例」
    或「results 交给 CI 统一生成报告」时才需要。

    为什么挂在 `pytest_unconfigure` 而不是 `pytest_sessionfinish`：后者要与
    terminalreporter 的钩子抢顺序，输出会插在 `1 passed in 18.7s` 汇总行之**前**，
    看起来像测试没跑完就出了报告；unconfigure 在汇总之后，输出落在最末。

    四条硬约束（都为了"生成报告不该影响测试结论"）：
      1. 任何异常只记 warning，**不抛、不改退出码**——用例通过就是通过；
      2. only-collect（`--co`）与空结果目录直接跳过，此时没有可生成的东西；
      3. Allure 是 JVM 进程，生成带超时（见 `report_builder.GENERATE_TIMEOUT`）；
      4. `quiet=True` 吞掉 JVM 的输出，只留一行结论，不污染 pytest 的汇总。

    开关定义在 `config.AUTO_REPORT`（与其他 `OE_*` 集中在一处），这里只管消费。

    ⚠ 本函数的形参 `config` 是 pytest 的 `Config` 对象，会**遮蔽**模块级的
    `import config`。直接用 `config.AUTO_REPORT` 会得到
    `AttributeError: 'Config' object has no attribute 'AUTO_REPORT'`——而且因为
    守卫写在 try 之外，异常会冲出钩子，把整轮会话的退出码改成 1（用例明明全绿）。
    因此这里局部重命名导入，并把**守卫本身也放进 try**：钩子里任何东西都不该杀掉会话。
    """
    try:
        import config as appcfg                          # 局部重命名，避开形参污染
        if not appcfg.AUTO_REPORT:
            return
        if getattr(config.option, "collectonly", False):
            return
        from common.report_builder import RESULTS, build
        if not RESULTS.is_dir() or not any(RESULTS.glob("*-result.json")):
            log.warning("自动生成报告已跳过：%s 下没有结果文件", RESULTS)
            return
        t0 = time.time()
        info = build(quiet=True)
        cost = time.time() - t0
        if info["code"] == 0:
            print("[auto-report] %d 条 / %.1fs -> %s"
                  % (info["count"], cost, info["out"] / "uireport.html"))
        else:
            log.warning("自动生成报告失败：%s", info["msg"])
            print("[auto-report] 失败：%s（手工重跑 python tools/gen_report.py）" % info["msg"])
    except Exception as exc:                             # noqa: BLE001
        log.warning("自动生成报告异常：%s", exc)
        print("[auto-report] 异常：%s" % exc)
