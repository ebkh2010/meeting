from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Notifications(Base):
    __tablename__ = "notifications"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    recipient_membership_id = Column(Integer, index=True, nullable=True)
    recipient_user_id = Column(String, index=True, nullable=True)
    kind = Column(String, nullable=True)
    title = Column(String, nullable=False)
    body = Column(String, nullable=True)
    link = Column(String, nullable=True)
    dedupe_key = Column(String, nullable=True)
    is_read = Column(Boolean, nullable=True)
    read_at = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)