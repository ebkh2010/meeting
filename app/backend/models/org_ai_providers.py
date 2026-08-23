from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Org_ai_providers(Base):
    __tablename__ = "org_ai_providers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    kind = Column(String, nullable=False)
    provider_key = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=True)
    priority = Column(Integer, nullable=True)
    base_url = Column(String, nullable=True)
    model = Column(String, nullable=True)
    api_key_enc = Column(String, nullable=True)
    auth_username = Column(String, nullable=True)
    auth_password_enc = Column(String, nullable=True)
    diarization = Column(Boolean, nullable=True)
    extra_json = Column(String, nullable=True)
    last_test_ok = Column(Boolean, nullable=True)
    last_test_at = Column(String, nullable=True)
    last_test_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)