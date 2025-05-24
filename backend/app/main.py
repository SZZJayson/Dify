# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine, Base
from app.apis import auth_api, dify_api, vocabulary_api # <--- 确保 vocabulary_api 已导入

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Learning Assistant Backend")

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_api.router, prefix="/api/v1", tags=["Authentication"])
app.include_router(dify_api.router, prefix="/api/v1/dify", tags=["Dify AI Modules"])
app.include_router(vocabulary_api.router, prefix="/api/v1/vocabulary", tags=["Vocabulary Learning"]) # <--- 确保这一行存在且正确

@app.get("/api/v1/health", tags=["Health Check"])
async def health_check():
    return {"status": "healthy", "message": "Backend is running!"}

# uvicorn app.main:app --reload --host 0.0.0.0 --port 8000