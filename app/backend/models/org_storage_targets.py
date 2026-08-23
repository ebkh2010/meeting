from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Org_storage_targets(Base):
    __tablename__ = "org_storage_targets"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    provider = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=True)
    endpoint = Column(String, nullable=True)
    bucket = Column(String, nullable=True)
    region = Column(String, nullable=True)
    path_prefix = Column(String, nullable=True)
    access_key = Column(String, nullable=True)
    secret_key_enc = Column(String, nullable=True)
    force_path_style = Column(Boolean, nullable=True)
    webdav_base_url = Column(String, nullable=True)
    webdav_username = Column(String, nullable=True)
    webdav_password_enc = Column(String, nullable=True)
    restore_retention_days = Column(Integer, nullable=True)
    last_test_ok = Column(Boolean, nullable=True)
    last_test_at = Column(String, nullable=True)
    last_test_message = Column(String, nullable=True)
    updated_by_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)