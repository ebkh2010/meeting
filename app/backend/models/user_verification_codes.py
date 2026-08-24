from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class User_verification_codes(Base):
    """کدهای یکبارمصرف تأیید ایمیل/موبایل کاربران (OTP)."""

    __tablename__ = "user_verification_codes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    purpose = Column(String, nullable=False)  # "email" | "mobile"
    target = Column(String, nullable=False)  # نشانی مقصد (ایمیل یا شمارهٔ موبایل)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
