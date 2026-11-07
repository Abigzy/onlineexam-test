# -*- coding: utf-8 -*-
"""运行配置：环境地址、账号池、超时与开关。

优先级：环境变量 > data/accounts.yaml > 默认值。
这样同一套脚本既能打本机 8777，也能通过 `API_BASE_URL=...` 指到测试环境。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "log"
REPORT_DIR = ROOT / "report"

for _d in (DATA_DIR, LOG_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

#: 被测服务地址（默认本机 8777，避开开发常用的 8000）
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8777").rstrip("/")

#: 单请求超时（秒）。AI 类接口单独放宽。
TIMEOUT = float(os.environ.get("API_TIMEOUT", "15"))
AI_TIMEOUT = float(os.environ.get("API_AI_TIMEOUT", "60"))

#: 本轮运行标识，用于造数与清理（at_<ts>）
RUN_TS = os.environ.get("API_RUN_TS") or datetime.now().strftime("%Y%m%d%H%M%S")
DATA_PREFIX = f"at_{RUN_TS}"

#: 是否允许写库造数（超时用例需要改 deadline_at）
ALLOW_DB_WRITE = os.environ.get("API_ALLOW_DB_WRITE", "0") == "1"


def _load_accounts() -> dict:
    path = DATA_DIR / "accounts.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return raw.get("accounts", {})


ACCOUNTS: dict = _load_accounts()


def account(alias: str) -> dict:
    """取账号配置，缺失时给出明确错误而不是 KeyError 堆栈。"""
    if alias not in ACCOUNTS:
        raise KeyError(f"账号别名 {alias!r} 未在 data/accounts.yaml 中定义")
    item = dict(ACCOUNTS[alias])
    item.setdefault("username", alias)
    item["password"] = os.environ.get(f"API_PWD_{alias.upper()}", item.get("password", ""))
    return item


def url(path: str) -> str:
    """拼绝对地址；允许传 /api/... 或 api/...。"""
    if path.startswith("http"):
        return path
    return f"{BASE_URL}/{path.lstrip('/')}"
