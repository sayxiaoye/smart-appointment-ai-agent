"""Detect the old massage-store schema and rebuild the local SQLite file."""

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine.url import make_url

logger = logging.getLogger(__name__)


def reset_legacy_sqlite_if_needed(db_url: str) -> None:
    """Backup and remove a database that still has the technicians table.

    SQLAlchemy create_all cannot alter existing tables, and host/game columns
    are not compatible with the massage-store schema.
    """
    url = make_url(db_url)
    if not url.drivername.startswith("sqlite"):
        return
    database = url.database
    if not database or database == ":memory:":
        return

    path = Path(database)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return

    connection = sqlite3.connect(str(path))
    try:
        found = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='technicians'"
        ).fetchone()
    finally:
        connection.close()

    if not found:
        return

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = path.with_name(f"{path.stem}.legacy.{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    try:
        path.unlink()
    except OSError as exc:
        raise RuntimeError(
            f"检测到旧按摩门店数据库，已备份到 {backup}，但无法删除原文件。请先停掉占用该库的进程后重试。"
        ) from exc

    for suffix in ("-wal", "-shm"):
        extra = Path(str(path) + suffix)
        if extra.exists():
            extra.unlink()

    logger.warning("检测到旧按摩门店数据库，已备份到 %s 并重建", backup)
