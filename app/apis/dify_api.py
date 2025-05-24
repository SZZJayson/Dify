# backend/app/apis/dify_api.py
from fastapi import (
    APIRouter,
    File,
    UploadFile,
    Depends,
    HTTPException,
    Form,
    status,
    Body # Keep if you use it for other Pydantic models directly in Body
)
from sqlalchemy.orm import Session as SQLAlchemySession # Keep if DB interaction is planned here
import shutil
import os
import uuid
import json
from typing import Dict, Any, List, Optional  # Ensure Optional is from typing
import re
from pydantic import BaseModel,Field # For request body Pydantic models

# Assuming these are correctly set up and accessible
from app.db.database import get_db
from app.db.models import User as UserModel
from app.apis.auth_api import get_current_active_user # Your authentication dependency
from app.core.config import settings # Application settings

# Service for Dify API calls
from app.services.dify_workflow_service import call_dify_api, DifyWorkflowError

# Utilities for file handling related to Dify
from app.dify_integration.dify_utils import (
    upload_file_to_dify, # For pre-uploading files to Dify's storage if needed
    determine_file_category_and_mime
)

router = APIRouter(
    # prefix is set in app/main.py when including this router, e.g., /api/v1/dify
    tags=["Dify AI Modules"] # OpenAPI/Swagger tag for this group of endpoints
)

TEMP_UPLOAD_DIR = "temp_uploads_for_dify_processing" # A dedicated temp directory
if not os.path.exists(TEMP_UPLOAD_DIR):
    os.makedirs(TEMP_UPLOAD_DIR)

# --- Helper function to consistently extract text output from Dify's response ---
# backend/app/apis/dify_api.py
import json
from typing import Dict, Any

def extract_text_from_dify_response(dify_response_data: Dict[str, Any], configured_output_key: str) -> str:
    text_output: Any = None
    final_output_key_used: str = configured_output_key

    print(f"--- Raw Dify Response Data Received by extract_text_from_dify_response ---")
    print(json.dumps(dify_response_data, indent=2, ensure_ascii=False))
    print(f"--- End of Raw Dify Response Data ---")
    print(f"Configured output key for extraction: {configured_output_key}")

    # 1. 检查是否是聊天/完成型应用的响应结构 (如 /chat-messages)
    if "answer" in dify_response_data and dify_response_data["answer"] is not None:
        print("Found 'answer' key, treating as Chat/Completion App response.")
        text_output = dify_response_data.get("answer")
        final_output_key_used = "answer (from Chat/Completion App)"
    else:
        # 2. 尝试解析工作流的输出结构 (通常在 data.outputs)
        dify_outputs_container: PyOptional[Dict[str, Any]] = None # To store the object that CONTAINS 'outputs'

        if "data" in dify_response_data and isinstance(dify_response_data.get("data"), dict):
            dify_outputs_container = dify_response_data.get("data")
            print("Found 'data' object in Dify response.")
        elif "outputs" in dify_response_data and isinstance(dify_response_data.get("outputs"), dict):
            # Fallback if 'outputs' is at the top level (less common for /workflows/run success)
            dify_outputs_container = dify_response_data # outputs is a direct key of response_data
            print("Found 'outputs' object at top level of Dify response.")
        else:
            print("Neither 'data' (containing 'outputs') nor top-level 'outputs' dictionary found.")

        actual_outputs_dict: PyOptional[Dict[str, Any]] = None
        if dify_outputs_container and "outputs" in dify_outputs_container and \
           isinstance(dify_outputs_container.get("outputs"), dict):
            actual_outputs_dict = dify_outputs_container.get("outputs")
            print(f"Successfully accessed 'outputs' dictionary: {list(actual_outputs_dict.keys()) if actual_outputs_dict else 'is None'}")
        else:
            print("Failed to access a valid 'outputs' dictionary from Dify response container.")


        if actual_outputs_dict: # 确保 actual_outputs_dict 是一个字典
            print(f"Processing 'outputs' object. Attempting to get value for key: '{configured_output_key}'")
            text_output = actual_outputs_dict.get(configured_output_key)
            final_output_key_used = f"outputs.{configured_output_key}"

            if text_output is None and configured_output_key != "text" and "text" in actual_outputs_dict:
                print(f"Warning: Key '{configured_output_key}' not found in 'outputs'. Falling back to 'outputs.text'.")
                text_output = actual_outputs_dict.get("text")
                final_output_key_used = "outputs.text (fallback)"
        else:
            # 如果没有找到 outputs 对象，但配置的输出键存在于顶层（不太可能 для /workflows/run 成功时）
            if configured_output_key in dify_response_data:
                 print(f"Warning: No 'outputs' object, but configured output key '{configured_output_key}' found at top level of Dify response.")
                 text_output = dify_response_data.get(configured_output_key)
                 final_output_key_used = f"{configured_output_key} (top-level)"


    print(f"Extracted text_output (before type conversion) using key '{final_output_key_used}': '{str(text_output)[:200]}...'")

    # 3. 处理和返回提取到的文本
    if text_output is None:
        # 检查Dify工作流是否本身执行失败了
        workflow_data = dify_response_data.get("data", {})
        if workflow_data.get("status") == "failed" and workflow_data.get("error"):
            dify_internal_error = workflow_data.get('error')
            print(f"Dify workflow itself failed. Error: {dify_internal_error}")
            # 提取 KeyError: 'text' 这种具体错误
            key_error_match = re.search(r"KeyError: '([^']*)'", dify_internal_error)
            if key_error_match:
                missing_key = key_error_match.group(1)
                return f"AI工作流执行失败：内部代码节点缺少预期的输入数据（键：'{missing_key}'）。请检查Dify工作流配置。"
            return f"AI工作流执行失败: {dify_internal_error[:200]}..."

        return "AI未能生成有效的文本回复（未找到指定输出或工作流输出为空）。"
    
    if not isinstance(text_output, str):
        try:
            return json.dumps(text_output, ensure_ascii=False) if isinstance(text_output, (dict, list)) else str(text_output)
        except TypeError:
            return str(text_output)
    return text_output


# === Pydantic Models for Request Bodies ===
class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None

class GenerateWordsRequest(BaseModel):
    keywords: str
    word_count: int = Field(10, gt=0, le=30) # Example: default 10, min 1, max 50

class ParseGrammarRequest(BaseModel):
    text_to_parse: str = Field(..., min_length=1, description="需要进行语法解析的文本")


# === API Endpoints ===

@router.post("/ai-chat", summary="Send text message to AI Chat Application")
async def ai_chat_endpoint(
    request_data: ChatRequest, # ChatRequest has 'query' and 'conversation_id'
    current_user: UserModel = Depends(get_current_active_user),
):
    if not settings.CHAT_APP_API_KEY or not settings.CHAT_APP_BASE_URL or not settings.CHAT_APP_API_ENDPOINT:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI聊天服务未正确配置。")

    dify_user_identifier = str(current_user.id) # Or current_user.email

    # --- MODIFICATION START ---
    # Construct the payload for Dify's /chat-messages or /completion-messages endpoint
    # The main user query needs to be both at the top-level 'query'
    # AND inside the 'inputs' object, using the variable name defined in Dify.
    
    # CHAT_TEXT_INPUT_KEY from your .env is the variable name for the query within Dify's 'inputs'
    if not settings.CHAT_TEXT_INPUT_KEY:
        raise DifyWorkflowError("CHAT_TEXT_INPUT_KEY is not configured for the chat application.", 500)

    dify_payload: Dict[str, Any] = {
        "query": request_data.query,  # Top-level query, required by /chat-messages
        "inputs": {},                 # Send an empty object for inputs, as it's optional
        "user": dify_user_identifier,
        "response_mode": "blocking",
    }

    if request_data.conversation_id:
        dify_payload["conversation_id"] = request_data.conversation_id
    
    # The rest of the try/except block remains the same
    try:
        print(f"Constructed Dify Payload for /ai-chat (with empty inputs): {json.dumps(dify_payload, indent=2, ensure_ascii=False)}")
        dify_response_data = call_dify_api( # call_dify_api sends this payload as JSON body
            dify_base_url=settings.CHAT_APP_BASE_URL,
            dify_api_key=settings.CHAT_APP_API_KEY,
            dify_api_endpoint_path=settings.CHAT_APP_API_ENDPOINT, # Should be /chat-messages
            payload=dify_payload
        )
        
        # extract_text_from_response will get 'answer' for chat apps
        ai_text = extract_text_from_dify_response(dify_response_data, settings.CHAT_TEXT_OUTPUT_KEY)
        
        return {
            "message": "AI回复已生成。",
            "ai_text": ai_text,
            "conversation_id": dify_response_data.get("conversation_id"),
            "dify_full_response": dify_response_data
        }
    except DifyWorkflowError as e:
        # Log the payload that caused the error for easier debugging
        print(f"DifyWorkflowError with payload: {json.dumps(dify_payload, indent=2, ensure_ascii=False)}")
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"AI聊天时发生意外错误: {type(e).__name__}")



@router.post("/correct-composition", summary="Submit composition (text and/or image) for AI correction")
async def correct_composition_endpoint(
    composition_text: Optional[str] = Form(None),
    composition_image: Optional[UploadFile] = File(None),
    current_user: UserModel = Depends(get_current_active_user),
):
    # 检查作文批改服务的核心配置 (这部分逻辑是好的，保持)
    if not settings.COMPOSITION_APP_API_KEY or \
       not settings.COMPOSITION_APP_BASE_URL or \
       not settings.COMPOSITION_APP_API_ENDPOINT or \
       not settings.COMPOSITION_TEXT_INPUT_KEY or \
       not settings.COMPOSITION_FILE_INPUT_KEY or \
       not settings.COMPOSITION_TEXT_OUTPUT_KEY:
        print("[API ERROR] Composition correction service is not properly configured in settings.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="作文批改服务配置不完整。")

    if not composition_text and not composition_image:
        print("[API VALIDATION] User must provide either text or an image for composition correction.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请提供作文文本或上传作文图片。")

    dify_user_identifier = str(current_user.id)
    workflow_inputs: Dict[str, Any] = {}
    temp_filepath: Optional[str] = None # Initialize for finally block
    original_filename: Optional[str] = None

    try:
        # 处理文本输入
        if composition_text:
            workflow_inputs[settings.COMPOSITION_TEXT_INPUT_KEY] = composition_text
            print(f"Composition text for Dify: '{composition_text}' using key '{settings.COMPOSITION_TEXT_INPUT_KEY}'")

        # 处理图片文件输入
        if composition_image:
            original_filename = composition_image.filename
            if not original_filename: # Should not happen if UploadFile is present
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传的作文图片没有有效的文件名。")
            
            file_extension = os.path.splitext(original_filename)[1]
            temp_filename_only = f"{uuid.uuid4()}{file_extension}"
            temp_filepath = os.path.join(TEMP_UPLOAD_DIR, temp_filename_only)
            
            print(f"Saving uploaded composition image temporarily to: {temp_filepath}")
            try:
                with open(temp_filepath, "wb") as buffer:
                    content = await composition_image.read()
                    buffer.write(content)
            except Exception as e_save:
                print(f"Error saving temporary file: {e_save}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="保存上传文件时出错。")
            finally:
                await composition_image.close() # Ensure file is closed

            dify_file_category, mime_type, detected_ext = determine_file_category_and_mime(original_filename)
            
            # 根据Dify文档，文件类型（type）可以是 "image", "document", "audio", "video", "custom"
            # 对于作文批改，我们主要期望图片。
            if not dify_file_category or dify_file_category != "image": # 严格要求是图片类型
                if temp_filepath and os.path.exists(temp_filepath): os.remove(temp_filepath)
                print(f"Invalid file type for composition: {dify_file_category}, original: {original_filename}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"作文批改仅支持图片文件。检测到的类型: {dify_file_category or '未知'}")

            if not mime_type: # Should be set if category is "image"
                if temp_filepath and os.path.exists(temp_filepath): os.remove(temp_filepath)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法确定上传文件的MIME类型。")

            # 上传文件到Dify的文件服务获取upload_file_id
            print(f"Uploading '{original_filename}' (as Dify type '{dify_file_category}') to Dify file service for user '{dify_user_identifier}'...")
            dify_upload_id = upload_file_to_dify(
                temp_filepath,
                mime_type,
                dify_user_identifier,
                api_base_url=settings.COMPOSITION_APP_BASE_URL, # Pass app-specific URL
                api_key=settings.COMPOSITION_APP_API_KEY      # Pass app-specific Key
            )
            print(f"Composition image uploaded to Dify, Dify Upload ID: {dify_upload_id}")
            
            # --- MODIFICATION: Pass a single file object, not a list ---
            # Dify的错误信息 "composition_image in input form must be a file" 暗示
            # 这个特定的输入变量期望一个文件对象，而不是文件对象列表。
            workflow_inputs[settings.COMPOSITION_FILE_INPUT_KEY] = {
                "transfer_method": "local_file", # Per Dify docs for uploaded files
                "upload_file_id": dify_upload_id,
                "type": dify_file_category       # e.g., "image" (来自 determine_file_category_and_mime)
            }
            # --- END MODIFICATION ---
            print(f"Composition image input for Dify (as single object): using key '{settings.COMPOSITION_FILE_INPUT_KEY}' with ID '{dify_upload_id}' and type '{dify_file_category}'")
        
        # 确保至少有一个输入被处理了 (文本或图片)
        if not workflow_inputs:
             # This case should ideally be caught by the initial check:
             # `if not composition_text and not composition_image:`
             # But as a safeguard:
             print("[API VALIDATION] No inputs were prepared for Dify workflow.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未提供有效输入进行作文批改。")
        
        # 构建发送给Dify的完整payload
        dify_payload = {
            "inputs": workflow_inputs,
            "response_mode": "blocking",
            "user": dify_user_identifier,
        }
        
        # 调用Dify API
        print(f"Calling Dify workflow for composition correction with payload: {json.dumps(dify_payload, indent=2, ensure_ascii=False)}")
        dify_response_data = call_dify_api(
            dify_base_url=settings.COMPOSITION_APP_BASE_URL,
            dify_api_key=settings.COMPOSITION_APP_API_KEY,
            dify_api_endpoint_path=settings.COMPOSITION_APP_API_ENDPOINT, # Usually "/workflows/run"
            payload=dify_payload
        )
        
        # 从Dify响应中提取批改结果文本
        ai_feedback_text = extract_text_from_dify_response(dify_response_data, settings.COMPOSITION_TEXT_OUTPUT_KEY)
        
        return {
            "message": "作文批改请求已处理。",
            "ai_text": ai_feedback_text,
            "dify_full_outputs": dify_response_data
        }

    except DifyWorkflowError as e:
        print(f"[API ERROR] DifyWorkflowError during composition correction: {str(e)}, Details: {e.details}")
        # Try to extract a more user-friendly message from Dify's error details if possible
        detail_message = str(e)
        if e.details and isinstance(e.details, dict) and "message" in e.details:
            detail_message = f"Dify服务错误: {e.details['message']}"
        raise HTTPException(status_code=e.status_code, detail=detail_message)
    except HTTPException: # Re-raise if it's already an HTTPException (e.g., from file validation)
        raise
    except IOError as e:
        print(f"[API ERROR] IOError during composition correction: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件处理失败: {str(e)}")
    except ValueError as e:
        print(f"[API ERROR] ValueError during composition correction: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"请求参数或数据格式错误: {str(e)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"作文批改时发生意外服务器错误。")
    finally:
        # 清理临时上传的文件
        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
                print(f"Temporary composition file {temp_filepath} removed.")
            except Exception as e_remove:
                print(f"Error removing temp composition file {temp_filepath}: {e_remove}")

@router.post("/generate-vocabulary", summary="Generate vocabulary based on keywords")
async def generate_vocabulary_endpoint(
    request_data: GenerateWordsRequest,
    current_user: UserModel = Depends(get_current_active_user),
):
    if not settings.VOCAB_GEN_APP_API_KEY or not settings.VOCAB_GEN_APP_BASE_URL: # 检查 Base URL
        raise HTTPException(status_code=503, detail="单词生成服务未正确配置 (API Key or Base URL)。")
    if not settings.VOCAB_GEN_APP_API_ENDPOINT or not settings.VOCAB_GEN_INPUT_KEY or not settings.VOCAB_GEN_WORD_COUNT_KEY or not settings.VOCAB_GEN_OUTPUT_KEY:
        raise HTTPException(status_code=503, detail="单词生成服务Dify工作流变量名未正确配置。")


    dify_user_identifier = str(current_user.id)
    
    # 构建发送给 Dify 工作流的 inputs 对象
    dify_workflow_inputs = {
        settings.VOCAB_GEN_INPUT_KEY: request_data.keywords,
        settings.VOCAB_GEN_WORD_COUNT_KEY: request_data.word_count # 使用配置的键名
    }

    dify_payload = {
        "inputs": dify_workflow_inputs,
        "response_mode": "blocking",
        "user": dify_user_identifier,
    }
    try:
        print(f"Calling Vocab Gen Dify. User: {dify_user_identifier}, Inputs: {dify_workflow_inputs}")
        dify_response_data = call_dify_api(
            dify_base_url=settings.VOCAB_GEN_APP_BASE_URL,
            dify_api_key=settings.VOCAB_GEN_APP_API_KEY,
            dify_api_endpoint_path=settings.VOCAB_GEN_APP_API_ENDPOINT,
            payload=dify_payload
        )
        
        generated_words_data = dify_response_data.get(settings.VOCAB_GEN_OUTPUT_KEY)
        generated_words: List[Dict[str, Any]] = []

        if isinstance(generated_words_data, str):
            try:
                parsed_data = json.loads(generated_words_data)
                if isinstance(parsed_data, list): generated_words = parsed_data
                else: raise DifyWorkflowError("AI返回的单词列表格式无效 (解析后不是列表)。", details=dify_response_data)
            except json.JSONDecodeError:
                raise DifyWorkflowError(f"AI返回的单词列表格式无效 (JSON字符串解析失败)。内容: {generated_words_data[:200]}...", details=dify_response_data)
        elif isinstance(generated_words_data, list):
            generated_words = generated_words_data
        else:
            raise DifyWorkflowError("AI未能生成有效的单词列表 (期望列表或JSON字符串)。", details=dify_response_data)

        return {"message": "单词列表生成成功。", "words": generated_words, "dify_full_outputs": dify_response_data}
    except DifyWorkflowError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成单词时发生意外错误: {type(e).__name__}")


@router.post("/parse-grammar", summary="Parse grammar of the provided text using Dify")
async def parse_grammar_endpoint(
    request_data: ParseGrammarRequest, # Uses ParseGrammarRequest Pydantic model
    current_user: UserModel = Depends(get_current_active_user),
):
    if not settings.GRAMMAR_PARSE_APP_API_KEY or not settings.GRAMMAR_PARSE_APP_BASE_URL or not settings.GRAMMAR_PARSE_APP_API_ENDPOINT:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="语法解析服务未正确配置。")

    dify_user_identifier = str(current_user.id)
    
    dify_payload = {
        "inputs": {
            settings.GRAMMAR_PARSE_INPUT_KEY: request_data.text_to_parse
        },
        "response_mode": "blocking",
        "user": dify_user_identifier,
    }

    try:
        print(f"Calling Grammar Parse Dify. User: {dify_user_identifier}, Text: '{request_data.text_to_parse[:50]}...'")
        dify_response_data = call_dify_api(
            dify_base_url=settings.GRAMMAR_PARSE_APP_BASE_URL,
            dify_api_key=settings.GRAMMAR_PARSE_APP_API_KEY,
            dify_api_endpoint_path=settings.GRAMMAR_PARSE_APP_API_ENDPOINT,
            payload=dify_payload
        )
        
        parsed_result_text = extract_text_from_dify_response(dify_response_data, settings.GRAMMAR_PARSE_OUTPUT_KEY)
        
        return {
            "message": "文本语法解析成功。",
            "ai_text": parsed_result_text, # Using ai_text for consistency in frontend if it expects this
            "parsed_result": parsed_result_text, # Or a more specific key
            "dify_full_outputs": dify_response_data
        }
    except DifyWorkflowError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"语法解析时发生意外错误: {type(e).__name__}")

# Remember to include your vocabulary_api.router in app/main.py if it's in a separate file.
# For example, if you created backend/app/apis/vocabulary_api.py:
# from . import vocabulary_api
# router.include_router(vocabulary_api.router, prefix="/vocabulary", tags=["Vocabulary Learning"])
# (Adjust prefix and tags as needed)