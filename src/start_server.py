import os
import sys
import argparse
import subprocess
import uvicorn
import logging

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from src.utils.config import setup_logging, PATHS

def run_server():
    parser = argparse.ArgumentParser(description="FDDS RAG Server (FastAPI)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--blocking", action="store_true", help="Run in foreground")
    args = parser.parse_args()

    log_file_path = os.path.join(PATHS['server_logs_dir'], f'server_{args.port}.log')
    pid_file_path = os.path.join(PATHS['run_dir'], f'server_{args.port}.pid')

    if not args.blocking:
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        log_file = open(log_file_path, 'a', encoding='utf-8')
        
        # We call this script again with --blocking to start uvicorn
        process = subprocess.Popen(
            [sys.executable, __file__, "--port", str(args.port), "--blocking"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            start_new_session=True if os.name != 'nt' else False
        )
        
        os.makedirs(os.path.dirname(pid_file_path), exist_ok=True)
        with open(pid_file_path, 'w') as f:
            f.write(str(process.pid))
        
        print(f"FastAPI Server started in background (PID: {process.pid})")
        print(f"Logs: {log_file_path}")
        return

    # In blocking mode, we run uvicorn
    setup_logging(level=logging.INFO)
    print(f"Starting FDDS FastAPI Server on port {args.port}...")
    
    try:
        # Import app inside run_server to avoid issues with multiprocess/spawning
        from src.main import app
        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        if os.path.exists(pid_file_path):
            try: os.remove(pid_file_path)
            except: pass

if __name__ == "__main__":
    run_server()
