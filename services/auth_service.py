"""注册、登录、退出和当前用户。"""

from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError

from db.db_router import DatabaseRouter
from services.passwords import hash_password, verify_password

MIN_PASSWORD_LENGTH = 8


class AuthValidationError(ValueError):
    """注册信息不符合要求。"""


class DuplicateUsernameError(AuthValidationError):
    """用户名已被占用。"""


class AuthService:
    def __init__(self, db_path: str = "sqlite:///data/smart_appointment.db"):
        self.db = DatabaseRouter(db_path)
        self.users = self.db.users

    def register(self, username: str, password: str, display_name: str) -> Dict[str, Any]:
        username = (username or "").strip()
        display_name = (display_name or "").strip()
        if not username:
            raise AuthValidationError("用户名不能为空")
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise AuthValidationError(f"密码至少需要 {MIN_PASSWORD_LENGTH} 个字符")
        if not display_name:
            raise AuthValidationError("称呼不能为空")
        if self.users.get_by_username(username):
            raise DuplicateUsernameError("用户名已被占用")
        try:
            user_id = self.users.create_user(username, hash_password(password), display_name)
        except IntegrityError as exc:
            raise DuplicateUsernameError("用户名已被占用") from exc
        user = self.users.get_by_id(user_id)
        return self.public_user(user)

    def login(self, username: str, password: str, session: Optional[dict] = None) -> Optional[Dict[str, Any]]:
        user = self.users.get_by_username((username or "").strip())
        if not user or not verify_password(password or "", user["password_hash"]):
            return None
        public = self.public_user(user)
        if session is not None:
            session["user_id"] = str(public["id"])
        return public

    def logout(self, session: dict) -> None:
        session.clear()

    def current_user(self, session: dict) -> Optional[Dict[str, Any]]:
        raw = session.get("user_id") if session is not None else None
        if raw in (None, ""):
            return None
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            return None
        user = self.users.get_by_id(user_id)
        if not user:
            return None
        return self.public_user(user)

    @staticmethod
    def public_user(user: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
        }
