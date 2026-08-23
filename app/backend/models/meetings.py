from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Meetings(Base):
    __tablename__ = "meetings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    meeting_type = Column(String, nullable=True)
    starts_at = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=True)
    location = Column(String, nullable=True)
    online_url = Column(String, nullable=True)
    secretary_membership_id = Column(Integer, index=True, nullable=True)
    secretary_name = Column(String, nullable=True)
    status = Column(String, nullable=True)
    created_by_user_id = Column(String, index=True, nullable=True)
    created_by_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)