# -*- coding: utf-8 -*-
"""日志初始化（对齐 IHRM 的 common/logging_use.py）。

与 IHRM 的差异只有一处：加了"已初始化"判断。
IHRM 在类体里调用一次没问题；我们用例分散在多个文件，重复调用会挂多个 handler，
导致一条日志打印 N 遍。
"""
import logging
import logging.handlers

from config import LOG_DIR


def init_log_config(filename: str = None, when: str = "midnight",
                    interval: int = 1, backup_count: int = 7):
    """按天切分日志，同时输出到控制台与文件。"""
    logger = logging.getLogger()
    if getattr(logger, "_at_initialized", False):
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(filename)s(%(funcName)s:%(lineno)d)] - %(message)s"
    )

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename or f"{LOG_DIR}/onlineexam.log",
        when=when, interval=interval, backupCount=backup_count, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(stream)
    logger.addHandler(file_handler)

    # 第三方库的 DEBUG 日志（urllib3 每次请求都打一行）会淹没用例输出
    for noisy in ("urllib3", "requests"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger._at_initialized = True
    return logger
