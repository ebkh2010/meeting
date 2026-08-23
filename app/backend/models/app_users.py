from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class App_users(Base):
    __tablename__ = "app_users"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    username = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    mobile = Column(String, nullable=False)
    email = Column(String, nullable=True)
    national_id = Column(String, index=True, nullable=True)
    gender = Column(String, nullable=True)
    role = Column(String, nullable=False)
    status = Column(String, nullable=True)
    must_change_password = Column(Boolean, nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)