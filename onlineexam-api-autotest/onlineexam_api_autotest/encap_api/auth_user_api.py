# -*- coding: utf-8 -*-
"""认证与用户管理接口封装（AUTH / USER）。"""
from __future__ import annotations

from .base import BaseApi


class AuthApi(BaseApi):
    def login(self, username: str, password: str):
        return self.post("/auth/login/", json={"username": username, "password": password})

    def register(self, **payload):
        return self.post("/auth/register/", json=payload)

    def refresh(self, refresh: str):
        return self.post("/auth/refresh/", json={"refresh": refresh})

    def logout(self, refresh: str):
        return self.post("/auth/logout/", json={"refresh": refresh})

    def me(self):
        return self.get("/auth/me/")

    def update_me(self, partial: bool = True, **payload):
        method = self.patch if partial else self.put
        return method("/auth/me/", json=payload)

    def change_password(self, old: str, new: str, confirm: str):
        return self.post("/auth/change-password/", json={
            "old_password": old, "new_password": new, "confirm_password": confirm,
        })


class UserApi(BaseApi):
    def list(self, **params):
        return self.get("/users/", params=params)

    def create(self, **payload):
        return self.post("/users/", json=payload)

    def detail(self, uid: int):
        return self.get(f"/users/{uid}/")

    def update(self, uid: int, partial: bool = True, **payload):
        method = self.patch if partial else self.put
        return method(f"/users/{uid}/", json=payload)

    def remove(self, uid: int):
        """删除用户（方法名不用 delete，避免覆盖基类的 HTTP 动词方法）。"""
        return self.client.delete(self._p(f"/users/{uid}/"))

    def reset_password(self, uid: int, new_password: str | None = None):
        body = {"new_password": new_password} if new_password else {}
        return self.post(f"/users/{uid}/reset-password/", json=body)

    def toggle_active(self, uid: int):
        return self.post(f"/users/{uid}/toggle-active/")

    def students(self, **params):
        return self.get("/users/students/", params=params)

    def teachers(self, **params):
        return self.get("/users/teachers/", params=params)
