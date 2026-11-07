# -*- coding: utf-8 -*-
"""L1/L2 认证与账号：14 条（docs/03 UI-AUTH-05 ~ 18，P1 8 / P2 6）。

`UI-AUTH-01 ~ 04` 已在 L0 冒烟覆盖（四角色登录/退出），本批不重复。

三条实测口径（写死在这里，避免后来人照用例原文写错）：
  1. **登录失败只有一种文案**「账号或密码错误，请重新输入」，账号不存在与密码错误
     完全一致（不枚举账号）；停用账号才有单独文案（管理端批已验证）。
  2. **注册页的入学年级没有空选项**（`grade_year_choices()` 从当前年份往前 4 年），
     所以「空提交」时年级不报必填错——原文写的「四处必填」实际是 5 处（不含年级）。
  3. **学号是展示用的 `div.form-control`**，不是只读 input；`readonly` 断言无从谈起，
     改验「8 位纯数字 + 前 4 位等于所选年级 + 页面注明由系统派发」。
"""
import re
import time

import allure
import pytest

import config
from common.api_client import ApiSession
from pages.auth_pages import LoginPage, ProfilePage, RegisterPage

P1 = pytest.mark.p1
P2 = pytest.mark.p2
FEATURE = "01 认证与账号"

LOGIN_FAILED = "账号或密码错误，请重新输入"


def nav_text(drv):
    """整条导航的文本（含折叠下拉项），空白压成单空格便于包含判断。"""
    raw = drv.execute_script(
        "return (document.querySelector('#mainNav')||{}).textContent||'';") or ""
    return " ".join(raw.split())


def body_text(drv):
    return drv.find_element("css selector", "body").text


@allure.feature(FEATURE)
class TestLoginWays:
    """登录入口的三种标识（用户名 / 邮箱 / 学号）与失败态。"""

    @P1
    @allure.story("UI-AUTH-05 邮箱方式登录成功")
    @allure.severity(allure.severity_level.NORMAL)
    def test_login_with_email(self, anonymous, sessions):
        email = sessions["teacher"].get("/auth/me/")["email"]

        page = LoginPage(anonymous)
        page.open()
        page.type(page.L["username"], email)
        page.type(page.L["password"], config.PASSWORD)
        page.click(page.L["submit"])
        page.wait.until(lambda d: "/login/" not in d.current_url,
                        message="用邮箱登录后没有离开登录页")

        assert anonymous.current_url.rstrip("/") == config.BASE_URL, \
            "邮箱登录应落地首页，实际 %s" % anonymous.current_url
        nav = nav_text(anonymous)
        assert "题库" in nav and "考试管理" in nav, \
            "教师工作台导航不完整：%s" % nav[:160]

    @P1
    @allure.story("UI-AUTH-06 学号方式登录成功")
    @allure.severity(allure.severity_level.NORMAL)
    def test_login_with_student_no(self, anonymous, sessions):
        student_no = sessions["student"].get("/auth/me/")["student_no"]
        assert re.match(r"^\d{8}$", student_no), \
            "用例前置：学生学号应为 8 位数字，实际 %r" % student_no

        page = LoginPage(anonymous)
        page.open()
        page.type(page.L["username"], student_no)
        page.type(page.L["password"], config.PASSWORD)
        page.click(page.L["submit"])
        page.wait.until(lambda d: "/login/" not in d.current_url,
                        message="用学号登录后没有离开登录页")

        assert anonymous.current_url.rstrip("/") == config.BASE_URL, \
            "学号登录应落地首页，实际 %s" % anonymous.current_url
        assert "我的考试" in nav_text(anonymous), "学号登录后不是学生工作台"

    @P1
    @allure.story("UI-AUTH-07 密码错误提示统一文案且停留登录页")
    @allure.severity(allure.severity_level.NORMAL)
    def test_wrong_password(self, anonymous):
        page = LoginPage(anonymous)
        page.open()
        page.type(page.L["username"], config.ACCOUNTS["student"])
        page.type(page.L["password"], "Wrong@123456")
        page.click(page.L["submit"])
        page.wait.until(lambda d: page.visible(page.L["error"]), message="密码错误没有提示")

        assert page.error_text().strip() == LOGIN_FAILED, \
            "密码错误文案不符：%r" % page.error_text()
        assert "/login/" in anonymous.current_url, "密码错误不应离开登录页"
        assert page.attr(page.L["username"], "value") == config.ACCOUNTS["student"], \
            "失败后账号输入框被清空，用户需要重填"

    @P1
    @allure.story("UI-AUTH-08 不存在的账号与密码错误提示完全一致（不枚举账号）")
    @allure.severity(allure.severity_level.NORMAL)
    def test_unknown_account_same_message(self, anonymous):
        page = LoginPage(anonymous)
        page.open()
        page.type(page.L["username"], "UIAT_NOBODY_20261105")
        page.type(page.L["password"], "Whatever@123456")
        page.click(page.L["submit"])
        page.wait.until(lambda d: page.visible(page.L["error"]), message="不存在的账号没有提示")

        assert page.error_text().strip() == LOGIN_FAILED, \
            "不存在的账号文案与密码错误不一致：%r" % page.error_text()
        text = body_text(anonymous)
        for leak in ("用户不存在", "账号不存在", "该账号未注册", "无此用户"):
            assert leak not in text, "登录页出现可枚举账号的提示「%s」" % leak


@allure.feature(FEATURE)
class TestRegister:
    """注册页：必填拦截、成功派发学号、四类校验。"""

    @P1
    @allure.story("UI-AUTH-09 已登录状态访问登录页被重定向")
    @allure.severity(allure.severity_level.NORMAL)
    def test_logged_in_visit_login_redirects(self, as_student):
        page = LoginPage(as_student)
        as_student.get(config.BASE_URL + "/login/")
        page.wait_leave_login()

        assert as_student.current_url.rstrip("/") == config.BASE_URL, \
            "已登录访问登录页应回首页，实际 %s" % as_student.current_url
        assert not page.visible(page.L["password"]), "已登录却仍渲染登录表单"

    @P1
    @allure.story("UI-AUTH-10 注册页必填项为空提交被拦截")
    @allure.severity(allure.severity_level.NORMAL)
    def test_register_empty(self, anonymous):
        page = RegisterPage(anonymous)
        page.submit_empty()
        page.wait.until(lambda d: page.count(page.L["errors"]) > 0, message="空提交没有报错")

        assert "/register/" in anonymous.current_url, "空提交不应该跳转"
        errs = page.field_errors()
        # 实测：年级 select 没有空选项，默认选中第一项，所以必填校验只覆盖 5 个文本框
        for label in ("用户名", "真实姓名", "邮箱", "密码", "确认密码"):
            assert label in errs, "「%s」为空却没有错误提示：%s" % (label, list(errs))
        assert all("必填" in msg for msg in errs["用户名"]), \
            "必填错误文案不符：%s" % errs["用户名"]
        assert "入学年级" not in errs, \
            "入学年级出现了必填错误，说明 select 的空选项行为变了，需要重写本用例"
        assert page.grade_value(), "入学年级没有默认值，空提交口径失效"

    @P1
    @allure.story("UI-AUTH-11 注册新学生成功后自动登录并由系统派发学号")
    @allure.severity(allure.severity_level.NORMAL)
    def test_register_success(self, anonymous, user_cleanup):
        uname = config.tag("reg%d" % int(time.time() % 100000))
        email = uname.lower() + "@test.local"
        user_cleanup.append(uname)

        page = RegisterPage(anonymous)
        page.fill(uname, email, "自动化学生", config.PASSWORD, grade_text="2026级")
        page.submit()
        page.wait.until(lambda d: "/register/" not in d.current_url,
                        message="注册成功后没有跳转")

        assert anonymous.current_url.rstrip("/") == config.BASE_URL, \
            "注册成功应落地首页，实际 %s" % anonymous.current_url
        assert "注册成功，已为你自动登录" in body_text(anonymous), \
            "注册成功提示缺失"

        prof = ProfilePage(anonymous)
        prof.open()
        student_no = prof.student_no_text()
        assert re.match(r"^\d{8}$", student_no), "系统派发的学号不是 8 位数字：%r" % student_no
        assert student_no.startswith("2026"), \
            "学号前 4 位应等于入学年级 2026，实际 %r" % student_no
        assert "由系统派发，不可修改" in prof.dispatch_note(), \
            "个人中心没有说明学号由系统派发：%r" % prof.dispatch_note()

    @P2
    @allure.story("UI-AUTH-12 个人中心修改真实姓名后导航同步")
    @allure.severity(allure.severity_level.NORMAL)
    def test_profile_rename(self, anonymous, admin_user):
        """用**一次性账号**改姓名，不动演示库的 student（纪律 3：造数不污染）。"""
        page = LoginPage(anonymous)
        page.login(admin_user["username"], admin_user["password"])

        prof = ProfilePage(anonymous)
        prof.open()
        assert prof.attr(prof.L["real_name"], "value") == admin_user["real_name"], \
            "个人中心没有回填当前姓名"
        new_name = "UIAT改名%s" % time.strftime("%H%M%S")
        prof.update_real_name(new_name)
        prof.wait.until(lambda d: prof.visible(prof.L["success"]),
                        message="保存资料后没有成功提示")

        assert "个人资料已更新" in prof.save_success_text(), \
            "保存提示不符：%r" % prof.save_success_text()
        assert new_name in nav_text(anonymous), \
            "保存后右上角用户名没有同步：%s" % nav_text(anonymous)[:120]

        anonymous.refresh()
        prof.wait.until(lambda d: nav_text(d).count(new_name) > 0,
                        message="刷新后导航又变回旧姓名")
        prof.open()
        assert prof.attr(prof.L["real_name"], "value") == new_name, "姓名没有落库"

    @P2
    @allure.story("UI-AUTH-13 重复用户名注册被拒")
    @allure.severity(allure.severity_level.MINOR)
    def test_duplicate_username(self, anonymous):
        page = RegisterPage(anonymous)
        page.fill(config.ACCOUNTS["student"],
                  "uiat_dup%s@test.local" % int(time.time()),
                  "自动化学生", config.PASSWORD, grade_text="2026级")
        page.submit()

        assert "/register/" in anonymous.current_url, "重复用户名不应注册成功"
        assert any("该用户名已被占用" in e for e in page.errors()), \
            "重复用户名提示不符：%s" % page.errors()

    @P2
    @allure.story("UI-AUTH-14 重复邮箱注册被拒")
    @allure.severity(allure.severity_level.MINOR)
    def test_duplicate_email(self, anonymous, sessions):
        used_email = sessions["student"].get("/auth/me/")["email"]
        page = RegisterPage(anonymous)
        page.fill(config.tag("dup%d" % int(time.time() % 100000)),
                  used_email, "自动化学生", config.PASSWORD, grade_text="2026级")
        page.submit()

        assert "/register/" in anonymous.current_url, "重复邮箱不应注册成功"
        assert any("该邮箱已被注册" in e for e in page.errors()), \
            "重复邮箱提示不符：%s" % page.errors()

    @P2
    @allure.story("UI-AUTH-15 两次密码不一致被拦")
    @allure.severity(allure.severity_level.MINOR)
    def test_password_mismatch(self, anonymous):
        uname = config.tag("mis%d" % int(time.time() % 100000))
        page = RegisterPage(anonymous)
        page.fill(uname, uname.lower() + "@test.local", "自动化学生",
                  config.PASSWORD, grade_text="2026级")
        page.type(page.L["password2"], "Exam@654321")
        page.submit()

        assert "/register/" in anonymous.current_url, "密码不一致不应注册成功"
        assert any("两次输入的密码不一致" in e for e in page.errors()), \
            "密码不一致提示不符：%s" % page.errors()

    @P2
    @allure.story("UI-AUTH-16 弱密码触发密码强度校验")
    @allure.severity(allure.severity_level.MINOR)
    def test_weak_password(self, anonymous):
        uname = config.tag("weak%d" % int(time.time() % 100000))
        page = RegisterPage(anonymous)
        page.fill(uname, uname.lower() + "@test.local", "自动化学生",
                  "123456", grade_text="2026级")
        page.submit()

        assert "/register/" in anonymous.current_url, "弱密码不应注册成功"
        errs = " | ".join(page.errors())
        assert ("常见" in errs) or ("只包含数字" in errs), \
            "弱密码没有触发强度校验：%s" % errs


@allure.feature(FEATURE)
class TestLoginInteraction:
    """登录页的交互细节：记住我、密码可见性。"""

    @P2
    @allure.story("UI-AUTH-17 勾选「记住我」登录后会话保持")
    @allure.severity(allure.severity_level.MINOR)
    def test_remember_me(self, anonymous):
        """「记住我」的真实差异在 **sessionid 的过期时间**：
        勾选 → 持久 cookie（带 expiry，默认 2 周）；不勾选 → 会话 cookie（无 expiry，
        关浏览器即失效）。只验「刷新后还登录」是验不出来的——两种都还登录着。
        """
        page = LoginPage(anonymous)
        page.login(config.ACCOUNTS["student"], config.PASSWORD, remember=True)
        cookies = {c["name"]: c for c in anonymous.get_cookies()}
        assert cookies.get("sessionid", {}).get("expiry"), \
            "勾选记住我后 sessionid 仍是会话 cookie（没有 expiry）"
        anonymous.refresh()
        assert "/login/" not in anonymous.current_url, "勾选记住我后刷新掉登录态"

        anonymous.delete_all_cookies()
        page.login(config.ACCOUNTS["student"], config.PASSWORD, remember=False)
        cookies = {c["name"]: c for c in anonymous.get_cookies()}
        assert "expiry" not in cookies.get("sessionid", {}), \
            "未勾选记住我时 sessionid 不应带 expiry（应为浏览器会话级）"
        anonymous.refresh()
        assert "/login/" not in anonymous.current_url, "未勾选记住我时刷新掉登录态"

    @P2
    @allure.story("UI-AUTH-18 密码可见性切换按钮生效")
    @allure.severity(allure.severity_level.MINOR)
    def test_toggle_password(self, anonymous):
        page = LoginPage(anonymous)
        page.open()
        page.type(page.L["password"], config.PASSWORD)
        assert page.password_input_type() == "password", "密码框初始应为密文"

        page.click(page.L["toggle"])
        page.wait.until(lambda d: page.password_input_type() == "text",
                        message="点击眼睛图标后密码没有变明文")
        assert page.attr(page.L["password"], "value") == config.PASSWORD, \
            "切到明文后密码值被改动"

        page.click(page.L["toggle"])
        page.wait.until(lambda d: page.password_input_type() == "password",
                        message="再次点击后密码没有恢复密文")
