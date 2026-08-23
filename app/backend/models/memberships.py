from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Memberships(Base):
    __tablename__ = "memberships"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    member_user_id = Column(String, index=True, nullable=True)
    email = Column(String, nullable=True)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    status = Column(String, nullable=True)
    is_virtual = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)