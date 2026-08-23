from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Action_items(Base):
    __tablename__ = "action_items"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=False)
    decision_id = Column(Integer, index=True, nullable=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    owner_membership_id = Column(Integer, index=True, nullable=True)
    owner_name = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    status = Column(String, nullable=True)
    progress_note = Column(String, nullable=True)
    source = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)