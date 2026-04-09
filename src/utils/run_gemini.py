import subprocess
import os
import time
import json
import shutil
import glob
import logging
import uuid
from typing import Optional, Dict, Tuple, Any

# Root setup for standalone execution
if __name__ == "__main__":
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.utils.config import get_config, get_project_root

logger = logging.getLogger("run_gemini")

def load_env():
    """Loads API key from config/.env into environment."""
    env_path = os.path.join(get_project_root(), 'config', '.env')
    if os.path.exists(env_path):
        from dotenv import load_dotenv
        load_dotenv(env_path)

def get_cli_chat_dir():
    """Returns the internal Gemini CLI chat directory."""
    return os.path.join(os.path.expanduser("~"), ".gemini", "tmp", "fdds", "chats")

def sync_session_to_cli(session_id: str, local_path: Optional[str] = None):
    """
    Ensures the session JSON exists in the CLI's internal directory 
    so it can be resumed with -r.
    """
    cli_dir = get_cli_chat_dir()
    os.makedirs(cli_dir, exist_ok=True)
    
    # If we have a specific local path, use it. Otherwise, search data/sessions.
    source_file = local_path
    if not source_file:
        config = get_config()
        base_sessions_dir = config['paths']['sessions_dir']
        matches = glob.glob(os.path.join(base_sessions_dir, f"**/*{session_id[:8]}*.json"), recursive=True)
        if matches:
            source_file = sorted(matches, key=os.path.getmtime, reverse=True)[0]
    
    if source_file and os.path.exists(source_file):
        # The CLI expects filename to be session-{id}.json or {anything}{id}.json
        # To be safe, we use the session-{session_id}.json as the filename.
        target_file = os.path.join(cli_dir, f"session-{session_id}.json")
        if not os.path.exists(target_file) or os.path.getmtime(source_file) > os.path.getmtime(target_file):
            shutil.copy2(source_file, target_file)
            logger.debug(f"Synced session {session_id[:8]} to CLI directory.")

def run_gemini(model_id: str, 
               prompt: str, 
               session_folder: str,
               session_name: Optional[str] = None, 
               session_id: Optional[str] = None, 
               system_prompt_file: Optional[str] = None,
               files: Optional[list] = None,
               max_retries: int = 3) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Executes Gemini API call using the Gemini CLI (subprocess) and returns (answer, metadata, error).
    Maintains compatibility with the SDK-based refactor interface.
    """
    config = get_config()
    paths = config['paths']
    base_sessions_dir = paths['sessions_dir']
    target_sessions_dir = os.path.join(base_sessions_dir, session_folder)
    os.makedirs(target_sessions_dir, exist_ok=True)

    # 1. Prepare Session Identity
    load_env()
    current_session_id = session_id or str(uuid.uuid4())
    
    # 2. Sync history to CLI if resuming
    if session_id:
        sync_session_to_cli(session_id)

    # 3. Create a temporary file for the text prompt to avoid Windows CLI length/newline limits
    import tempfile
    cli_dir = get_cli_chat_dir()
    os.makedirs(cli_dir, exist_ok=True)
    fd, temp_prompt_path = tempfile.mkstemp(suffix=".txt", prefix="tmp", dir=cli_dir)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(prompt)

    # 4. Construct Command
    cmd = ["gemini.cmd", "--yolo"]
    
    # Build the combined prompt with file attachments
    cli_prompt = f"@{temp_prompt_path}"
    if files:
        for f_path in files:
            if os.path.exists(f_path):
                cli_prompt += f" @{os.path.abspath(f_path)}"
                
    cmd.extend(["-p", cli_prompt])
    cmd.extend(["--model", model_id])
    
    # If resuming, use -r with the ID
    if session_id:
        cmd.extend(["-r", session_id])

    # 5. Execute with Retries
    retries = 0
    while True:
        try:
            logger.debug(f"Executing CLI: {' '.join(cmd[:5])}...")
            # Run without shell=True to avoid cmd.exe parsing issues, use gemini.cmd on Windows
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', check=False, env=os.environ)
            
            # Clean up the temp prompt file
            if os.path.exists(temp_prompt_path):
                try: os.remove(temp_prompt_path)
                except: pass

            if result.returncode != 0:
                err_payload = result.stderr.lower()
                # Handle rate limits
                if ("429" in err_payload or "quota" in err_payload or "503" in err_payload) and (max_retries == -1 or retries < max_retries):
                    retries += 1
                    wait_time = 10 * retries
                    logger.warning(f"CLI Rate limit. Retrying in {wait_time}s... (Attempt {retries})")
                    time.sleep(wait_time)
                    continue
                return None, None, f"CLI Error (code {result.returncode}): {result.stderr}"
            
            answer = result.stdout.strip()
            break
        except Exception as e:
            return None, None, f"Subprocess failed: {str(e)}"

    # 5. Capture the JSON session file generated by the CLI
    cli_dir = get_cli_chat_dir()
    
    # Search for the session file in the CLI dir
    # Try ID-based search first
    matches = glob.glob(os.path.join(cli_dir, f"*{current_session_id[:8]}*.json"))
    
    # If ID-based search fails, the CLI might have used a different naming convention.
    # We'll take the most recent JSON file in that directory as a fallback.
    if not matches:
        matches = glob.glob(os.path.join(cli_dir, "*.json"))
    
    if not matches:
        return answer, {"stats": {}}, f"Warning: CLI succeeded but no session file was found in {cli_dir}."
    
    latest_cli_json = sorted(matches, key=os.path.getmtime, reverse=True)[0]
    
    # 6. Determine local output path and archive
    if not session_name:
        timestamp_str = time.strftime("%Y-%m-%d_%H-%M-%S")
        safe_id = current_session_id[:8]
        if session_id:
            base_filename = f"{timestamp_str}_{model_id.replace('.', '_')}_resumed_{safe_id}"
        else:
            base_filename = f"{timestamp_str}_{model_id.replace('.', '_')}_{safe_id}"
        session_out_path = os.path.join(target_sessions_dir, f"{base_filename}.json")
    else:
        session_out_path = os.path.join(target_sessions_dir, session_name)

    # Copy CLI JSON to our local project structure
    shutil.copy2(latest_cli_json, session_out_path)
    
    # 7. Extract stats from the JSON for metadata
    stats = {}
    try:
        with open(session_out_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Find the last gemini message to get tokens
            for msg in reversed(data.get("messages", [])):
                if msg.get("type") == "gemini" and "tokens" in msg:
                    t = msg["tokens"]
                    stats = {
                        "models": {
                            model_id: {
                                "tokens": {
                                    "input": t.get("input", 0),
                                    "candidates": t.get("output", 0),
                                    "total": t.get("total", 0),
                                    "cached": t.get("cached", 0),
                                    "thoughts": t.get("thoughts", 0)
                                }
                            }
                        }
                    }
                    break
    except Exception as e:
        logger.warning(f"Failed to parse stats from session JSON: {e}")

    metadata = {
        "session_path": session_out_path,
        "session_id": current_session_id,
        "stats": stats
    }

    return answer, metadata, None

if __name__ == "__main__":
    from src.utils.config import setup_logging
    setup_logging()
    import argparse
    parser = argparse.ArgumentParser(description="Gemini CLI wrapper.")
    parser.add_argument("-m", "--model", default="gemini-1.5-flash")
    parser.add_argument("-p", "--prompt", required=True)
    parser.add_argument("-f", "--folder", default="test", help="Session folder.")
    parser.add_argument("--files", nargs="*", help="List of files to attach.")
    args = parser.parse_args()
    
    ans, meta, err = run_gemini(args.model, args.prompt, session_folder=args.folder, files=args.files)
    if err: print(f"Error: {err}")
    else: print(f"Response: {ans}\nStats: {meta['stats']}")
