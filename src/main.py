import os
import sys
import logging
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from starlette.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

# Load environment variables once at boot
load_dotenv(os.path.join(os.path.dirname(__file__), '../config/.env'))

# --- FAIL FAST: API Key Check ---
if not os.environ.get("GEMINI_API_KEY"):
    print("FATAL: GEMINI_API_KEY environment variable is not set.")
    print("Please set it in your environment before starting the server.")
    sys.exit(1)

from src.utils.config import setup_logging, PATHS, get_config
from src.api.admin import router as admin_router
from src.api.chat import router as chat_router
from src.api.config import router as config_router

app = FastAPI(title="FDDS AI Assistant")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(config_router)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.error(f"Validation error: {exc.errors()} on path {request.url.path}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": str(exc.body)},
    )

# --- Static Routes & File Serving ---

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), '../public/index.html'))

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin():
    return FileResponse(os.path.join(os.path.dirname(__file__), '../public/admin.html'))

@app.get("/correction", response_class=HTMLResponse)
async def serve_correction():
    return FileResponse(os.path.join(os.path.dirname(__file__), '../public/correction.html'))

# Document serving
@app.get("/documents/{file_path:path}")
async def serve_documents(file_path: str):
    abs_path = os.path.abspath(os.path.join(PATHS['documents_dir'], file_path))
    if not abs_path.startswith(os.path.abspath(PATHS['documents_dir'])):
        raise HTTPException(status_code=403, detail="Access denied")
    if os.path.exists(abs_path) and os.path.isfile(abs_path):
        return FileResponse(abs_path)
    raise HTTPException(status_code=404, detail="File not found")

# Audio serving
@app.get("/audio/{file_path:path}")
async def serve_audio(file_path: str, chatId: str):
    if chatId not in file_path:
        raise HTTPException(status_code=403, detail="Access denied")
    
    abs_path = os.path.abspath(os.path.join(PATHS['user_audio_dir'], file_path))
    if os.path.exists(abs_path) and os.path.isfile(abs_path):
        return FileResponse(abs_path, media_type="audio/wav")
    raise HTTPException(status_code=404, detail="Audio not found")

# Serve other public assets
app.mount("/assets", StaticFiles(directory="public/assets"), name="assets")

if __name__ == "__main__":
    setup_logging(level=logging.DEBUG)
    uvicorn.run(app, host="0.0.0.0", port=8000)
