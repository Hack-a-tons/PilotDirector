from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from typing import Optional
import os
import json
import asyncio
import traceback

# Load environment variables from .env/.env.local (repo root or agent dir) if present
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # python-dotenv may not be installed yet

def _load_env_files() -> None:
    if load_dotenv is None:
        return
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / ".env.local",  # repo root/.env.local
        here.parents[2] / ".env",        # repo root/.env
        here.parents[1] / ".env.local",  # agent/.env.local
        here.parents[1] / ".env",        # agent/.env
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=False)

_load_env_files()

from .agent import agentic_chat_router, current_user_id
from .sheets_integration import get_sheet_data, convert_sheet_to_canvas_items, sync_canvas_to_sheet, get_sheet_names, create_new_sheet

app = FastAPI()

# Add error handling middleware
@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        # Check for Azure OpenAI content filter error
        if "content_filter" in str(e) or "ResponsibleAIPolicyViolation" in str(e):
            print(f"[ERROR] Content filter triggered: {str(e)}")
            return JSONResponse(
                status_code=200,  # Return 200 to avoid frontend errors
                content={
                    "error": "I apologize, but I cannot process that request due to content policy restrictions. Please try rephrasing your request or ask for help with a different video editing task."
                }
            )
        else:
            print(f"[ERROR] Unexpected error: {str(e)}")
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            raise e

# Middleware to extract user_id from headers and log requests
@app.middleware("http")
async def set_user_context_and_log(request: Request, call_next):
    user_id = request.headers.get('x-user-id', 'default')
    current_user_id.set(user_id)
    
    # Log incoming requests
    if request.url.path == "/run":
        try:
            body = await request.body()
            if body:
                request_data = json.loads(body)
                messages = request_data.get('messages', [])
                if messages:
                    last_message = messages[-1].get('content', '')
                    print(f"[CHAT] User: {last_message}")
        except Exception as e:
            print(f"[DEBUG] Could not parse request body: {e}")
        
        # Recreate request with body for downstream processing
        from starlette.requests import Request as StarletteRequest
        request = StarletteRequest(request.scope, receive=lambda: {"type": "http.request", "body": body})
    
    response = await call_next(request)
    
    # Simple response logging for /run endpoint
    if request.url.path == "/run":
        try:
            # Just log that we got a response - the content is too complex to parse reliably
            print(f"[DEBUG] AI response sent to client")
        except Exception as e:
            print(f"[DEBUG] Response logging error: {e}")
    
    return response

app.include_router(agentic_chat_router)

# Request models
class SheetSyncRequest(BaseModel):
    sheet_id: str
    sheet_name: Optional[str] = None

class CanvasToSheetSyncRequest(BaseModel):
    canvas_state: dict
    sheet_id: str
    sheet_name: Optional[str] = None

class CreateSheetRequest(BaseModel):
    title: str

# Sheets sync endpoint
@app.post("/sheets/sync")
async def sync_sheets(request: SheetSyncRequest):
    """
    Sync data from Google Sheets to canvas format.
    
    Args:
        request: Contains sheet_id to import from
        
    Returns:
        Canvas state with items converted from sheet data
    """
    try:
        # Extract sheet ID from URL if full URL is provided
        sheet_id = request.sheet_id
        if "/spreadsheets/d/" in sheet_id:
            # Extract ID from Google Sheets URL
            start = sheet_id.find("/spreadsheets/d/") + len("/spreadsheets/d/")
            end = sheet_id.find("/", start)
            if end == -1:
                end = sheet_id.find("#", start)
            if end == -1:
                end = len(sheet_id)
            sheet_id = sheet_id[start:end]
        
        sheet_name = request.sheet_name
        if sheet_name:
            print(f"Syncing sheet: {sheet_id} (sheet: {sheet_name})")
        else:
            print(f"Syncing sheet: {sheet_id} (default sheet)")
        
        # Fetch sheet data using Composio
        sheet_data = get_sheet_data(sheet_id, sheet_name)
        if not sheet_data:
            raise HTTPException(
                status_code=400, 
                detail="Failed to fetch sheet data. Please check the sheet ID and ensure it's accessible."
            )
        
        # Convert to canvas items
        canvas_data = convert_sheet_to_canvas_items(sheet_data, sheet_id)
        
        return JSONResponse(content={
            "success": True,
            "data": canvas_data,
            "message": f"Successfully imported {len(canvas_data['items'])} items from sheet '{canvas_data['globalTitle']}'"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in sheets sync: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/sync-to-sheets")
async def sync_canvas_to_sheets(request: CanvasToSheetSyncRequest):
    """
    Sync canvas state to Google Sheets.
    
    Args:
        request: Contains canvas_state and sheet_id
        
    Returns:
        Sync result status
    """
    try:
        sheet_name_info = f" (sheet: {request.sheet_name})" if request.sheet_name else ""
        print(f"[SYNC] Syncing canvas to sheet: {request.sheet_id}{sheet_name_info}")
        
        # Call the sync function with sheet name
        result = sync_canvas_to_sheet(request.sheet_id, request.canvas_state, request.sheet_name)
        
        if result.get("success"):
            return JSONResponse(content={
                "success": True,
                "message": result.get("message"),
                "items_synced": result.get("items_synced", 0)
            })
        else:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to sync canvas to sheets")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in canvas-to-sheets sync: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/sheets/list")
async def list_sheet_names(request: SheetSyncRequest):
    """
    List available sheet names in a Google Spreadsheet.
    
    Args:
        request: Contains sheet_id
        
    Returns:
        List of available sheet names
    """
    try:
        print(f"Listing sheets in: {request.sheet_id}")
        
        # Get sheet names using Composio
        sheet_names = get_sheet_names(request.sheet_id)
        if not sheet_names:
            raise HTTPException(
                status_code=400, 
                detail="Failed to get sheet names. Please check the sheet ID and ensure it's accessible."
            )
        
        return JSONResponse(content={
            "success": True,
            "sheet_names": sheet_names,
            "count": len(sheet_names)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in sheet listing: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/sheets/create")
async def create_sheet(request: CreateSheetRequest):
    """
    Create a new Google Sheet.
    
    Args:
        request: Contains title for the new sheet
        
    Returns:
        New sheet details including sheet_id and URL
    """
    try:
        print(f"Creating new sheet with title: {request.title}")
        
        # Create new sheet using Composio
        result = create_new_sheet(request.title)
        if not result.get("success"):
            raise HTTPException(
                status_code=400, 
                detail=result.get("error", "Failed to create new sheet")
            )
        
        return JSONResponse(content={
            "success": True,
            "sheet_id": result.get("sheet_id"),
            "sheet_url": result.get("sheet_url"),
            "title": result.get("title"),
            "message": f"Successfully created new sheet '{request.title}'"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating sheet: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
