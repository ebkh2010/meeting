from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Meeting_attachments(Base):
    __tablename__ = "meeting_attachments"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=False)
    object_key = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    uploaded_by_user_id = Column(String, index=True, nullable=True)
    uploaded_by_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)