# backend/app/services/dify_workflow_service.py
import requests
import json
from typing import Dict, Any, Optional as PyOptional

# Settings will be passed or accessed differently now, or functions will take them directly.
# from app.core.config import settings # We might not use the global settings directly here anymore

class DifyWorkflowError(Exception):
    def __init__(self, message: str, status_code: int = 500, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details

def call_dify_api( # Renamed for clarity, as it's more generic now
    dify_base_url: str,
    dify_api_key: str,
    dify_api_endpoint_path: str, # e.g., "/chat-messages" or "/workflows/run"
    payload: Dict[str, Any], # This will contain inputs, user, response_mode, etc.
    timeout: int = 500
) -> Dict[str, Any]:
    """
    A generic function to call a Dify API endpoint.
    The payload should be structured according to Dify's requirements for the specific endpoint.
    """
    if not dify_base_url or not dify_api_key:
        raise DifyWorkflowError("Dify Base URL or API Key was not provided for the API call.", status_code=503)

    url = f"{dify_base_url.rstrip('/')}{dify_api_endpoint_path}"
    headers = {
        "Authorization": f"Bearer {dify_api_key}",
        "Content-Type": "application/json",
    }

    print(f"Calling Dify API: URL={url}, Payload User={payload.get('user')}")
    print(f"Full Payload to Dify ({dify_api_endpoint_path}): {json.dumps(payload, indent=2, ensure_ascii=False)}")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
    # ... (Error handling IDENTICAL to the previous run_dify_workflow function) ...
    except requests.exceptions.Timeout:
        msg = f"Dify request to {dify_api_endpoint_path} timed out after {timeout} seconds."
        print(f"[DIFY API ERROR] {msg}")
        raise DifyWorkflowError(msg, status_code=504, details={"timeout_seconds": timeout, "endpoint": dify_api_endpoint_path})
    except requests.exceptions.ConnectionError as e:
        msg = f"Could not connect to Dify service for {dify_api_endpoint_path}: {e}"
        print(f"[DIFY API ERROR] {msg}")
        raise DifyWorkflowError(msg, status_code=503, details=str(e))
    except requests.exceptions.HTTPError as e:
        error_text = e.response.text
        print(f"[DIFY API ERROR] HTTP error from {dify_api_endpoint_path}: {e.response.status_code} - {error_text}")
        try: error_details = e.response.json()
        except ValueError: error_details = error_text
        raise DifyWorkflowError(f"Dify execution at {dify_api_endpoint_path} failed (status {e.response.status_code}).", status_code=e.response.status_code, details=error_details)
    except requests.exceptions.RequestException as e:
        msg = f"An unexpected error occurred with Dify for {dify_api_endpoint_path}: {e}"
        print(f"[DIFY API ERROR] {msg}")
        raise DifyWorkflowError(msg, status_code=500, details=str(e))


    result = response.json()
    print(f"Dify API Raw Result (from {dify_api_endpoint_path}): {json.dumps(result, indent=2, ensure_ascii=False)}")

    # For /chat-messages or /completion-messages, the structure is different
    if dify_api_endpoint_path in ["/chat-messages", "/completion-messages"]:
        if result.get("answer"):
            return {"answer": result.get("answer"), "conversation_id": result.get("conversation_id")}
        else: # Error or unexpected structure
            dify_status = result.get('status_code', result.get('status', 200))
            dify_message = result.get('message', result.get('code')) # Dify error messages
            if dify_status != 200 or dify_message:
                 error_msg = f"Dify chat/completion error: {dify_message or 'Unknown error'}"
                 print(f"[DIFY API ERROR] {error_msg}")
                 raise DifyWorkflowError(error_msg, status_code=dify_status if isinstance(dify_status, int) else 500, details=result)
            return {"answer": "AI did not provide an answer.", "raw_dify_response": result}

    # For /workflows/run, parse 'outputs' (as before)
    outputs: PyOptional[Dict[str, Any]] = None
    if "outputs" in result and result["outputs"] is not None:
        outputs = result.get("outputs")
    # ... (rest of the outputs parsing logic from your previous run_dify_workflow) ...
    elif "data" in result and isinstance(result.get("data"), dict) and \
         "outputs" in result["data"] and result["data"]["outputs"] is not None:
        outputs = result["data"].get("outputs")
    # No 'answer' fallback here as it's specific to chat/completion types

    if outputs is None:
        dify_status = result.get('status_code', result.get('status', 200))
        dify_message = result.get('message', result.get('error', {}).get('message'))
        if dify_status not in [200, "succeeded", "success"] or result.get('code'):
            error_msg_from_dify = dify_message or 'Unknown Dify internal error in response body.'
            print(f"[DIFY WORKFLOW ERROR] Dify API returned an error structure: {error_msg_from_dify}")
            error_status_code = dify_status if isinstance(dify_status, int) and dify_status >= 400 else 500
            raise DifyWorkflowError(error_msg_from_dify, status_code=error_status_code, details=result)
        return {"text": "AI未能提供标准格式的输出。", "raw_dify_response": result}

    return outputs