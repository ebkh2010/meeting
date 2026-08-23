from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Recordings(Base):
    __tablename__ = "recordings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=False)
    bucket_name = Column(String, nullable=True)
    object_key = Column(String, nullable=False)
    file_name = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    upload_status = Column(String, nullable=True)
    consent_ack = Column(Boolean, nullable=True)
    purge_after = Column(String, nullable=True)
    uploaded_by_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)