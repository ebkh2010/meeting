from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Organizations(Base):
    __tablename__ = "organizations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    plan_code = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    status = Column(String, nullable=True)
    monthly_ai_minutes_quota = Column(Integer, nullable=True)
    ai_minutes_used = Column(Integer, nullable=True)
    quota_period = Column(String, nullable=True)
    # سقف دلاری مدل زبانی کل سازمان در هر دوره (سنت؛ خالی/صفر = بدون سقف)
    ai_llm_limit_cents = Column(Integer, nullable=True)
    max_concurrent_ai_jobs = Column(Integer, nullable=True)
    audio_retention_days = Column(Integer, nullable=True)
    max_audio_mb = Column(Integer, nullable=True)
    max_audio_minutes = Column(Integer, nullable=True)
    is_demo = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)