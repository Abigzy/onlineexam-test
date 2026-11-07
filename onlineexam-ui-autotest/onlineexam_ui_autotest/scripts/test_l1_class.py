# -*- coding: utf-8 -*-
"""L1/L2 学生·班级：6 条（docs/03 UI-CLS-02 ~ 07，P1 4 / P2 2）。

`UI-CLS-01`（班级列表加载）已在 L0 冒烟覆盖。

三条实测口径（2026-11-05）：
  1. 学生越权访问别的班**不是 404**，而是弹 `#permModal`：`#c-name` 被改写成
     「权限不足」，底部按钮是**「返回班级列表」**（用例原文写的「知道了」不存在）。
  2. 新建班级弹窗里的年级是 `input`（不是 select），类型用两个 radio 切换；
     名称为空时不写内联错误，而是 toast「请填写班级名称」且弹窗不关。
  3. 删除班级走原生 `window.confirm`，确认后 600ms 才跳回列表 —— 必须先覆盖 confirm
     再点，否则 driver 直接抛 `UnexpectedAlertPresentException`。
"""
import re
import time

import allure
import pytest

import config
from pages.student_pages import ClassroomDetailPage, ClassroomPage

P1 = pytest.mark.p1
P2 = pytest.mark.p2
FEATURE = "04 学生·班级"


@allure.feature(FEATURE)
class TestStudentClassroom:
    """学生视角：本班详情与非本班越权。"""

    @P1
    @allure.story("UI-CLS-02 学生进入本班详情看到成员名单")
    @allure.severity(allure.severity_level.NORMAL)
    def test_own_class_detail(self, as_student, sessions):
        mine = sessions["student"].get("/classrooms/").get("results") or []
        assert mine, "用例前置：演示学生应至少在一个班级里"
        own = mine[0]

        page = ClassroomPage(as_student).open()
        assert page.card_count() >= 1, "学生班级列表为空"
        assert not page.visible(page.L["create"]), "学生不该看到「新建班级」按钮"

        detail = page.open_by_id(own["id"])
        assert detail.name_text() == own["name"], \
            "详情页班级名不符：%r vs %r" % (detail.name_text(), own["name"])
        # 等成员区两个接口都回来（名字就绪 ≠ 成员列表就绪），见 wait_members 注释
        count, rows = detail.wait_members()
        assert count > 0, "本班成员数为 0（前置不成立）"
        assert count == rows, "成员数与名单行数不一致：%s vs %s" % (count, rows)

        me = sessions["student"].get("/auth/me/")
        names = " ".join(detail.member_texts())
        assert (me["student_no"] in names) or (me["real_name"] in names), \
            "名单里找不到本人（学号 %s / 姓名 %s）" % (me["student_no"], me["real_name"])
        assert not detail.visible(detail.L["add_btn"]), "学生不该看到「添加学生」"
        assert not detail.visible(detail.L["delete_class"]), "学生不该看到「删除班级」"

    @P1
    @allure.story("UI-CLS-03 学生访问非本班详情弹出权限不足")
    @allure.severity(allure.severity_level.NORMAL)
    def test_other_class_blocked(self, as_student, sessions):
        mine = {c["id"] for c in (sessions["student"].get("/classrooms/").get("results") or [])}
        others = [c for c in (sessions["teacher"].get("/classrooms/", params={"page_size": 100})
                              .get("results") or []) if c["id"] not in mine]
        assert others, "用例前置：需要存在一个学生不在其中的班级"
        other = others[0]

        detail = ClassroomPage(as_student).open_by_id(other["id"])
        detail.wait_for(lambda d: detail.perm_modal_visible(), message="越权访问没有弹权限不足")
        text = detail.perm_modal_text()
        assert "权限不足" in text, "弹窗文案不含「权限不足」：%r" % text[:120]
        assert "任课教师或班主任" in text, "弹窗没有说明越权原因：%r" % text[:160]
        assert detail.member_rows() == 0, "越权页面仍然渲染了成员名单（数据泄露）"
        assert other["name"] not in " ".join(detail.member_texts()), \
            "越权页面出现了该班信息"

        page = detail.leave_by_perm_button()
        assert page.url.rstrip("/") == config.BASE_URL + "/classrooms", \
            "点「返回班级列表」没有回到列表，实际 %s" % page.url


@allure.feature(FEATURE)
class TestTeacherClassroom:
    """教师视角：新建、加人、删除、必填校验。"""

    @P1
    @allure.story("UI-CLS-04 教师新建班级后列表出现该班级")
    @allure.severity(allure.severity_level.NORMAL)
    def test_create_class(self, as_teacher, sessions):
        name = config.tag("CLS%d" % (int(time.time()) % 100000))
        page = ClassroomPage(as_teacher).open()
        before = page.card_count()
        try:
            page.create(name, grade="2026", admin_type=True)
            assert page.card_count() == before + 1, \
                "新建后卡片数没有 +1（%d → %d）" % (before, page.card_count())
            assert name in page.card_names(), "列表里找不到新建的班级：%s" % name
            assert "加载中" not in (page.js_text("#class-list") or ""), "列表残留加载中"
        finally:
            for row in (sessions["teacher"].get(
                    "/classrooms/", params={"page_size": 100}).get("results") or []):
                if row.get("name") == name:
                    sessions["teacher"].delete("/classrooms/%s/" % row["id"])

    @P1
    @allure.story("UI-CLS-05 班级详情添加学生后名单与人数同步")
    @allure.severity(allure.severity_level.NORMAL)
    def test_add_student(self, as_teacher, new_classroom, class_student):
        assert re.match(r"^\d{8}$", class_student["student_no"]), \
            "用例前置：学生学号不是 8 位数字（%r）" % class_student["student_no"]

        detail = ClassroomPage(as_teacher).open_by_id(new_classroom["id"])
        assert detail.member_count() == 0, "新建班级不应已有成员"
        detail.add_student_by_no(class_student["student_no"])

        assert detail.member_count() == 1, "人数没有变成 1：%s" % detail.member_count()
        assert detail.member_rows() == 1, "名单行数没有变成 1：%s" % detail.member_rows()
        rows = " ".join(detail.member_texts())
        assert class_student["student_no"] in rows, "名单里没有新加入的学号"
        assert class_student["real_name"] in rows, "名单里没有新加入的姓名"
        assert not detail.visible(detail.L["add_modal"]), "加完学生后导入弹窗没有关闭"

    @P2
    @allure.story("UI-CLS-06 新建班级必填项为空保存被拦")
    @allure.severity(allure.severity_level.MINOR)
    def test_create_empty_name(self, as_teacher):
        page = ClassroomPage(as_teacher).open()
        before = page.card_count()

        page.submit_empty_name()
        assert page.visible(page.L["modal"]), "名称为空时弹窗被关掉了（应保持打开）"
        assert page.card_count() == before, "名称为空却新建出了班级"
        assert page.toast_text() and "班级名称" in page.toast_text(), \
            "没有给出「请填写班级名称」提示：%r" % page.toast_text()

    @P2
    @allure.story("UI-CLS-07 删除班级需二次确认且删除后从列表消失")
    @allure.severity(allure.severity_level.MINOR)
    def test_delete_class(self, as_teacher, new_classroom):
        detail = ClassroomPage(as_teacher).open_by_id(new_classroom["id"])
        assert detail.name_text() == new_classroom["name"], "详情页不是要删的那个班"

        page = detail.delete_class(confirm=True)
        assert page.url.rstrip("/") == config.BASE_URL + "/classrooms", \
            "删除后没有跳回班级列表，实际 %s" % page.url
        page.wait_for(lambda d: new_classroom["name"] not in page.card_names(),
                      message="删除后列表里仍有该班级")
