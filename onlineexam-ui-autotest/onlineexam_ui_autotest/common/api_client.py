# -*- coding: utf-8 -*-
"""接口会话：用页面表单登录拿到 sessionid，再用同一会话调 /api/v1/ 造数据。

为什么不用 JWT：页面层与接口层共用 Django session（SessionAuthentication 已开启），
一条会话既能开浏览器也能造数，省掉两套凭据的同步问题。

两个必踩的坑（步骤 5 实测）：
    1. trust_env=False —— 否则 requests 走系统代理，造数请求会 502/404；
    2. 非安全方法必须带 X-CSRFToken + Referer —— SessionAuthentication 强制 CSRF。
"""
import re

import requests

import config


class ApiError(AssertionError):
    """接口返回 code != 0 时抛出，带上报文便于定位。"""


class ApiSession:
    def __init__(self, username, password=None):
        self.username = username
        self.password = password or config.PASSWORD
        self.session = requests.Session()
        self.session.trust_env = False
        self.login()

    # ------------------------------------------------------------ 登录
    def login(self):
        base = config.BASE_URL
        r = self.session.get(base + "/login/", timeout=30)
        assert r.status_code == 200, "登录页打不开：HTTP %s" % r.status_code
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
        token = m.group(1) if m else self.session.cookies.get("csrftoken", "")
        r = self.session.post(
            base + "/login/",
            data={"csrfmiddlewaretoken": token, "username": self.username,
                  "password": self.password, "next": ""},
            headers={"Referer": base + "/login/"},
            allow_redirects=False, timeout=30)
        assert r.status_code in (301, 302), "登录失败：HTTP %s" % r.status_code
        self.session.headers.update({
            "X-CSRFToken": self.session.cookies.get("csrftoken", ""),
            "Referer": base + "/",
        })
        return self

    @property
    def session_id(self):
        return self.session.cookies.get("sessionid")

    # ------------------------------------------------------------ 请求
    def request(self, method, path, expect=(200, 201, 204), **kwargs):
        url = config.API_URL + path if path.startswith("/") else path
        r = self.session.request(method, url, timeout=60, **kwargs)
        try:
            body = r.json()
        except ValueError:
            raise ApiError("%s %s 返回非 JSON：HTTP %s %s" % (
                method, path, r.status_code, r.text[:200]))
        if r.status_code not in expect:
            raise ApiError("%s %s 失败：HTTP %s code=%s message=%s" % (
                method, path, r.status_code, body.get("code"), body.get("message")))
        if body.get("code") not in (0, None):
            raise ApiError("%s %s 业务错误：code=%s message=%s" % (
                method, path, body.get("code"), body.get("message")))
        return body.get("data")

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, json=None, **kw):
        return self.request("POST", path, json=json or {}, **kw)

    def patch(self, path, json=None, **kw):
        return self.request("PATCH", path, json=json or {}, **kw)

    def delete(self, path, expect=(200, 204), **kw):
        return self.request("DELETE", path, expect=expect, **kw)
