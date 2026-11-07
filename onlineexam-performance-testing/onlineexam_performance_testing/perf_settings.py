"""压测环境配置（属于测试资产，放在压测工程里，不写进被测项目）。

由 ``scripts/serve.py`` 通过 ``DJANGO_SETTINGS_MODULE=perf_settings`` 加载，
加载时被测系统根目录（``OE_PROJECT``，默认 ``D:/OnlineExam``）与压测工程根目录都在 ``sys.path`` 上。

与 ``OnlineExam.settings.development`` 的区别只有三点：

1. ``DEBUG = False``：开发配置开着 DEBUG，Django 会把每条 SQL 存进
   ``connection.queries``，压测时既占内存又偏慢，且让「改了什么导致变慢」失去可比性。
2. 收窄 ``ALLOWED_HOSTS``：压测只从本机发起。
3. 去掉 DRF 浏览器调试渲染器、日志降到 WARNING：少一次内容协商、少大量 IO。
"""

from OnlineExam.settings.development import *  # noqa: F401,F403

import os as _os

DEBUG = False

# 调优实验开关：数据库连接复用。
# 默认 0 = 与线上/开发配置一致，每个请求结束后关闭连接。
# 本项目 MySQL 新建连接实测 52-69ms（skip_name_resolve=OFF 触发反向域名解析），
# 而连接池复用后单条查询仅 0.1ms —— 这是当前最贵的固定开销。
DATABASES["default"]["CONN_MAX_AGE"] = int(_os.environ.get("PERF_CONN_MAX_AGE", "0"))  # noqa: F405

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "apps.common.renderers.UnifiedJSONRenderer",
)

LOGGING["root"]["level"] = "WARNING"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "WARNING"  # noqa: F405
