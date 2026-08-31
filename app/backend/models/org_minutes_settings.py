"""تنظیمات تولید صورتجلسهٔ هر سازمان (ترجیحات محتوایی، نه تأمین‌کنندهٔ AI).

- ``use_agenda`` — آیا دستور جلسه در پرامپت تولید لحاظ شود؟ (پیش‌فرض: بله)
- ``use_attendees`` — آیا مدعوین لحاظ شوند؟ (پیش‌فرض: نه)
- ``words_per_hour`` — طول هدف صورتجلسه به کلمه برای هر ساعت صوت (پیش‌فرض: ۱۰۰۰)
- ``considerations`` — ملاحظات دلخواه کاربر که به پرامپت اضافه می‌شود.
"""
from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text


class Org_minutes_settings(Base):
    __tablename__ = "org_minutes_settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, unique=True, index=True, nullable=False)
    use_agenda = Column(Boolean, nullable=True)
    use_attendees = Column(Boolean, nullable=True)
    words_per_hour = Column(Integer, nullable=True)
    considerations = Column(Text, nullable=True)
    updated_by_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
