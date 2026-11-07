# -*- coding: utf-8 -*-
"""公共断言（标准分层的 common/assert_tools.py 写法）。

通用签名是 `common_assert(res, status_code, success, code, message)`；
本项目响应体是 `{code, message, data}`，没有 `success` 字段，因此把 success
做成可选参数：传了就按该语义校验（success 等价于 code == 0），不传则忽略。
"""
from common.client import ApiResponse


class CommonAssert(object):
    """一个入口覆盖全部断言维度。"""

    @classmethod
    def common_assert(cls, res: ApiResponse, status_code: int,
                      code: int = None, message: str = None,
                      success: bool = None) -> ApiResponse:
        # 1) HTTP 状态
        assert res.status == status_code, (
            f"HTTP 状态不符：期望 {status_code}，实际 {res.status} | "
            f"{res.method} {res.path} | {res.brief()}"
        )
        # 2) 业务码
        if code is not None:
            assert res.code == code, (
                f"业务码不符：期望 {code}，实际 {res.code} | {res.method} {res.path}"
            )
        # 3) success 语义（本项目用 code == 0 表达）
        if success is not None:
            actual = res.code == 0
            assert actual is success, (
                f"success 不符：期望 {success}，实际 {actual}（code={res.code}）"
            )
        # 4) 提示语（子串匹配，避免文案微调导致误报）
        if message:
            assert message in res.message, (
                f"message 不含 {message!r}，实际 {res.message!r} | {res.method} {res.path}"
            )
        return res

    # 语义化别名：新用例优先用这两个，读起来更直白
    @classmethod
    def assert_ok(cls, res: ApiResponse, status_code: int = 200) -> ApiResponse:
        return cls.common_assert(res, status_code=status_code, code=0, success=True)

    @classmethod
    def assert_error(cls, res: ApiResponse, status_code: int,
                     code: int = None, message: str = None) -> ApiResponse:
        assert res.status != 500, f"不允许 500：{res.method} {res.path} | {res.brief()}"
        return cls.common_assert(res, status_code=status_code, code=code,
                                 message=message, success=False)
