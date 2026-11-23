"""密码哈希。使用标准库 pbkdf2，不保存明文。"""

import hashlib
import hmac
import secrets

_PREFIX = "pbkdf2_sha256"
_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _ITERATIONS
    )
    return f"{_PREFIX}${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        prefix, iterations, salt, digest = stored.split("$", 3)
        if prefix != _PREFIX:
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
        )
        return hmac.compare_digest(check.hex(), digest)
    except (TypeError, ValueError):
        return False
