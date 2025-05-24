# backend/app/apis/vocabulary_api.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as SQLAlchemySession
from typing import List

from app.db.database import get_db
from app.db.models import User as UserModel
from app.apis.auth_api import get_current_active_user
from app.schemas import vocabulary_schemas as schemas
from app.crud import vocabulary_crud as crud

router = APIRouter(
   # API prefix /api/v1/vocabulary/...
    tags=["Vocabulary Learning"]
)

@router.post("/progress", response_model=schemas.UserWordResponse, summary="Update progress for a single word")
async def update_single_word_progress(
    progress_update: schemas.WordProgressUpdateRequest,
    db: SQLAlchemySession = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    print(f"Received progress update for user {current_user.id}, word: {progress_update.word}, status: {progress_update.status}") # 调试信息
    try:
        db_user_word = crud.create_or_update_user_word(db=db, user_id=current_user.id, word_progress=progress_update)
        print(f"Progress update successful for word ID: {db_user_word.id}") # 调试信息
        return db_user_word
    except Exception as e:
        print(f"Error in update_single_word_progress: {e}") # 调试信息
        import traceback
        traceback.print_exc() # 打印完整错误堆栈到后端控制台
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="保存单词进度时发生内部错误。")

@router.post("/progress/batch", response_model=List[schemas.UserWordResponse], summary="Update progress for multiple words")
async def update_batch_word_progress(
    batch_update_request: schemas.BulkWordProgressUpdateRequest,
    db: SQLAlchemySession = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    updated_words = []
    for progress_update in batch_update_request.progress_updates:
        db_user_word = crud.create_or_update_user_word(db=db, user_id=current_user.id, word_progress=progress_update)
        updated_words.append(db_user_word)
    return updated_words


@router.get("/review-list", response_model=List[schemas.DifyWordSchema], summary="Get list of words due for review with full details") # <--- response_model 变为 DifyWordSchema
async def get_review_list(
      limit: int = 20,
      db: SQLAlchemySession = Depends(get_db),
      current_user: UserModel = Depends(get_current_active_user),
  ):
      words_for_review_models = crud.get_words_for_review(db=db, user_id=current_user.id, limit=limit)
      
      detailed_review_words = []
      for user_word_model in words_for_review_models:
          if hasattr(user_word_model, 'dify_word_data_json') and user_word_model.dify_word_data_json:
              try:
                  dify_data = json.loads(user_word_model.dify_word_data_json)
                  # 确保 dify_data 包含 DifyWordSchema 需要的所有字段，或者用 Pydantic 解析它
                  # For simplicity, assuming dify_data directly matches DifyWordSchema structure
                  detailed_review_words.append(dify_data)
              except json.JSONDecodeError:
                  print(f"Error parsing stored Dify JSON for word: {user_word_model.word}")
                  # Fallback: return basic info if JSON is corrupted or missing
                  detailed_review_words.append({"word": user_word_model.word, "definition_cn": "释义信息丢失"})
          else:
              # Fallback if no full Dify data was stored (shouldn't happen if implemented correctly)
              detailed_review_words.append({"word": user_word_model.word, "definition_cn": "详细信息未存储"})
      
      print(f"Returning detailed review list for user {current_user.id}: {len(detailed_review_words)} words")
      return detailed_review_words # FastAPI will validate against List[schemas.DifyWordSchema]


@router.get("/summary", response_model=dict, summary="Get user's vocabulary learning summary")
async def get_vocabulary_summary(
    db: SQLAlchemySession = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    summary = crud.get_user_vocabulary_summary(db=db, user_id=current_user.id)
    return summary