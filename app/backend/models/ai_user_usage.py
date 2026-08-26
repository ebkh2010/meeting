"""مدل‌های مصرف و سهمیهٔ هوش مصنوعی به‌ازای هر کاربر.

دو جدول مستقل از سهمیهٔ سازمانی:
- ``Ai_user_quotas``: سقف هر کاربر (دلار مدل زبانی و دقیقهٔ رونویسی در هر دوره).
- ``Ai_user_usage``: رویداد مصرف واقعی هر کار AI با مالکیت کاربر (توکن، هزینه و دقیقه).
"""
from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Ai_user_quotas(Base):
    __tablename__ = "ai_user_quotas"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    # سقف دلاری مدل زبانی به سنت (۵ دلار = ۵۰۰)
    llm_limit_cents = Column(Integer, nullable=True)
    # سقف رونویسی به دقیقه (۱۰ ساعت = ۶۰۰)
    stt_limit_minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)


class Ai_user_usage(Base):
    __tablename__ = "ai_user_usage"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    job_id = Column(Integer, index=True, nullable=True)
    meeting_id = Column(Integer, index=True, nullable=True)
    kind = Column(String, nullable=False)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True)
    minutes_charged = Column(Integer, nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    cost_cents = Column(Integer, nullable=True)
    detail = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
