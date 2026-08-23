from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Participants(Base):
    __tablename__ = "participants"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=False)
    membership_id = Column(Integer, index=True, nullable=False)
    member_user_id = Column(String, index=True, nullable=True)
    full_name = Column(String, nullable=True)
    rsvp_status = Column(String, nullable=True)
    rsvp_note = Column(String, nullable=True)
    attended = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)