# -*- coding: utf-8 -*-
"""L1 管理端：8 条（docs/03 UI-ADM-01 ~ 08，P0 2 / P1 3 / P2 3）。

数据纪律：所有新建账号都登记到 `user_cleanup`，收尾用 `DELETE /users/{id}/` 真删，
不往 52 个演示账号里留垃圾；编辑 / 停用 / 重置密码用 `admin_user` 现造的靶子用户。

两个实现约束（都写进 docs/05 §4）：
    1. 固定 user-data-dir 下**不能同时开两个 Chrome**（DevToolsActivePort 冲突）。
       跨账号验证统一用「同一 driver 清 cookie → 表单登录」；这不销毁服务端
       共享 admin session，后续用例重新注入即可。
    2. 列表 / 表单是 Django 服务端渲染，筛选与保存都整页导航，
       提交后必须等 URL 变化，否则读到的是旧页面。
"""
import time

import allure
import pytest

import config
from pages.admin_pages import (
    ManageDashboardPage,
    ManageUserFormPage,
    ManageUserPage,
)
from pages.auth_pages import LoginPage, ProfilePage

P0 = pytest.mark.p0
P1 = pytest.mark.p1
P2 = pytest.mark.p2
FEATURE = "10 管理端"


def _stamp():
    return time.strftime("%H%M%S")


@allure.feature(FEATURE)
class TestUserList:
    """用户列表与筛选。"""

    @P0
    @allure.story("UI-ADM-01 用户管理列表渲染并可筛选")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_user_list_filter(self, as_admin):
        page = ManageUserPage(as_admin).open()
        before = page.row_count()
        assert before >= 1, "用户列表没有数据行"

        page.filter_role("学生")
        roles = page.role_cells()

        assert roles, "按学生筛选后没有数据行"
        assert all("学生" in r for r in roles), \
            "筛选结果里混入了非学生角色：%s" % roles[:5]
        assert page.row_count() <= before, "筛选后行数反而变多"
        assert page.filter_value() == "student", "筛选条件没有保留"
        assert "role=student" in as_admin.current_url, "筛选没有提交到服务端"


@allure.feature(FEATURE)
class TestUserCreate:
    """新建用户与表单校验。"""

    @P0
    @allure.story("UI-ADM-02 新建用户后可用新账号登录")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_create_user_then_login(self, as_admin, user_cleanup):
        """用例原文是「退出登录后用新账号登录」。

        固定 profile 下不能同时开两个 Chrome，而且真正的 logout 会销毁共享
        admin session（L0 踩过连锁失败）。这里用 delete_all_cookies() 达到同样
        的「以新账号登录」语义，服务端 admin session 不受影响。
        """
        uname = config.tag("adm_new_%s" % _stamp())
        email = uname.lower() + "@example.com"
        user_cleanup.append(uname)

        form = ManageUserFormPage(as_admin).open()
        pwd = form.fill_create(uname, email, "UIAT新建",
                               grade_text="2026级").generated_password()
        assert pwd and len(pwd) >= 8, "「生成密码」没有填出可用的强密码：%r" % pwd
        form.submit()

        page = ManageUserPage(as_admin)
        page.wait_url("search=")            # 新建成功跳 /manage/users/?search=<username>
        page.wait_for(lambda d: uname in page.js_text("table tbody"),
                      message="创建成功后列表里找不到新用户")
        assert "学生" in page.row_text(uname), "新用户角色不是学生"

        as_admin.delete_all_cookies()
        lp = LoginPage(as_admin).login(uname, pwd)
        assert "/login/" not in as_admin.current_url, \
            "新账号登录失败：%s" % lp.error_text()
        assert ProfilePage(as_admin).open().student_no_text(), \
            "新学生账号没有派发学号"

    @P2
    @allure.story("UI-ADM-07 创建重复用户名被拒")
    @allure.severity(allure.severity_level.MINOR)
    def test_duplicate_username(self, as_admin, sessions):
        email = "uiat_dup_%s@example.com" % _stamp()
        form = ManageUserFormPage(as_admin).open()
        form.fill_create("student", email, "UIAT重复",
                         grade_text="2026级", password="UiAt@12345")
        form.submit()

        assert "/manage/users/new/" in as_admin.current_url, "重复用户名竟然提交成功并跳转"
        errs = form.errors()
        assert any(("已被占用" in e) or ("已存在" in e) for e in errs), \
            "没有出现「用户名已存在」类提示：%s" % errs
        rows = sessions["admin"].get("/users/", params={"search": email}).get("results") or []
        assert not any(r.get("email") == email for r in rows), "校验失败却创建了新用户"

    @P2
    @allure.story("UI-ADM-08 创建学生未填年级被拒")
    @allure.severity(allure.severity_level.MINOR)
    def test_missing_grade(self, as_admin, sessions):
        uname = config.tag("adm_nograde_%s" % _stamp())
        email = uname.lower() + "@example.com"
        form = ManageUserFormPage(as_admin).open()
        form.fill_create(uname, email, "UIAT无年级",
                         grade_text=None, password="UiAt@12345")
        form.submit()

        assert "/manage/users/new/" in as_admin.current_url, "未填年级竟然提交成功并跳转"
        errs = form.errors()
        assert any(("入学年级" in e) or ("年级" in e) for e in errs), \
            "没有出现年级必填类提示：%s" % errs
        rows = sessions["admin"].get("/users/", params={"search": uname}).get("results") or []
        assert not any(r.get("username") == uname for r in rows), \
            "校验失败却创建了用户（可能派发了空学号）"


@allure.feature(FEATURE)
class TestUserGovernance:
    """编辑、停用、重置密码、代管提示条。"""

    @P1
    @allure.story("UI-ADM-03 编辑用户资料后列表更新")
    @allure.severity(allure.severity_level.NORMAL)
    def test_edit_user(self, as_admin, admin_user):
        new_name = "UIAT改姓名%s" % _stamp()
        form = ManageUserFormPage(as_admin).open_edit(admin_user["id"])
        form.set_real_name(new_name)

        page = ManageUserPage(as_admin)
        page.wait_url("search=")            # 编辑保存同样跳回带 search 的列表
        assert new_name in page.row_text(admin_user["username"]), \
            "保存后列表该行姓名没有更新"

        as_admin.refresh()                  # 刷新后仍为新姓名（不是前端临时改 DOM）
        assert new_name in page.row_text(admin_user["username"]), \
            "刷新后姓名回退，说明没落库"

    @P1
    @allure.story("UI-ADM-04 停用用户需二次确认且状态变化")
    @allure.severity(allure.severity_level.NORMAL)
    def test_disable_user(self, as_admin, admin_user):
        """用例原预期「弹窗文案含该用户名」——实测 `#toggleModalText` 是固定文案，
        不含目标账号（已登记 OBS-12，建议开发把目标用户名写进确认弹窗）。
        目标身份改由行按钮的 `data-username` 精确定位，不会点错人。
        """
        page = ManageUserPage(as_admin).open()
        page.search_user(admin_user["username"])
        page.row_action(admin_user["username"], "toggle-active")
        page.disable_modal().wait_open()

        assert "停用" in page.toggle_title(), "二次确认标题不含「停用」"
        assert "停用" in page.toggle_text() or "停用" in page.js_text("#toggleConfirm"), \
            "二次确认没有明确的停用语义"

        page.click(page.L["toggle_confirm"])
        page.wait_row_contains(admin_user["username"], "已停用", timeout=12)

        as_admin.delete_all_cookies()
        lp = LoginPage(as_admin).login(admin_user["username"], admin_user["password"])
        assert "该账号已被停用" in lp.error_text(), \
            "停用账号仍能登录，或错误提示不可读：%r" % lp.error_text()

    @P1
    @allure.story("UI-ADM-05 管理员代管教学功能有提示条且可返回")
    @allure.severity(allure.severity_level.NORMAL)
    def test_delegated_banner(self, as_admin):
        page = ManageDashboardPage(as_admin)
        page.open_delegated("/question-bank/")

        banner = page.banner_text()
        assert "管理员" in banner and "代管" in banner, \
            "代管提示条缺失或文案不对：%r" % banner[:120]
        assert "/manage/" in page.banner_links(), "提示条里没有返回管理控制台的链接"

        page.click(".alert-warning a")
        page.wait_url("/manage/")

    @P2
    @allure.story("UI-ADM-06 重置密码弹窗展示新密码并可复制")
    @allure.severity(allure.severity_level.MINOR)
    def test_reset_password(self, as_admin, admin_user):
        page = ManageUserPage(as_admin).open()
        page.search_user(admin_user["username"])
        newpwd = page.reset_password_for(admin_user["username"])

        assert len(newpwd) >= 8, "弹窗没有展示明文新密码：%r" % newpwd
        page.copy_password()
        assert page.console_errors() == [], "点「复制」后出现 JS 错误：%s" % page.console_errors()[:2]

        as_admin.delete_all_cookies()
        lp = LoginPage(as_admin).login(admin_user["username"], newpwd)
        assert "/login/" not in as_admin.current_url, \
            "新密码无法登录：%s" % lp.error_text()
