# backend/app/schemas/vocabulary_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import enum

# Mirroring the DB enum for schema validation
class WordLearningStatusEnum(str, enum.Enum):
    UNKNOWN = "unknown"
    VAGUE = "vague"
    KNOWN = "known"
    MASTERED = "mastered"

class UserWordBase(BaseModel):
    word: str
    status: WordLearningStatusEnum

class UserWordCreate(UserWordBase):
    # dify_word_data: Optional[str] = None # If you store the full Dify object
    pass

class UserWordUpdate(BaseModel):
    status: WordLearningStatusEnum
    # You might allow updating incorrect_attempts, last_reviewed_at from frontend for sync,
    # but next_review_at should ideally be calculatedサーバーサイド.

class UserWord(UserWordBase): # For responses
    id: int
    user_id: int
    incorrect_attempts: int
    correct_attempts_streak: int
    last_reviewed_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class WordProgressUpdateRequest(BaseModel):
    word: str = Field(..., description="The word string being updated.")
    status: WordLearningStatusEnum = Field(..., description="The new learning status of the word.")
    # session_id: Optional[str] = None # Optional: if you track learning sessions

class BulkWordProgressUpdateRequest(BaseModel):
    progress_updates: List[WordProgressUpdateRequest]


class UserBase(BaseModel):
    email: str
    # 你可以在这里添加其他基础用户字段，比如 full_name
    # full_name: Optional[str] = None

class UserCreate(UserBase): # <--- 这个是必需的
    password: str
    # 如果注册时也允许设置 full_name
    # full_name: Optional[str] = None

class UserLogin(UserBase):
    password: str

class User(UserBase): # 用于API响应
    id: int
    is_active: bool
    # full_name: Optional[str] = None # 如果 User 模型有此字段

    class Config:
        from_attributes = True # Pydantic V2 (was orm_mode = True in V1)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel): # 用于JWT内部
    email: Optional[str] = None