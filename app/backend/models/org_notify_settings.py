from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Org_notify_settings(Base):
    __tablename__ = "org_notify_settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    smtp_enabled = Column(Boolean, nullable=True)
    smtp_host = Column(String, nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String, nullable=True)
    smtp_password_enc = Column(String, nullable=True)
    smtp_use_tls = Column(Boolean, nullable=True)
    smtp_use_ssl = Column(Boolean, nullable=True)
    smtp_from_email = Column(String, nullable=True)
    smtp_from_name = Column(String, nullable=True)
    sms_enabled = Column(Boolean, nullable=True)
    sms_api_key_enc = Column(String, nullable=True)
    sms_line_number = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)