from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String


class Transcripts(Base):
    __tablename__ = "transcripts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=False)
    meeting_id = Column(Integer, index=True, nullable=False)
    recording_id = Column(Integer, index=True, nullable=False)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True)
    full_text = Column(String, nullable=True)
    segments_json = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    known_word_ratio = Column(Float, nullable=True)
    stats_words = Column(Integer, nullable=True)
    stats_known_words = Column(Integer, nullable=True)
    job_id = Column(Integer, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)