# -*- coding: utf-8 -*-
"""造数脚本：为接口自动化准备一套隔离的 fixtures。

为什么不用接口造数：
  * 建题→建卷→发布→建考→发布 这条链本身就是要测的对象，
    造数阶段再用它，失败时无法区分"环境没造好"还是"功能坏了"；
  * 直接调 service 层可以一次拿到全部 id，测试更稳定。
所以这里**只调 service，不写裸 SQL**，业务规则仍然生效。

运行（必须用被测项目的虚拟环境，并设置 OE_PROJECT 指向被测系统）：
    cd onlineexam-api-autotest/onlineexam_api_autotest
    .venv/Scripts/python.exe scripts/seed_env.py

产出：data/fixtures.json（测试只读这个文件，不关心数据库细节）
"""
from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

PROJECT = Path(os.environ.get("OE_PROJECT", "D:/OnlineExam"))
sys.path.insert(0, str(PROJECT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "OnlineExam.settings.development")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.common.constants import Difficulty, QuestionType  # noqa: E402
from apps.exam.models import Exam  # noqa: E402
from apps.exam.services import ExamService  # noqa: E402
from apps.papers.models import Paper  # noqa: E402
from apps.papers.services import PaperService  # noqa: E402
from apps.questions.models import KnowledgePoint, Question  # noqa: E402
from apps.questions.services import QuestionService  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "data" / "fixtures.json"
PASSWORD = "Exam@123456"
SUBJECT = "操作系统"
TS = timezone.now().strftime("%m%d%H%M%S")
PREFIX = f"at_{TS}"

User = get_user_model()


def log(msg):
    print(f"[seed] {msg}")


def ensure_teacher() -> dict:
    """专用教师：不设任教学科，避免 teacher_subject_scope 把 at_ 数据过滤掉。"""
    username = f"{PREFIX}_teacher"
    user = User.objects.create_user(
        username=username,
        password=PASSWORD,
        email=f"{username}@example.com",
        real_name="自动化教师",
        role="teacher",
        subject="",
        school="自动化测试",
    )
    log(f"教师 {username} id={user.id}")
    return {"id": user.id, "username": username, "password": PASSWORD}


def ensure_student(key: str, real_name: str) -> dict:
    username = f"{PREFIX}_{key}"
    student_no = f"2099{TS[-4:]}{1 if key == 'a' else 2}"
    user = User.objects.create_user(
        username=username,
        password=PASSWORD,
        email=f"{username}@example.com",
        real_name=real_name,
        role="student",
        student_no=student_no,
        school="自动化测试",
    )
    log(f"学生 {username} id={user.id} 学号={student_no}")
    return {"id": user.id, "username": username, "password": PASSWORD,
            "student_no": student_no, "real_name": real_name}


def make_kp(name: str, subject: str, parent=None) -> KnowledgePoint:
    kp = KnowledgePoint.objects.create(
        name=name, subject=subject, parent=parent, created_by=None,
    )
    log(f"知识点 {name} id={kp.id}")
    return kp


def make_question(*, key: str, qtype: str, stem: str, score: float,
                  answer: str = "", options: list | None = None,
                  kp_ids: list | None = None, active: bool = True) -> Question:
    data = {
        "type": qtype,
        "stem": stem,
        "subject": SUBJECT,
        "difficulty": Difficulty.MEDIUM,
        "score": score,
        "reference_answer": answer,
        "analysis": f"{PREFIX} 解析",
        "knowledge_point_ids": kp_ids or [],
        "is_active": active,
    }
    if options is not None:
        data["options"] = options
    question = QuestionService.save_question(data=dict(data), user=None)
    if not active:
        question.is_active = False
        question.save(update_fields=["is_active"])
    log(f"题目 {key} id={question.id} type={qtype} score={score}")
    return question


def make_paper(title: str, question_ids: list, *, pass_score=15, owner=None) -> Paper:
    paper = PaperService.create(data={
        "title": title,
        "subject": SUBJECT,
        "duration_minutes": 30,
        "pass_score": pass_score,
        "question_ids": question_ids,
    }, user=owner or User.objects.get(username="teacher"))
    log(f"试卷 {title} id={paper.id} 题数={paper.question_count} 总分={paper.total_score}")
    return paper


def make_exam(title: str, paper: Paper, students: list[int], *, show_score=False,
              max_attempts=2, force_submit=False, owner=None) -> Exam:
    now = timezone.now()
    exam = ExamService.create(data={
        "title": title,
        "paper": paper,
        "start_time": now - timedelta(minutes=5),
        # 窗口给足 3 小时：上午造数、下午再跑回归也不会因考试过期导致"假失败"
        "end_time": now + timedelta(hours=3),
        "duration_minutes": 20,
        "pass_score": 15,
        "max_attempts": max_attempts,
        "multiple_choice_policy": "strict",
        "detect_switch": True,
        "max_switch_count": 2,
        "auto_submit_on_limit": force_submit,
        "show_score_immediately": show_score,
        "participant_ids": students,
    }, user=owner or User.objects.get(username="teacher"))
    ExamService.change_status(exam, "published")
    log(f"考试 {title} id={exam.id} 状态={exam.status}")
    return exam


def cleanup_previous():
    """把上一轮的 at_ 数据下线：考试归档、学生停用，不物理删除。"""
    old_exams = Exam.objects.filter(title__startswith="at_").exclude(status="archived")
    count = old_exams.update(status="archived")
    old_users = User.objects.filter(username__startswith="at_").exclude(username=f"{PREFIX}%")
    users = old_users.update(is_active=False)
    log(f"清理历史 at_ 数据：考试归档 {count}，学生停用 {users}")


def main():
    cleanup_previous()

    teacher = ensure_teacher()
    teacher_user = User.objects.get(pk=teacher["id"])
    student_a = ensure_student("a", "自动化学生A")
    student_b = ensure_student("b", "自动化学生B")

    kp_root = make_kp(f"{PREFIX}_操作系统", SUBJECT)
    kp_child = make_kp(f"{PREFIX}_进程管理", SUBJECT, parent=kp_root)
    kp_net = make_kp(f"{PREFIX}_计算机网络", "计算机网络")

    q_single = make_question(
        key="single", qtype=QuestionType.SINGLE, stem=f"{PREFIX} 单选：进程调度单位",
        score=2, options=[
            {"label": "A", "content": "线程", "is_correct": True},
            {"label": "B", "content": "程序", "is_correct": False},
            {"label": "C", "content": "文件", "is_correct": False},
            {"label": "D", "content": "设备", "is_correct": False},
        ], kp_ids=[kp_child.id])
    q_multiple = make_question(
        key="multiple", qtype=QuestionType.MULTIPLE, stem=f"{PREFIX} 多选：哪些是进程状态",
        score=4, options=[
            {"label": "A", "content": "就绪", "is_correct": True},
            {"label": "B", "content": "运行", "is_correct": True},
            {"label": "C", "content": "阻塞", "is_correct": True},
            {"label": "D", "content": " sleeping", "is_correct": False},
        ], kp_ids=[kp_child.id])
    q_judge = make_question(
        key="judge", qtype=QuestionType.JUDGE, stem=f"{PREFIX} 判断：死锁一定由互斥引起",
        score=2, options=[
            {"label": "A", "content": "正确", "is_correct": True},
            {"label": "B", "content": "错误", "is_correct": False},
        ], kp_ids=[kp_child.id])
    q_fill = make_question(
        key="fill", qtype=QuestionType.FILL, stem=f"{PREFIX} 填空：栈的特点是____，队列的特点是____",
        score=4, answer="后进先出\n先进先出", kp_ids=[kp_child.id])
    q_short = make_question(
        key="short", qtype=QuestionType.SHORT, stem=f"{PREFIX} 简答：简述进程与线程的区别",
        score=10, answer="进程是资源分配单位，线程是调度单位；线程共享进程地址空间。",
        kp_ids=[kp_child.id])
    q_essay = make_question(
        key="essay", qtype=QuestionType.ESSAY, stem=f"{PREFIX} 论述：论述死锁的四个必要条件",
        score=10, answer="互斥、请求与保持、不可剥夺、循环等待。", kp_ids=[kp_child.id])
    q_inactive = make_question(
        key="inactive", qtype=QuestionType.SINGLE, stem=f"{PREFIX} 已停用题",
        score=2, options=[
            {"label": "A", "content": "A", "is_correct": True},
            {"label": "B", "content": "B", "is_correct": False},
        ], kp_ids=[kp_child.id], active=False)

    question_ids = [q.id for q in (q_single, q_multiple, q_judge, q_fill, q_short, q_essay)]
    paper_draft = make_paper(f"{PREFIX}_草稿卷", question_ids, owner=teacher_user)
    paper_published = make_paper(f"{PREFIX}_已发布卷", question_ids, owner=teacher_user)
    PaperService.change_status(paper_published, "published")
    log(f"试卷发布 id={paper_published.id} status={paper_published.status}")

    exam_normal = make_exam(f"{PREFIX}_正式考试", paper_published, [student_a["id"]],
                            max_attempts=100, owner=teacher_user)
    exam_score_open = make_exam(f"{PREFIX}_立即公布", paper_published, [student_a["id"]],
                                show_score=True, max_attempts=20, owner=teacher_user)
    exam_force = make_exam(f"{PREFIX}_强制交卷", paper_published, [student_a["id"]],
                           max_attempts=20, force_submit=True, owner=teacher_user)

    paper_questions = {
        str(pq.question_id): pq.id
        for pq in paper_published.paper_questions.all()
    }
    paper_questions_draft = {
        str(pq.question_id): pq.id
        for pq in paper_draft.paper_questions.all()
    }

    fixtures = {
        "run_ts": TS,
        "prefix": PREFIX,
        "subject": SUBJECT,
        "password": PASSWORD,
        "teacher": teacher,
        "students": {"a": student_a, "b": student_b},
        "knowledge": {"root": kp_root.id, "child": kp_child.id, "net": kp_net.id},
        "questions": {
            "single": q_single.id, "multiple": q_multiple.id, "judge": q_judge.id,
            "fill": q_fill.id, "short": q_short.id, "essay": q_essay.id,
            "inactive": q_inactive.id,
        },
        "answers": {"single": "A", "multiple": "ABC", "judge": "A",
                    "fill": "后进先出\n先进先出"},
        "scores": {"single": 2, "multiple": 4, "judge": 2, "fill": 4,
                   "short": 10, "essay": 10, "total": 32},
        "papers": {"draft": paper_draft.id, "published": paper_published.id},
        "paper_questions": paper_questions,
        "paper_questions_draft": paper_questions_draft,
        "exams": {"normal": exam_normal.id, "score_open": exam_score_open.id,
                  "force": exam_force.id},
    }
    FIXTURES.parent.mkdir(parents=True, exist_ok=True)
    FIXTURES.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"写出 {FIXTURES}")
    print(json.dumps(fixtures, ensure_ascii=False))


if __name__ == "__main__":
    main()
