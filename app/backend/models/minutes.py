from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Minutes(Base):
    __tablename__ = "minutes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=False)
    status = Column(String, nullable=True)
    body_markdown = Column(String, nullable=True)
    summary = Column(String, nullable=True)
    current_version = Column(Integer, nullable=True)
    generated_by = Column(String, nullable=True)
    review_requested_at = Column(String, nullable=True)
    approved_by_name = Column(String, nullable=True)
    approved_at = Column(String, nullable=True)
    locked_at = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)