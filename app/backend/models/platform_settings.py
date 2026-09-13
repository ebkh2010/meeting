"""تنظیمات سراسری پلتفرم: جفت‌های کلید/مقدار سطح سامانه.

برخلاف ``org_notify_settings`` که تنظیمات هر مستأجر را نگه می‌دارد، این جدول
برای مقادیری است که به یک سازمان خاص تعلق ندارند و مدیر پلتفرم یک‌بار برای کل
سامانه تعیین می‌کند (مثل قالب متن پیامک یادآوری فعال‌سازی).

جدول تازه است؛ ``Base.metadata.create_all`` در راه‌اندازی آن را می‌سازد و نیازی
به مهاجرت ستونی روی جدول‌های موجود نیست.
"""
from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text


class Platform_settings(Base):
    __tablename__ = "platform_settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
