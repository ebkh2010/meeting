from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Notify_deliveries(Base):
    __tablename__ = "notify_deliveries"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=True)
    membership_id = Column(Integer, index=True, nullable=True)
    channel = Column(String, nullable=False)
    recipient = Column(String, nullable=True)
    recipient_name = Column(String, nullable=True)
    status = Column(String, nullable=False)
    provider_message_id = Column(String, index=True, nullable=True)
    error_message = Column(String, nullable=True)
    body_preview = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)