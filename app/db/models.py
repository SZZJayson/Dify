# backend/app/db/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from typing import Optional

from .database import Base

# --- User Model ---
class User(Base):
    # ... (User model definition as before) ...
    __tablename__ = "users"
    id: int = Column(Integer, primary_key=True, index=True)
    email: str = Column(String, unique=True, index=True, nullable=False)
    hashed_password: str = Column(String, nullable=False)
    is_active: bool = Column(Boolean, default=True)
    created_at: DateTime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: Optional[DateTime] = Column(DateTime(timezone=True), onupdate=func.now())
    learned_words = relationship("UserWord", back_populates="owner", cascade="all, delete-orphan")


# --- WordLearningStatus Enum ---
class WordLearningStatus(enum.Enum):
    UNKNOWN = "unknown"
    VAGUE = "vague"
    KNOWN = "known"
    MASTERED = "mastered"

# --- UserWord Model ---
class UserWord(Base):
    __tablename__ = "user_words"

    id: int = Column(Integer, primary_key=True, index=True)
    user_id: int = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    word: str = Column(String, nullable=False, index=True)
    
    # --- MODIFICATION START ---
    status: WordLearningStatus = Column(
        SQLAlchemyEnum(
            WordLearningStatus,
            name="wordlearningstatus", # 数据库中枚举类型的名称 (对于PostgreSQL等重要)
            values_callable=lambda obj: [e.value for e in obj] # 告诉SQLAlchemy使用枚举的.value
        ),
        default=WordLearningStatus.UNKNOWN,
        nullable=False
    )
    # --- MODIFICATION END ---
    
    incorrect_attempts: int = Column(Integer, default=0)
    correct_attempts_streak: int = Column(Integer, default=0)
    last_reviewed_at: Optional[DateTime] = Column(DateTime(timezone=True), nullable=True)
    next_review_at: Optional[DateTime] = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at: DateTime = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: Optional[DateTime] = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="learned_words")

    def __repr__(self):
        return f"<UserWord(user_id={self.user_id}, word='{self.word}', status='{self.status.value}')>"