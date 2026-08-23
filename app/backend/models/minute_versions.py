from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Minute_versions(Base):
    __tablename__ = "minute_versions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    minutes_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=True)
    version = Column(Integer, nullable=False)
    body_markdown = Column(String, nullable=True)
    summary = Column(String, nullable=True)
    status_at_version = Column(String, nullable=True)
    changed_by_name = Column(String, nullable=True)
    change_note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)