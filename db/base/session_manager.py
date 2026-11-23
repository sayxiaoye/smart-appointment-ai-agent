from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from ..models import Base


class SessionManager:
    """
    数据库会话管理器
    
    职责：
    1. 管理数据库连接和会话
    2. 提供统一的会话上下文管理
    3. 处理事务和异常回滚
    """
    
    def __init__(self, db_path='sqlite:///data/smart_appointment.db'):
        """
        初始化会话管理器
        
        Args:
            db_path: 数据库连接路径
        """
        self.engine = create_engine(db_path)
        Base.metadata.create_all(self.engine)
        self._ensure_host_gender_column()
        self.Session = scoped_session(sessionmaker(bind=self.engine))

    def _ensure_host_gender_column(self):
        """已有 SQLite 不会被 create_all 改表，缺性别列时补上一列。"""
        if self.engine.dialect.name != "sqlite":
            return
        with self.engine.begin() as conn:
            tables = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='hosts'"
            ).fetchall()
            if not tables:
                return
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(hosts)").fetchall()}
            if "gender" not in columns:
                conn.exec_driver_sql("ALTER TABLE hosts ADD COLUMN gender VARCHAR")

    @contextmanager
    def session_scope(self):
        """
        提供会话上下文管理
        
        自动处理：
        - 会话创建和关闭
        - 事务提交和回滚
        - 异常处理
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self):
        """关闭会话管理器"""
        self.Session.remove()
        self.engine.dispose()
