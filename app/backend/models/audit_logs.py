from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Audit_logs(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    actor_user_id = Column(String, index=True, nullable=True)
    actor_name = Column(String, nullable=True)
    actor_role = Column(String, nullable=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(Integer, index=True, nullable=True)
    detail = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)