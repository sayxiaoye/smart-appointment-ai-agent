"""用户表、密码和注册服务。"""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from db.base.session_manager import SessionManager
from db.repositories.user_repository import UserRepository
from services.auth_service import AuthService, AuthValidationError, DuplicateUsernameError
from services.passwords import hash_password, verify_password


def test_users_table_rejects_duplicate_username_without_altering_behavior_table(tmp_path: Path):
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE user_behaviors (
            id INTEGER PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            action_type VARCHAR NOT NULL
        )
        """
    )
    before = [row[1] for row in conn.execute("PRAGMA table_info(user_behaviors)")]
    conn.commit()
    conn.close()

    url = "sqlite:///" + db_file.as_posix()
    repo = UserRepository(SessionManager(url))
    repo.create_user("ada", "stored-hash", "艾达")
    with pytest.raises(IntegrityError):
        repo.create_user("ada", "other-hash", "另一个")

    check = sqlite3.connect(db_file)
    after = [row[1] for row in check.execute("PRAGMA table_info(user_behaviors)")]
    user_columns = [row[1] for row in check.execute("PRAGMA table_info(users)")]
    count = check.execute("SELECT COUNT(*) FROM users WHERE username = 'ada'").fetchone()[0]
    check.close()

    assert before == after
    assert user_columns == ["id", "username", "password_hash", "display_name"]
    assert count == 1


def test_password_hash_verifies_without_storing_plaintext():
    stored = hash_password("correct-password")
    assert verify_password("correct-password", stored)
    assert not verify_password("wrong-password", stored)
    assert "correct-password" not in stored
    assert stored.startswith("pbkdf2_sha256$")


def test_register_login_logout_and_validation(tmp_path: Path):
    service = AuthService("sqlite:///" + (tmp_path / "auth.db").as_posix())
    with pytest.raises(AuthValidationError):
        service.register("user-one", "short", "小明")
    with pytest.raises(AuthValidationError):
        service.register("user-one", "long-enough", "   ")
    assert service.users.get_by_username("user-one") is None

    created = service.register("user-one", "long-enough", "小明")
    stored = service.users.get_by_username("user-one")
    assert created["display_name"] == "小明"
    assert "password_hash" not in created
    assert "long-enough" not in stored["password_hash"]
    assert verify_password("long-enough", stored["password_hash"])

    with pytest.raises(DuplicateUsernameError):
        service.register("user-one", "long-enough", "小红")
    assert service.users.count_by_username("user-one") == 1

    session = {}
    assert service.login("user-one", "wrong-password", session) is None
    assert "user_id" not in session
    logged_in = service.login("user-one", "long-enough", session)
    assert logged_in["username"] == "user-one"
    assert service.current_user(session)["display_name"] == "小明"
    service.logout(session)
    assert service.current_user(session) is None
