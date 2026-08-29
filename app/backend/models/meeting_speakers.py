"""گوینده‌های جلسه: برچسب گوینده از رونویسی (diarization) + نام دلخواه کاربر.

برچسب گوینده از سرویس رونویسی می‌آید (مثلاً ``SPEAKER_0``) و «حرف» هیچ
دادهٔ بیومتریکی در اختیار ما نمی‌گذارد؛ کاربر پس از شنیدن کلیپ کوتاه صدای هر
گوینده، نام او را روی این ردیف ثبت می‌کند. نام‌گذاری گوینده اثر محتوایی دارد
و فقط برای مدیر جلسه (مدیر سازمان/دبیر همان جلسه) مجاز است.
"""
from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Meeting_speakers(Base):
    __tablename__ = "meeting_speakers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=False)
    transcript_id = Column(Integer, index=True, nullable=True)
    speaker_key = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
