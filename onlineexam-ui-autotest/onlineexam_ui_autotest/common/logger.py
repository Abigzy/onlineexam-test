# -*- coding: utf-8 -*-
"""日志：控制台 + 按运行时间落文件，便于失败复盘时对齐时间线。"""
import logging
import os
import sys

import config

_FMT = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
_configured = False


def _init():
    global _configured
    if _configured:
        return
    path = os.path.join(config.LOG_DIR, "ui_%s.log" % config.RUN_TAG)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter(_FMT, datefmt="%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)
    _configured = True


def get(name="ui"):
    _init()
    return logging.getLogger(name)
