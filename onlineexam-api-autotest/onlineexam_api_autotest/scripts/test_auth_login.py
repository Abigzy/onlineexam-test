# -*- coding: utf-8 -*-
"""登录用例（JSON 数据驱动写法）。

数据在 data/login_data.json：一条记录 = 一条用例，
字段顺序 desc, req_data, status_code, code, message 与 parametrize 一一对应。
"""
import logging

import pytest

from common.assert_tools import CommonAssert
from common.client import ApiClient
from common.get_data import read_login_data
from common.logging_use import init_log_config
from encap_api.auth_user_api import AuthApi

pytestmark = pytest.mark.l0

init_log_config()


class TestLogin(object):

    @pytest.mark.parametrize("desc,req_data,status_code,code,message", read_login_data())
    def test_login_collection(self, desc, req_data, status_code, code, message):
        logging.info("正在测试：%s", desc)
        # 每次用独立 client（不带 token），确保走的是真正的登录接口
        api = AuthApi(ApiClient(label=f"login:{desc}"))
        res = api.login(req_data["username"], req_data["password"])
        CommonAssert.common_assert(res, status_code, code, message)
