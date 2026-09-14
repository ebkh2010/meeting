"""مدیران پلتفرم: حساب‌های مدیریتی سطح سامانه، مستقل از مستأجرها.

مدیر پلتفرم به هیچ سازمانی تعلق ندارد و فقط از endpointهای ``/api/v1/platform``
استفاده می‌کند؛ توکن آن با نوع ``vidara_platform`` امضا می‌شود و در وابستگی‌های
فضای کاری (که نوع ``vidara_app`` را می‌خواهند) رد می‌شود.

``is_owner`` یعنی «مدیر اصلی»: تنها حسابی که می‌تواند مدیر پلتفرم دیگری تعریف،
ویرایش یا حذف کند. حساب ساخته‌شده از متغیرهای محیطی در نخستین راه‌اندازی مدیر
اصلی است و همیشه باید دست‌کم یک مدیر اصلی باقی بماند.
"""
from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Platform_admins(Base):
    __tablename__ = "platform_admins"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    status = Column(String, nullable=True)
    # nullable=True چون این ستون روی دیتابیس‌های از قبل مستقرشده با ALTER و بدون
    # NOT NULL اضافه می‌شود؛ در کد همیشه با bool() خوانده می‌شود.
    is_owner = Column(Boolean, nullable=True, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
