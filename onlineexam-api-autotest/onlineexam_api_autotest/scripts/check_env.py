# -*- coding: utf-8 -*-
"""环境自检：一次跑完，输出可直接贴进《环境搭建》文档的结论。

用法：
    D:/OnlineExam/.venv/Scripts/python.exe scripts/check_env.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config                      # noqa: E402
from common.auth import TokenPool              # noqa: E402
from common.client import ApiClient            # noqa: E402
from encap_api.admin_api import SystemApi      # noqa: E402
from encap_api.auth_user_api import UserApi    # noqa: E402


def line(ok: bool, text: str) -> str:
    return f"[{'OK' if ok else 'FAIL'}] {text}"


def main() -> int:
    failed = 0
    anon = ApiClient(label="check")

    # 1) 健康检查
    health = anon.get("/api/health/")
    ok = health.status == 200 and health.code == 0 and (health.data or {}).get("database") == "up"
    failed += 0 if ok else 1
    print(line(ok, f"健康检查 {config.BASE_URL}/api/health/ -> "
                   f"{health.status} {health.data}"))

    # 2) 账号池
    pool = TokenPool()
    for alias in config.ACCOUNTS:
        try:
            client = pool.get(alias)
            me = client.get("/api/v1/auth/me/")
            ok = me.status == 200 and me.code == 0
            failed += 0 if ok else 1
            print(line(ok, f"账号 {alias:<10} 登录并读取 /me/ -> "
                           f"{me.status} role={(me.data or {}).get('role')}"))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(line(False, f"账号 {alias} 异常：{exc}"))

    # 3) 数据量（决定能跑哪些用例）
    admin = pool.get("admin")
    users = UserApi(admin).list(page_size=1)
    overview = SystemApi(admin).overview()
    print(line(users.code == 0, f"用户总数 = {(users.data or {}).get('count')}"))
    print(line(overview.code == 0, f"/system/overview/ -> {overview.status}"))

    teacher = pool.get("teacher")
    for label, path in (
        ("题库", "/api/v1/questions/?page_size=1"),
        ("试卷", "/api/v1/papers/?page_size=1"),
        ("考试", "/api/v1/exams/?page_size=1"),
    ):
        resp = teacher.get(path)
        ok = resp.status == 200 and resp.code == 0
        failed += 0 if ok else 1
        print(line(ok, f"{label}总数 = {(resp.data or {}).get('count')}"))

    # 4) 演示数据是否够跑只读冒烟
    student = pool.get("student")
    exams = student.get("/api/v1/exams/?page_size=1")
    attempts = student.get("/api/v1/attempts/?page_size=1")
    print(line(exams.code == 0, f"学生可见考试数 = {(exams.data or {}).get('count')}"))
    print(line(attempts.code == 0, f"学生作答数 = {(attempts.data or {}).get('count')}"))

    print("\n结论：" + ("环境可用" if failed == 0 else f"有 {failed} 项失败，先修环境"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
