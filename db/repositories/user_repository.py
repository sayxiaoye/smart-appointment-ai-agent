from typing import Any, Dict, Optional

from ..base.session_manager import SessionManager
from ..models import User


class UserRepository:
    """用户账号数据访问。只保存登录所需字段。"""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def create_user(self, username: str, password_hash: str, display_name: str) -> int:
        with self.session_manager.session_scope() as session:
            user = User(
                username=username,
                password_hash=password_hash,
                display_name=display_name,
            )
            session.add(user)
            session.flush()
            return user.id

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self.session_manager.session_scope() as session:
            user = session.query(User).filter(User.username == username).first()
            return self._to_dict(user) if user else None

    def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self.session_manager.session_scope() as session:
            user = session.query(User).filter(User.id == user_id).first()
            return self._to_dict(user) if user else None

    def count_by_username(self, username: str) -> int:
        with self.session_manager.session_scope() as session:
            return session.query(User).filter(User.username == username).count()

    def _to_dict(self, user: User) -> Dict[str, Any]:
        return {
            "id": user.id,
            "username": user.username,
            "password_hash": user.password_hash,
            "display_name": user.display_name,
        }
