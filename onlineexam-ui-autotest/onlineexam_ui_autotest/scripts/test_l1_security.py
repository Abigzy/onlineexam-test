# -*- coding: utf-8 -*-
"""L1 权限与可见性：8 条（docs/03 UI-SEC-02 ~ 06 + 07 ~ 10）。

分层：`UI-SEC-01` 已在 L0 冒烟覆盖，本文件不重复。
`UI-SEC-07 ~ 10` 是边界档（未登录回跳、越权不泄露数据），随 L2 边界批一起补齐。

判定口径按实测分两类（见 `pages/security_pages.py` 注释）：
  403    —— teacher→/my-exams/、student→/exams/{id}/monitor/
  302→/  —— student / teacher→/manage*/（不是 403）
"""
import re

import allure
import pytest
import requests

import config
from pages.auth_pages import LoginPage
from pages.security_pages import AccessGuardPage

P0 = pytest.mark.p0
P1 = pytest.mark.p1
P2 = pytest.mark.p2
FEATURE = "11 权限与可见性"


def _status(session, path):
    """直接读服务端响应（allow_redirects=False），区分 403 与 302。

    `session` 既可以是 ApiSession（带 `.session`），也可以是裸 requests.Session
    ——未登录场景没有登录态可复用，直接开一个新会话。
    """
    sess = getattr(session, "session", session)
    r = sess.get(config.BASE_URL + path, allow_redirects=False, timeout=30)
    return r.status_code, r.headers.get("Location") or ""


@allure.feature(FEATURE)
class TestRoleIsolation:
    """角色越权访问与学生导航可见范围。"""

    @P0
    @allure.story("UI-SEC-02 教师访问我的考试页被拒")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_teacher_cannot_open_my_exams(self, as_teacher, sessions):
        code, _ = _status(sessions["teacher"], "/my-exams/")
        assert code == 403, "教师访问学生「我的考试」应返回 403，实际 %s" % code

        page = AccessGuardPage(as_teacher).open_protected("/my-exams/")
        assert not page.has(page.L["exam_cards"]), "403 页不应渲染学生考试卡片"
        assert "Traceback" not in as_teacher.page_source, "403 页泄露了服务端堆栈"

    @P1
    @allure.story("UI-SEC-03 学生访问管理端被重定向回首页")
    @allure.severity(allure.severity_level.NORMAL)
    def test_student_manage_users_redirect(self, as_student, sessions):
        code, loc = _status(sessions["student"], "/manage/users/")
        assert code in (301, 302) and "/manage" not in loc, \
            "学生访问管理端应被重定向回首页，实际 %s → %r" % (code, loc)

        page = AccessGuardPage(as_student).open_protected("/manage/users/")
        page.wait_leave("/manage")
        assert page.url.rstrip("/") == config.BASE_URL, \
            "最终应落地首页，实际 %s" % page.url
        assert not page.has(page.L["user_filter"]), "首页不应出现用户管理筛选表单"
        assert "用户管理" not in page.nav_text_content(), "学生导航出现管理端入口"

    @P1
    @allure.story("UI-SEC-04 教师访问管理端被重定向回首页")
    @allure.severity(allure.severity_level.NORMAL)
    def test_teacher_manage_redirect(self, as_teacher, sessions):
        code, loc = _status(sessions["teacher"], "/manage/")
        assert code in (301, 302) and "/manage" not in loc, \
            "教师访问管理控制台应被重定向回首页，实际 %s → %r" % (code, loc)

        page = AccessGuardPage(as_teacher).open_protected("/manage/")
        page.wait_leave("/manage")
        assert page.url.rstrip("/") == config.BASE_URL, \
            "最终应落地首页，实际 %s" % page.url
        nav = page.nav_text_content()
        assert "管理控制台" not in nav and "用户管理" not in nav, \
            "教师导航出现管理端入口：%s" % nav[:200]
        assert not page.has(page.L["user_filter"]), "首页不应出现数据总览/用户管理表单"

    @P1
    @allure.story("UI-SEC-05 学生导航不出现教师与管理员入口")
    @allure.severity(allure.severity_level.NORMAL)
    def test_student_nav_scope(self, as_student):
        page = AccessGuardPage(as_student).open_protected("/")
        nav = page.nav_text_content()

        for item in ("题库", "试卷与组卷", "考试管理", "批改与成绩", "作弊检测",
                     "管理控制台", "用户管理"):
            assert item not in nav, \
                "学生导航出现越权入口「%s」：%s" % (item, nav[:200])
        for item in ("我的考试", "错题本", "我的学情", "每日练习"):
            assert item in nav, "学生导航缺少「%s」：%s" % (item, nav[:200])

    @P1
    @allure.story("UI-SEC-06 学生访问考试监控页被拒")
    @allure.severity(allure.severity_level.NORMAL)
    def test_student_cannot_open_monitor(self, as_student, sessions, new_exam):
        eid = new_exam(publish=True)
        path = "/exams/%s/monitor/" % eid
        code, _ = _status(sessions["student"], path)
        assert code in (302, 403), \
            "学生访问考试监控页应被拒绝，实际 HTTP %s" % code

        page = AccessGuardPage(as_student).open_protected(path)
        assert not page.has(page.L["attempt_body"]), "403 页不应出现考生名单"
        assert not page.has(page.L["exam_cards"]), "403 页不应出现考试卡片"
        assert "Traceback" not in as_student.page_source, "403 页泄露了服务端堆栈"


@allure.feature(FEATURE)
class TestAnonymousAndLeakage:
    """未登录回跳与越权页面的数据泄露检查（L2 边界）。"""

    @P1
    @allure.story("UI-SEC-07 未登录访问受保护页跳登录并回跳原页")
    @allure.severity(allure.severity_level.NORMAL)
    def test_login_returns_to_original_page(self, anonymous):
        """两段都要验：① 服务端 302 带对 next；② 登录后真的回到原页而不是首页。

        只验 ①（很多人只跑到这里）会漏掉"登录成功但 next 被吞掉"的情况，
        用户体感是"我点了个链接，登完被扔回首页，还得再点一次"。
        """
        code, loc = _status(requests.Session(), "/my-exams/")
        assert code in (301, 302), "未登录访问 /my-exams/ 应跳转，实际 %s" % code
        assert "/login/" in loc and "next=/my-exams/" in loc, \
            "跳转地址缺少 next=/my-exams/：%r" % loc

        page = LoginPage(anonymous)
        page.open_raw("/my-exams/")          # open_raw 无返回值，别链式调用
        page.wait_url("/login/")
        assert "next=/my-exams/" in anonymous.current_url, \
            "浏览器跳到登录页时丢了 next 参数：%s" % anonymous.current_url

        page.login(config.ACCOUNTS["student"], next_path="/my-exams/")
        page.wait_for(lambda d: re.fullmatch(r".*/my-exams/?", d.current_url) is not None,
                      message="登录成功后没有回到 /my-exams/（当前 %s）" % anonymous.current_url)
        assert "我的考试" in page.body_text(), "回到的页面不是「我的考试」页"

    @P2
    @allure.story("UI-SEC-08 未登录访问个人中心跳登录")
    @allure.severity(allure.severity_level.MINOR)
    def test_anonymous_profile_redirect(self, anonymous):
        code, loc = _status(requests.Session(), "/profile/")
        assert code in (301, 302), "未登录访问 /profile/ 应跳转，实际 %s" % code
        assert "/login/" in loc and "next=/profile/" in loc, \
            "跳转地址缺少 next=/profile/：%r" % loc

        page = AccessGuardPage(anonymous).open_protected("/profile/")
        page.wait_url("/login/")
        assert "next=/profile/" in anonymous.current_url, \
            "浏览器最终地址没有带 next 参数：%s" % anonymous.current_url
        for marker in ("真实姓名", "学号 / 工号", "保存资料"):
            assert marker not in page.body_text(), \
                "登录页泄露了个人中心内容「%s」" % marker

    @P2
    @allure.story("UI-SEC-09 越权页面不泄露业务数据")
    @allure.severity(allure.severity_level.MINOR)
    def test_forbidden_pages_do_not_leak(self, as_student, sessions):
        exams = sessions["teacher"].get("/exams/", params={"page_size": 1}).get("results") or []
        assert exams, "用例前置：需要一场已存在的考试"
        paths = ["/question-bank/", "/grading/exams/%s/scoreboard/" % exams[0]["id"]]

        page = AccessGuardPage(as_student)
        for path in paths:
            code, _ = _status(sessions["student"], path)
            assert code == 403, "%s 应返回 403，实际 %s" % (path, code)

            page.open_protected(path)
            body = page.body_text()
            for marker in ("Traceback", "SELECT ", "参考答案", "UIAT 题库"):
                assert marker not in body, "%s 的 403 页泄露了「%s」" % (path, marker)
            assert not page.has(page.L["question_rows"]), \
                "%s 的 403 页仍然渲染了题目列表" % path

    @P2
    @allure.story("UI-SEC-10 教师访问学生专属页被拒")
    @allure.severity(allure.severity_level.MINOR)
    def test_teacher_blocked_on_student_pages(self, as_teacher, sessions):
        for path in ("/my-wrong-book/", "/practice/"):
            code, _ = _status(sessions["teacher"], path)
            assert code == 403, "教师访问 %s 应返回 403，实际 %s" % (path, code)

            page = AccessGuardPage(as_teacher).open_protected(path)
            body = page.body_text()
            assert "暂无错题" not in body, "%s 的 403 页出现了错题内容" % path
            assert "提交作答" not in body, "%s 的 403 页出现了练习卡片" % path
            assert "Traceback" not in as_teacher.page_source, "%s 泄露了服务端堆栈" % path
