from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Meeting_archive_files(Base):
    __tablename__ = "meeting_archive_files"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=False)
    source_kind = Column(String, nullable=False)
    source_id = Column(Integer, index=True, nullable=False)
    file_name = Column(String, nullable=True)
    content_type = Column(String, nullable=True)
    source_bucket = Column(String, nullable=True)
    source_object_key = Column(String, nullable=True)
    remote_path = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    checksum_sha256 = Column(String, nullable=True)
    status = Column(String, nullable=False)
    error_message = Column(String, nullable=True)
    archived_at = Column(String, nullable=True)
    restored_at = Column(String, nullable=True)
    restore_expires_at = Column(String, nullable=True)
    archived_by_name = Column(String, nullable=True)
    restored_by_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)