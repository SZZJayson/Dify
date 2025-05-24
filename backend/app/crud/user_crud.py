from sqlalchemy.orm import Session as SQLAlchemySession
from app.db import models
from app.schemas import user_schemas
from app.security.auth_security import get_password_hash
from typing import Optional # For return type hinting

def get_user_by_email(db: SQLAlchemySession, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: SQLAlchemySession, user: user_schemas.UserWordCreate) -> models.User:
    hashed_password = get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user