# backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os
from typing import Optional

DOTENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env')
print(f"Attempting to load .env from (config.py): {DOTENV_PATH}")
if os.path.exists(DOTENV_PATH):
    load_dotenv(dotenv_path=DOTENV_PATH)
else:
    print(f"[WARNING in config.py] .env file not found at {DOTENV_PATH}. Using environment variables or defaults.")

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./test.db"
    SECRET_KEY: str = "a_very_secret_key_that_should_be_changed"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    USER_ID: str = "default_dify_user_from_config" # Default Dify user for API calls

    # AI Chat App Config
    CHAT_APP_API_KEY: Optional[str] = None
    CHAT_APP_BASE_URL: Optional[str] = None # Base URL for Dify API, can be global if all apps on same instance
    CHAT_APP_API_ENDPOINT: str = "/chat-messages" # Default to chat app endpoint
    CHAT_TEXT_INPUT_KEY: str = "query"
    CHAT_TEXT_OUTPUT_KEY: str = "answer" # Dify Chat App output is usually 'answer'

    # Composition Correction App Config
    COMPOSITION_APP_API_KEY: Optional[str] = None
    COMPOSITION_APP_BASE_URL: Optional[str] = None
    COMPOSITION_APP_API_ENDPOINT: str = "/workflows/run"
    COMPOSITION_FILE_INPUT_KEY: str = "composition_image"
    COMPOSITION_TEXT_INPUT_KEY: str = "composition_text"
    COMPOSITION_TEXT_OUTPUT_KEY: str = "correction_feedback"

    # Vocabulary Generation App Config
    VOCAB_GEN_APP_API_KEY: Optional[str] = None
    VOCAB_GEN_APP_BASE_URL: Optional[str] = None
    VOCAB_GEN_APP_API_ENDPOINT: str = "/workflows/run"
    VOCAB_GEN_INPUT_KEY: str = "keywords"
    VOCAB_GEN_WORD_COUNT_KEY: str = "count" # 新增
    VOCAB_GEN_OUTPUT_KEY: str = "word_list"

    # Grammar Parsing App Config
    GRAMMAR_PARSE_APP_API_KEY: Optional[str] = None
    GRAMMAR_PARSE_APP_BASE_URL: Optional[str] = None
    GRAMMAR_PARSE_APP_API_ENDPOINT: str = "/workflows/run"
    GRAMMAR_PARSE_INPUT_KEY: str = "text_to_parse"
    GRAMMAR_PARSE_OUTPUT_KEY: str = "correction_feedback"


    model_config = SettingsConfigDict(
        env_file=DOTENV_PATH if os.path.exists(DOTENV_PATH) else None,
        env_file_encoding='utf-8',
        extra='ignore'
    )

settings = Settings()

# Verification prints
print("--- Config Loaded (config.py) ---")
print(f"CHAT_FILE_INPUT_KEY: {settings.CHAT_TEXT_INPUT_KEY}")
print(f"COMPOSITION_FILE_INPUT_KEY: {settings.COMPOSITION_FILE_INPUT_KEY}")
print(f"VOCAB_GEN_INPUT_KEY: {settings.VOCAB_GEN_INPUT_KEY}")
print(f"GRAMMAR_PARSE_INPUT_KEY: {settings.GRAMMAR_PARSE_INPUT_KEY}")
print("---------------------------------")

if not settings.CHAT_APP_API_KEY or not settings.CHAT_APP_BASE_URL :
    print("[CRITICAL ERROR in config.py] CHAT_APP_API_KEY or CHAT_APP_BASE_URL not configured!")
else:
    print("[INFO in config.py] Dify app configurations appear to be present.")