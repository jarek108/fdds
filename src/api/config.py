import os
import json
import logging
import subprocess
import sys
from fastapi import APIRouter, HTTPException
from src.utils.config import get_config, PATHS
from src.services.storage import storage

router = APIRouter()
logger = logging.getLogger("config_api")

@router.get("/api/config")
async def get_public_config():
    config = get_config()
    return {
        "audio_recording_timeout_s": config.get("audio_recording_timeout_s", 30)
    }

@router.get("/api/correction")
async def get_correction():
    correction_path = PATHS['correction_file']
    if os.path.exists(correction_path):
        with open(correction_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

@router.post("/api/correction")
async def update_correction(request: dict):
    # Check auth
    config = get_config()
    expected_password = config.get('correction_password')
    if expected_password and request.get('password') != expected_password:
        raise HTTPException(status_code=401, detail="Nieprawidłowe hasło.")
    
    content = request.get('content', '')
    correction_path = PATHS['correction_file']
    os.makedirs(os.path.dirname(correction_path), exist_ok=True)
    with open(correction_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Rebuild master session
    try:
        script_path = os.path.join(os.path.dirname(__file__), '../create_master_session.py')
        subprocess.run([sys.executable, script_path], capture_output=True, check=True)
        storage.load_doc_index()
    except Exception as e:
        logger.error(f"Failed to rebuild master session: {e}")
        raise HTTPException(status_code=500, detail="Correction saved but master session rebuild failed.")
    
    return {"success": True}
