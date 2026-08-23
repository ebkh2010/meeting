from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Invitations(Base):
    __tablename__ = "invitations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, nullable=False)
    token = Column(String, nullable=False)
    status = Column(String, nullable=True)
    expires_at = Column(String, nullable=True)
    invited_by_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)