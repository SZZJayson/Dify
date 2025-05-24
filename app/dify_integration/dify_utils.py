# backend/app/dify_integration/dify_utils.py
import os
import requests
from typing import Tuple, Optional as PyOptional

from app.core.config import settings # Import settings

def upload_file_to_dify(
    file_path: str,
    mime_type: str,
    dify_user: str,
    api_base_url: str, # 新增参数
    api_key: str       # 新增参数
) -> str:
    """Uploads a file to Dify's file service using specific base_url and api_key."""
    if not api_base_url or not api_key: # 使用传入的参数
        raise ValueError("Dify api_base_url or api_key was not provided for file upload.")
    
    url = f"{api_base_url.rstrip('/')}/files/upload" # 使用传入的 api_base_url
    headers = {"Authorization": f"Bearer {api_key}"}   # 使用传入的 api_key
    
    try:
        with open(file_path, "rb") as f:
            files_payload = {"file": (os.path.basename(file_path), f, mime_type)}
            data_payload = {"user": dify_user}
            print(f"Uploading to Dify: URL={url}, User={dify_user}, Filename={os.path.basename(file_path)}, MIME={mime_type}")
            resp = requests.post(url, headers=headers, files=files_payload, data=data_payload, timeout=60)
        resp.raise_for_status()
        response_json = resp.json()
        print(f"Dify file upload successful: {response_json}")
        if "id" not in response_json:
            raise ValueError("Dify file upload response did not contain an 'id'.")
        return response_json["id"]
    except requests.exceptions.RequestException as e:
        error_message = f"Error uploading file to Dify: {e}"
        if hasattr(e, 'response') and e.response is not None:
            error_message += f" | Response: {e.response.text}"
        print(f"[ERROR] {error_message}")
        raise IOError(error_message)
    except (KeyError, ValueError) as e:
        error_message = f"Error parsing Dify file upload response: {e}"
        print(f"[ERROR] {error_message}")
        raise ValueError(error_message)


def determine_file_category_and_mime(filename: str) -> Tuple[PyOptional[str], PyOptional[str], PyOptional[str]]:
    """Determines Dify category and MIME type based on file extension."""
    ext = os.path.splitext(filename)[1].lower()
    category: PyOptional[str] = None
    mime: PyOptional[str] = None

    image_mime_map = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp",
    }
    doc_mime_map = { # Added for potential future use, though chat/composition focus on images
        ".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
        ".csv": "text/csv",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    
    if ext in image_mime_map:
        category = "image"
        mime = image_mime_map.get(ext)
    elif ext in doc_mime_map: # If a document is uploaded for a feature that supports it
        category = "document"
        mime = doc_mime_map.get(ext)
    else:
        print(f"Unsupported file extension: {ext} for filename: {filename}. Will not assign Dify category/mime.")
        return None, None, ext # Return None if type is not explicitly supported or recognized

    return category, mime, ext