# backend/app/crud/vocabulary_crud.py
from sqlalchemy.orm import Session as SQLAlchemySession
from sqlalchemy import func, or_
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from app.db import models
from app.schemas import vocabulary_schemas as schemas

def get_user_word(db: SQLAlchemySession, user_id: int, word: str) -> Optional[models.UserWord]:
    return db.query(models.UserWord).filter(models.UserWord.user_id == user_id, models.UserWord.word == word).first()

def create_or_update_user_word(db: SQLAlchemySession, user_id: int, word_progress: schemas.WordProgressUpdateRequest) -> models.UserWord:
    db_user_word = get_user_word(db, user_id=user_id, word=word_progress.word)
    
    now = datetime.now(timezone.utc) # Use timezone-aware datetime

    if db_user_word: # Update existing record
        db_user_word.status = word_progress.status
        db_user_word.last_reviewed_at = now
        if word_progress.status == schemas.WordLearningStatusEnum.KNOWN or word_progress.status == schemas.WordLearningStatusEnum.MASTERED:
            db_user_word.correct_attempts_streak = (db_user_word.correct_attempts_streak or 0) + 1
            db_user_word.incorrect_attempts = 0 # Reset incorrect on correct
            # Simple spaced repetition: known -> +1 day, mastered -> +3 days, vague -> review soon, unknown -> review very soon
            if word_progress.status == schemas.WordLearningStatusEnum.KNOWN:
                 db_user_word.next_review_at = now + timedelta(days=db_user_word.correct_attempts_streak * 1) # Increase review interval
            elif word_progress.status == schemas.WordLearningStatusEnum.MASTERED:
                 db_user_word.next_review_at = now + timedelta(days=db_user_word.correct_attempts_streak * 3)
        else: # Vague or Unknown
            db_user_word.incorrect_attempts = (db_user_word.incorrect_attempts or 0) + 1
            db_user_word.correct_attempts_streak = 0 # Reset streak
            if word_progress.status == schemas.WordLearningStatusEnum.UNKNOWN:
                db_user_word.next_review_at = now + timedelta(minutes=10) # Review very soon
            else: # Vague
                db_user_word.next_review_at = now + timedelta(hours=1) # Review soon
        db_user_word.updated_at = now
    else: # Create new record
        db_user_word = models.UserWord(
            user_id=user_id,
            word=word_progress.word,
            status=word_progress.status,
            last_reviewed_at=now,
            incorrect_attempts= 1 if word_progress.status != schemas.WordLearningStatusEnum.KNOWN and word_progress.status != schemas.WordLearningStatusEnum.MASTERED else 0,
            correct_attempts_streak= 1 if word_progress.status == schemas.WordLearningStatusEnum.KNOWN or word_progress.status == schemas.WordLearningStatusEnum.MASTERED else 0
        )
        # Set initial next_review_at based on status
        if word_progress.status == schemas.WordLearningStatusEnum.KNOWN:
            db_user_word.next_review_at = now + timedelta(days=1)
        elif word_progress.status == schemas.WordLearningStatusEnum.MASTERED:
             db_user_word.next_review_at = now + timedelta(days=3)
        elif word_progress.status == schemas.WordLearningStatusEnum.UNKNOWN:
            db_user_word.next_review_at = now + timedelta(minutes=10)
        else: # Vague
            db_user_word.next_review_at = now + timedelta(hours=1)
        db.add(db_user_word)
    
    db.commit()
    db.refresh(db_user_word)
    return db_user_word
    
def get_words_for_review(db: SQLAlchemySession, user_id: int, limit: int = 20) -> List[models.UserWord]:
    now = datetime.now(timezone.utc)
    return db.query(models.UserWord)\
        .filter(models.UserWord.user_id == user_id)\
        .filter(or_(models.UserWord.next_review_at <= now, models.UserWord.next_review_at == None))\
        .filter(models.UserWord.status != schemas.WordLearningStatusEnum.MASTERED)\
        .order_by(models.UserWord.next_review_at.asc().nullsfirst(), models.UserWord.incorrect_attempts.desc())\
        .limit(limit)\
        .all()

def get_user_vocabulary_summary(db: SQLAlchemySession, user_id: int) -> dict:
    counts = db.query(
            models.UserWord.status,
            func.count(models.UserWord.id)
        ).filter(models.UserWord.user_id == user_id)\
        .group_by(models.UserWord.status)\
        .all()
    summary = {status.value: count for status, count in counts}
    summary["total_learned"] = sum(summary.values())
    return summary