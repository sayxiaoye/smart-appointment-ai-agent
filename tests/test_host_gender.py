"""主持人性别：新库写入，旧库补列并回填。"""

import sqlite3
from pathlib import Path

from services.host_service import HostService


def test_default_hosts_have_gender(tmp_path: Path):
    service = HostService("sqlite:///" + (tmp_path / "hosts.db").as_posix())
    service.initialize_default_hosts()
    hosts = {host["name"]: host["gender"] for host in service.get_all_hosts()}
    assert hosts["陈屿"] == "男"
    assert hosts["林可"] == "女"
    assert hosts["苏晚"] == "女"
    assert hosts["许清"] == "女"
    assert set(hosts.values()) <= {"男", "女"}


def test_existing_hosts_without_gender_column_are_backfilled(tmp_path: Path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE hosts (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL UNIQUE,
            host_types JSON NOT NULL,
            specialty VARCHAR
        )
        """
    )
    conn.execute(
        "INSERT INTO hosts (name, host_types, specialty) VALUES (?, ?, ?)",
        ("陈屿", '["pro_host"]', "控场"),
    )
    conn.commit()
    conn.close()

    service = HostService("sqlite:///" + db.as_posix())
    host = service.get_host_by_name("陈屿")
    assert host["gender"] == "男"
