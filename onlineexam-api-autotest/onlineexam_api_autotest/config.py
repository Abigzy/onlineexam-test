# -*- coding: utf-8 -*-
"""项目级常量（对齐 IHRM 的 config.py 用法）。

IHRM 里 config.py 只放 `BASE_DIR` 和少量常量；这里保留同样的入口，
运行期的完整配置（超时、账号池、环境地址）仍在 `common/config.py`。
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#: 被测服务地址，可用环境变量覆盖
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8777").rstrip("/")

#: 演示账号（口令统一，演示库约定）
PASSWORD = "Exam@123456"
ADMIN = "admin"
TEACHER = "teacher"
OS_TEACHER = "os_teacher"
STUDENT = "student"
STUDENT2 = "s_002"

#: 造数前缀（所有测试数据以此开头，便于识别与清理）
TEST_PREFIX = "at_"

#: 目录
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "log")
REPORT_DIR = os.path.join(BASE_DIR, "report")
