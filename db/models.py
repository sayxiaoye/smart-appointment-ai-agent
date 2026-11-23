from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Host(Base):
    __tablename__ = "hosts"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    host_types = Column(JSON, nullable=False)
    specialty = Column(String, nullable=True)
    schedules = relationship("HostSchedule", back_populates="host", cascade="all, delete-orphan")


class HostSchedule(Base):
    __tablename__ = "host_schedules"
    id = Column(Integer, primary_key=True)
    host_id = Column(Integer, ForeignKey("hosts.id"))
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)  # 'busy' or 'free'
    appointment_id = Column(Integer, nullable=True)
    host = relationship("Host", back_populates="schedules")


class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    min_players = Column(Integer, nullable=False)
    max_players = Column(Integer, nullable=False)
    duration_min = Column(Integer, nullable=False)
    needs_host = Column(Boolean, nullable=False, default=True)
    allowed_host_types = Column(JSON, nullable=False)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    keywords = Column(JSON, nullable=True)
    embedding = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Integer, default=1)


class UserBehavior(Base):
    __tablename__ = "user_behaviors"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False, default="default_user")
    action_type = Column(String, nullable=False)  # 'appointment', 'consultation', 'inquiry'
    action_data = Column(JSON, nullable=True)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=True)
    session_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    host = relationship("Host")


class UserPreference(Base):
    __tablename__ = "user_preferences"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False, default="default_user")
    preference_type = Column(String, nullable=False)  # 'host', 'host_type', 'game', 'time'
    preference_value = Column(String, nullable=False)
    confidence_score = Column(Integer, default=1)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserRecommendation(Base):
    __tablename__ = "user_recommendations"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False, default="default_user")
    recommendation_type = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=True)
    is_sent = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    host = relationship("Host")
