import os
import json
import logging
import time
import shutil
import hashlib
import subprocess
import sys
import threading
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel
from src.utils.config import get_config, PATHS
from src.services.storage import storage

router = APIRouter(prefix="/api/admin")
logger = logging.getLogger("admin_api")

class AdminAuth(BaseModel):
    password: str = None

class RelPathRequest(BaseModel):
    password: str = None
    relPath: str

class CreateFolderRequest(BaseModel):
    password: str = None
    parentPath: str = ""
    folderName: str

def check_admin_auth(password: str):
    config = get_config()
    expected_password = config.get('correction_password')
    if expected_password and password != expected_password:
        raise HTTPException(status_code=401, detail="Nieprawidłowe hasło.")

def build_doc_tree(path, root, show_hidden=False, trace_dir=None):
    tree = []
    try:
        items = sorted(os.listdir(path), key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))
        for item in items:
            full_path = os.path.join(path, item)
            rel_path = os.path.relpath(full_path, root)
            
            is_hidden = item.endswith('.hidden') or '.hidden' in rel_path
            if is_hidden and not show_hidden:
                continue
                
            display_name = item.replace('.hidden', '')
            safe_rel_path = rel_path.replace('\\', '/')
            
            if os.path.isdir(full_path):
                tree.append({
                    "name": display_name,
                    "type": "folder",
                    "isHidden": is_hidden,
                    "relPath": safe_rel_path,
                    "children": build_doc_tree(full_path, root, show_hidden, trace_dir)
                })
            else:
                if item.lower().endswith(('.txt', '.hash')): continue
                
                has_trace = False
                trace_url = None
                if trace_dir and item.lower().endswith('.pdf'):
                    hash_file_path = full_path + ".hash"
                    file_hash = None
                    if os.path.exists(hash_file_path):
                        try:
                            with open(hash_file_path, 'r', encoding='utf-8') as f:
                                file_hash = f.read().strip()
                        except: pass
                    
                    if file_hash:
                        trace_rel_path = f"{file_hash}.json"
                        trace_full_path = os.path.normpath(os.path.join(trace_dir, trace_rel_path))
                        if os.path.exists(trace_full_path):
                            has_trace = True
                            trace_url = f"/api/admin/trace-content?relPath={trace_rel_path}"

                tree.append({
                    "name": display_name,
                    "type": "file",
                    "isHidden": is_hidden,
                    "relPath": safe_rel_path,
                    "hasTrace": has_trace,
                    "traceUrl": trace_url,
                    "url": f"/documents/{safe_rel_path}"
                })
    except Exception as e:
        logger.error(f"Error building tree for {path}: {e}")
    return tree

@router.get("/stats")
async def get_stats():
    config = get_config()
    documents_root = PATHS['documents_dir']
    trace_root = PATHS['traces_dir']
    trace_dir = os.path.join(trace_root, f"{config['trace_length']}_{config['doc_tracing_model']}")
    
    total_docs = 0
    docs_with_traces = 0
    current_fingerprint = []
    
    for root, _, files in os.walk(documents_root):
        if '.hidden' in root: continue
        for file in files:
            if file.lower().endswith('.pdf') and not file.endswith('.hidden'):
                total_docs += 1
                pdf_path = os.path.join(root, file)
                rel_pdf_path = os.path.relpath(pdf_path, documents_root)
                hash_file = pdf_path + ".hash"
                if os.path.exists(hash_file):
                    with open(hash_file, 'r', encoding='utf-8') as f:
                        file_hash = f.read().strip()
                        current_fingerprint.append(f"{rel_pdf_path.replace(os.sep, '/')}:{file_hash}")
                        if os.path.exists(os.path.join(trace_dir, f"{file_hash}.json")):
                            docs_with_traces += 1
                else:
                    current_fingerprint.append(f"{rel_pdf_path.replace(os.sep, '/')}:missing")
    
    current_fingerprint.sort()
    current_fingerprint_hash = hashlib.sha256(json.dumps(current_fingerprint).encode('utf-8')).hexdigest()
    
    kb_stats = {}
    kb_stats_path = PATHS['kb_stats']
    if os.path.exists(kb_stats_path):
        try:
            with open(kb_stats_path, 'r', encoding='utf-8') as f:
                kb_stats = json.load(f)
        except: pass

    stored_fingerprint = kb_stats.get("fingerprint_hash", "")
    is_up_to_date = (current_fingerprint_hash == stored_fingerprint) if stored_fingerprint else False

    return {
        "total_docs": total_docs,
        "docs_with_traces": docs_with_traces,
        "kb_tokens": kb_stats.get("token_count", 0),
        "last_sync": kb_stats.get("timestamp", "Wymagana synchronizacja"),
        "is_up_to_date": is_up_to_date,
        "current_model": config["doc_tracing_model"],
        "trace_length": config["trace_length"]
    }

@router.get("/documents")
async def get_documents():
    config = get_config()
    documents_root = PATHS['documents_dir']
    trace_dir = os.path.join(PATHS['traces_dir'], f"{config['trace_length']}_{config['doc_tracing_model']}")
    return build_doc_tree(documents_root, documents_root, show_hidden=True, trace_dir=trace_dir)

@router.post("/remove")
async def remove_item(request: RelPathRequest):
    check_admin_auth(request.password)
    rel_path = request.relPath
    target_path = os.path.abspath(os.path.join(PATHS['documents_dir'], rel_path.replace('/', os.sep)))
    if not target_path.startswith(os.path.abspath(PATHS['documents_dir'])):
        raise HTTPException(status_code=403, detail="Invalid path")
    if os.path.exists(target_path):
        if os.path.isdir(target_path): shutil.rmtree(target_path)
        else:
            os.remove(target_path)
            if os.path.exists(target_path + ".hash"): os.remove(target_path + ".hash")
        return {"success": True}
    raise HTTPException(status_code=404, detail="Not found")

@router.post("/toggle-visibility")
async def toggle_visibility(request: RelPathRequest):
    check_admin_auth(request.password)
    rel_path = request.relPath
    target_path = os.path.abspath(os.path.join(PATHS['documents_dir'], rel_path.replace('/', os.sep)))
    if not target_path.startswith(os.path.abspath(PATHS['documents_dir'])):
        raise HTTPException(status_code=403, detail="Invalid path")
    new_path = target_path[:-7] if target_path.endswith('.hidden') else target_path + '.hidden'
    if os.path.exists(target_path):
        os.rename(target_path, new_path)
        return {"success": True, "newPath": os.path.relpath(new_path, PATHS['documents_dir'])}
    raise HTTPException(status_code=404, detail="Not found")

@router.post("/create-folder")
async def create_folder(request: CreateFolderRequest):
    check_admin_auth(request.password)
    parent_rel_path = request.parentPath
    folder_name = request.folderName
    target_dir = os.path.abspath(os.path.join(PATHS['documents_dir'], parent_rel_path.replace('/', os.sep), folder_name))
    if not target_dir.startswith(os.path.abspath(PATHS['documents_dir'])):
        raise HTTPException(status_code=403, detail="Invalid path")
    os.makedirs(target_dir, exist_ok=True)
    return {"success": True}

@router.post("/upload")
async def upload_file(password: str = Form(...), parentPath: str = Form(""), file: UploadFile = File(...)):
    check_admin_auth(password)
    target_path = os.path.abspath(os.path.join(PATHS['documents_dir'], parentPath.replace('/', os.sep), file.filename))
    if not target_path.startswith(os.path.abspath(PATHS['documents_dir'])):
        raise HTTPException(status_code=403, detail="Invalid path")
    content = await file.read()
    with open(target_path, 'wb') as f: f.write(content)
    file_hash = hashlib.sha256(content).hexdigest()
    with open(target_path + ".hash", 'w', encoding='utf-8') as f: f.write(file_hash)
    return {"success": True}

@router.post("/sync")
async def trigger_sync(request: AdminAuth):
    check_admin_auth(request.password)
    log_path = os.path.join(PATHS['run_dir'], 'sync.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(f"--- Synchronizacja rozpoczęta: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    
    def run_sync():
        try:
            trace_script = os.path.join(os.path.dirname(__file__), '../create_document_traces.py')
            master_script = os.path.join(os.path.dirname(__file__), '../create_master_session.py')
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            with open(log_path, 'a', encoding='utf-8') as log_f:
                p1 = subprocess.Popen([sys.executable, trace_script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
                for line in p1.stdout: log_f.write(line); log_f.flush()
                p1.wait()
                if p1.returncode != 0: return
                p2 = subprocess.Popen([sys.executable, master_script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
                for line in p2.stdout: log_f.write(line); log_f.flush()
                p2.wait()
                if p2.returncode == 0: storage.load_doc_index()
        except Exception as e: logger.error(f"Sync error: {e}")

    threading.Thread(target=run_sync, daemon=True).start()
    return {"success": True}

@router.get("/trace-content")
async def get_trace_content(relPath: str = Query(...)):
    config = get_config()
    trace_dir = os.path.join(PATHS['traces_dir'], f"{config['trace_length']}_{config['doc_tracing_model']}")
    file_path = os.path.abspath(os.path.join(trace_dir, relPath.replace('/', os.sep)))
    if not file_path.startswith(os.path.abspath(trace_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Trace file not found")

@router.get("/sync-log")
async def get_sync_log():
    log_path = os.path.join(PATHS['run_dir'], 'sync.log')
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""
