from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Agenda_items(Base):
    __tablename__ = "agenda_items"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=False)
    position = Column(Integer, nullable=True)
    title = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    planned_minutes = Column(Integer, nullable=True)
    owner_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)