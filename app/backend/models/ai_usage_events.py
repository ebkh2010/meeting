from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Ai_usage_events(Base):
    __tablename__ = "ai_usage_events"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    job_id = Column(Integer, index=True, nullable=True)
    meeting_id = Column(Integer, index=True, nullable=True)
    kind = Column(String, nullable=False)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True)
    minutes_charged = Column(Integer, nullable=True)
    detail = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)