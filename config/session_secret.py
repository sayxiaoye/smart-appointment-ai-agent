"""登录 cookie 的签名密钥。缺失或仍是示例占位符时拒绝启动。"""

import os

SESSION_SECRET_PLACEHOLDER = "replace_with_a_long_random_string"


def require_session_secret() -> str:
    secret = os.getenv("SESSION_SECRET", "").strip()
    if not secret or secret == SESSION_SECRET_PLACEHOLDER:
        raise RuntimeError("缺少有效的 SESSION_SECRET，拒绝启动")
    return secret
