#!/usr/bin/env python
"""准备压测数据：调用被测项目自己的 seed 脚本，再补齐压测必需、但 seed 没管的两件事。

    # 全新准备（重建 130 个学生 + 1 份 20 题卷 + 1 场考试，并建立班级关系）
    .venv/Scripts/python.exe scripts/seed.py --students 130

    # 只续期（隔天继续跑时，考试时间窗已过，跑这个即可）
    .venv/Scripts/python.exe scripts/seed.py --refresh-only

    # 每轮压测前清空作答记录（避免 max_attempts 被打满导致 104xx 业务失败）
    .venv/Scripts/python.exe scripts/seed.py --refresh-only --reset-attempts

为什么需要补两步（**不是**急着改被测项目）：

1. **班级关系**：``open_to_all`` 的教师考试只对「该教师可管理班级里的学生」开放
   （``apps/exam/models.py::Exam.open_to_all_scope``）。seed 建了 130 个学生却没有班级，
   结果学生能登录、``/exams/`` 却返回空，``/exams/{id}/start/`` 直接 404。
   这属于种子数据缺环，不是性能问题，所以补在压测侧，被测项目一行不动。
2. **max_attempts 上限**：seed 给的是 200。100 并发跑 90 秒，一个学生被复用几十次，
   很容易打满，失败原因会被业务规则污染。压测把它抬到 1000。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
# 被测系统根目录：默认 D:/OnlineExam，可用环境变量 OE_PROJECT 覆盖
PROJECT = Path(os.environ.get("OE_PROJECT", "D:/OnlineExam"))
PY = PROJECT / ".venv" / "Scripts" / "python.exe"
EXPECTED_DB = "online_exam_perf"
CLASS_NAME = "压测教学班"


def bootstrap() -> None:
    sys.path.insert(0, str(PROJECT))
    sys.path.insert(0, str(WS))
    os.environ["DJANGO_SETTINGS_MODULE"] = "perf_settings"
    os.environ.setdefault("DB_NAME", EXPECTED_DB)
    os.environ["AI_PROVIDER"] = "mock"


def run_project_seed(students: int) -> None:
    env = os.environ.copy()
    env.update(
        DJANGO_SETTINGS_MODULE="perf_settings",
        PYTHONPATH=os.pathsep.join([str(WS), str(PROJECT)]),
        DB_NAME=EXPECTED_DB,
    )
    cmd = [str(PY), str(PROJECT / "scripts" / "perf_seed.py"), "setup", "--students", str(students)]
    print(f"[seed] {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=str(PROJECT), env=env, check=True)


def prepare_data(*, reset_attempts: bool) -> dict:
    """班级 + 考试时间窗 + 次数上限（+ 可选清作答）。"""
    from datetime import timedelta

    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.classroom.models import Classroom
    from apps.exam.models import Exam, ExamAttempt

    User = get_user_model()
    students = list(User.objects.filter(username__startswith="perf_stu_").order_by("username"))
    teacher = User.objects.filter(username="perf_teacher").first()
    exam = Exam.objects.order_by("pk").first()
    if not (students and teacher and exam):
        raise SystemExit("[FATAL] 种子数据不完整，先跑 --students N 做一次完整准备")

    classroom = Classroom.objects.filter(name=CLASS_NAME).first()
    if classroom is None:
        classroom = Classroom.objects.create(
            name=CLASS_NAME,
            grade_year="2026",
            subject="性能测试",
            head_teacher=teacher,
            created_by=teacher,
            description="模块 11 压测专用班级，勿用于演示。",
        )
    classroom.is_active = True
    classroom.head_teacher = teacher
    classroom.created_by = teacher
    classroom.save(update_fields=["is_active", "head_teacher", "created_by", "updated_at"])
    classroom.teachers.add(teacher)
    classroom.students.set(students)

    now = timezone.now()
    exam.status = "published"
    exam.start_time = now - timedelta(minutes=5)
    exam.end_time = now + timedelta(hours=6)
    exam.max_attempts = 1000
    exam.save(update_fields=["status", "start_time", "end_time", "max_attempts", "updated_at"])

    removed = 0
    if reset_attempts:
        removed = ExamAttempt.objects.filter(exam=exam).delete()[0]

    return {
        "db": EXPECTED_DB,
        "exam_id": exam.pk,
        "paper_id": exam.paper_id,
        "classroom_id": classroom.pk,
        "students": len(students),
        "classroom_students": classroom.students.count(),
        "attempts_left": ExamAttempt.objects.filter(exam=exam).count(),
        "deleted_rows": removed,
        "window": f"{timezone.localtime(exam.start_time):%m-%d %H:%M} → "
        f"{timezone.localtime(exam.end_time):%H:%M}",
    }


def reissue_tokens() -> int:
    """重新离线签发 access token。

    simplejwt 的 access token 默认只有 60 分钟，隔一段时间再跑压测，旧 token 全部 401
    （表现为一堆「此令牌对任何类型的令牌无效」）。这里按现有账号重签一遍，
    比每次都重建数据轻得多；签名逻辑与被测项目的 perf_seed 一致，避免两套真源。
    """
    import json as _json

    from django.contrib.auth import get_user_model
    from rest_framework_simplejwt.tokens import RefreshToken

    User = get_user_model()
    payload = {}
    for user in User.objects.filter(username__startswith="perf_").order_by("username"):
        payload[user.username] = {
            "user_id": user.pk,
            "role": user.role,
            "access": str(RefreshToken.for_user(user).access_token),
        }
    target = PROJECT / "scripts" / ".perf_tokens.json"
    target.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(payload)


def copy_artifacts() -> None:
    """把种子产物复制到压测工程内，让脚本不依赖被测项目的相对路径。"""
    (WS / "scripts").mkdir(parents=True, exist_ok=True)
    for name in (".perf_meta.json", ".perf_tokens.json"):
        src = PROJECT / "scripts" / name
        if src.exists():
            shutil.copy2(src, WS / "scripts" / name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=130, help="学生数量（并发上限要留余量）")
    ap.add_argument("--refresh-only", action="store_true", help="不重建库，只修班级/时间窗/上限")
    ap.add_argument("--reset-attempts", action="store_true", help="清空该考试的作答记录")
    args = ap.parse_args()

    if os.environ.get("DB_NAME", EXPECTED_DB) != EXPECTED_DB:
        print(f"[FATAL] 库名必须 {EXPECTED_DB}", file=sys.stderr)
        return 2

    if not args.refresh_only:
        run_project_seed(args.students)

    bootstrap()
    import django

    django.setup()
    info = prepare_data(reset_attempts=args.reset_attempts)
    reissued = reissue_tokens()
    copy_artifacts()
    info["tokens"] = reissued
    print("[seed] " + json.dumps(info, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
