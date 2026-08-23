from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Jobs(Base):
    __tablename__ = "jobs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=True)
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    progress = Column(Integer, nullable=True)
    attempts = Column(Integer, nullable=True)
    max_attempts = Column(Integer, nullable=True)
    payload_json = Column(String, nullable=True)
    result_json = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    provider_task_ids = Column(String, nullable=True)
    started_at = Column(String, nullable=True)
    finished_at = Column(String, nullable=True)
    created_by_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)