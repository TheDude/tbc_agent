"""
Tool: google_drive — search, inspect, and read files from Google Drive.

Requires the GOOGLE_SERVICE_ACCOUNT_KEY_FILE environment variable to point to
a Google service account JSON key file. The service account must have been
granted access (read) to the Drive files it needs to reach.
"""

import json
import os
import tempfile

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from pydantic_ai import Tool

from tbc_agent.auth.google import get_google_drive_credentials
from tbc_agent.auth.oauth_client import (
    OauthAuthorizationDeclined,
    OauthConfigMissing,
    OauthRefreshFailed,
)

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

_EXPORT_MIME_MAP = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

_drive_service = None




def _try_oauth_service():
    try:
        breakpoint()
        creds = get_google_drive_credentials()
        return build("drive", "v3", credentials=creds)
    except (OauthConfigMissing, OauthAuthorizationDeclined, OauthRefreshFailed) as exc:
        return str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return str(exc)


def _try_service_account():
    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE")
    if not key_file:
        return "GOOGLE_SERVICE_ACCOUNT_KEY_FILE environment variable is not set. Provide the path to a service account JSON key file."

    try:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(key_file), scopes=_SCOPES
        )
        return build("drive", "v3", credentials=credentials)
    except Exception as exc:  # pragma: no cover - defensive
        return str(exc)


def _get_drive_service():
    global _drive_service
    if _drive_service is not None:
        return _drive_service

    oauth_result = _try_oauth_service()
    if not isinstance(oauth_result, str):
        _drive_service = oauth_result
        return _drive_service

    fallback_result = _try_service_account()
    if isinstance(fallback_result, str):
        raise RuntimeError(
            "Failed to establish Google Drive credentials via OAuth2 and service account."
            f" OAuth2 error: {oauth_result}; Service account error: {fallback_result}"
        )

    _drive_service = fallback_result
    return _drive_service


def _reset_drive_service():
    global _drive_service
    _drive_service = None


def gd_search(query: str) -> str:
    """
    Search Google Drive and return matching files.
    
    Args:
        query: Google Drive search query string. Examples:
            - 'name contains "report"'
            - 'mimeType = "application/vnd.google-apps.document"'  
            - 'modifiedTime > 2024-01-01'
            - 'owners contains "user@example.com"'
            - 'sharedWithMe = true'
            - Combined: 'name contains "budget" and mimeType = "application/vnd.google-apps.spreadsheet"'
    
    Returns:
        JSON string with array of file objects containing: id, name, mimeType, modifiedTime, owners
        Example: {"files": [{"id": "...", "name": "...", ...}, ...]}
        Or error: {"error": "...", "message": "..."}
    """
    try:
        service = _get_drive_service()
        
        results = (
            service.files()
            .list(
                q=query,
                pageSize=20,
                fields="files(id, name, mimeType, modifiedTime, owners(emailAddress))",
            )
            .execute()
        )
        
        files = results.get("files", [])
        return json.dumps({"files": files}, indent=2)
        
    except HttpError as e:
        return json.dumps({
            "error": "search_failed",
            "message": str(e),
            "status": e.resp.status if hasattr(e, 'resp') else None
        })
    except Exception as e:
        return json.dumps({
            "error": "unexpected_error",
            "message": str(e)
        })

def gd_read_metadata(file_id: str) -> str:
    """
    Get metadata for a specific Google Drive file.
    
    Args:
        file_id: The Google Drive file ID
        
    Returns:
        JSON string with file metadata including: id, name, mimeType, size, 
        createdTime, modifiedTime, owners, shared, webViewLink, capabilities
        Or error: {"error": "...", "message": "..."}
    """
    try:
        service = _get_drive_service()
        
        file_metadata = (
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, size, createdTime, modifiedTime, "
                       "owners(emailAddress), shared, webViewLink, capabilities",
            )
            .execute()
        )
        
        return json.dumps(file_metadata, indent=2)
        
    except HttpError as e:
        if e.resp.status == 404:
            error_type = "file_not_found"
        elif e.resp.status == 403:
            error_type = "permission_denied"
        else:
            error_type = "metadata_fetch_failed"
            
        return json.dumps({
            "error": error_type,
            "message": str(e),
            "status": e.resp.status if hasattr(e, 'resp') else None
        })
    except Exception as e:
        return json.dumps({
            "error": "unexpected_error",
            "message": str(e)
        })

def gd_read_file(file_id: str) -> str:
    """
    Download and extract plaintext content from a Google Drive file.
    
    For Google Workspace files (Docs, Sheets, Slides), exports to appropriate format.
    For other files, downloads directly.
    
    Args:
        file_id: The Google Drive file ID
        
    Returns:
        Plaintext content of the file
        Or error: {"error": "...", "message": "..."}
    """
    temp_path = None
    try:
        service = _get_drive_service()
        
        metadata = (
            service.files()
            .get(fileId=file_id, fields="id, name, mimeType")
            .execute()
        )
        
        mime_type = metadata.get("mimeType", "")
        export_mime = _EXPORT_MIME_MAP.get(mime_type)
        
        if export_mime:
            request = service.files().export_media(
                fileId=file_id,
                mimeType=export_mime
            )
        else:
            request = service.files().get_media(fileId=file_id)
        
        with tempfile.NamedTemporaryFile(
            mode='wb',
            delete=False,
            suffix='.tmp'
        ) as temp_file:
            temp_path = temp_file.name
            
            downloader = MediaIoBaseDownload(temp_file, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return content
        
    except HttpError as e:
        if e.resp.status == 404:
            error_type = "file_not_found"
        elif e.resp.status == 403:
            error_type = "permission_denied"
        else:
            error_type = "download_failed"
            
        return json.dumps({
            "error": error_type,
            "message": str(e),
            "status": e.resp.status if hasattr(e, 'resp') else None
        })
    except UnicodeDecodeError as e:
        return json.dumps({
            "error": "encoding_error",
            "message": f"File is not valid UTF-8 text: {str(e)}"
        })
    except Exception as e:
        return json.dumps({
            "error": "unexpected_error",
            "message": str(e)
        })
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


tools = [
    Tool(gd_search),
    Tool(gd_read_metadata),
    Tool(gd_read_file),
]
