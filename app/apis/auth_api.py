from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session as SQLAlchemySession # Use alias for clarity
from datetime import timedelta
from typing import Any # For Depends type

from app.db.database import get_db
from app.schemas import user_schemas as schemas # Use alias for schemas
from app.crud import user_crud
from app.security.auth_security import verify_password, create_access_token
from app.core.config import settings
from jose import JWTError, jwt # For decoding token in get_current_user
from app.db import models # <--- 添加这一行来导入你的 SQLAlchemy 模型

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login") # Define it once here

@router.post("/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: SQLAlchemySession = Depends(get_db)) -> Any:
    db_user = user_crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    created_user = user_crud.create_user(db=db, user=user)
    return created_user

@router.post("/login", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: SQLAlchemySession = Depends(get_db)
) -> Any:
    user = user_crud.get_user_by_email(db, email=form_data.username) # form_data.username is email
    if not user or not verify_password(form_data.password, user.hashed_password) or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password, or inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


async def get_current_user(token: str = Depends(oauth2_scheme), db: SQLAlchemySession = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
        # token_data = schemas.TokenData(email=email) # Not strictly needed if just using email
    except JWTError:
        raise credentials_exception
    
    user = user_crud.get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user

@router.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)) -> Any:
    return current_user