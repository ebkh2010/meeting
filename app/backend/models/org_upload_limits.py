from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Org_upload_limits(Base):
    __tablename__ = "org_upload_limits"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    max_audio_minutes = Column(Integer, nullable=True)
    max_audio_mb = Column(Integer, nullable=True)
    max_attachment_mb = Column(Integer, nullable=True)
    updated_by_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)