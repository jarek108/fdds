"""
Standalone programmatic wrapper for the Gemini CLI in headless mode.
This module allows executing prompts, attaching files, and resuming sessions 
using the Gemini CLI, returning structured session data and statistics.

Usage Examples:
    # Use as a library
    from src.utils.gemini_cli_headless import run_gemini_cli_headless
    session = run_gemini_cli_headless("Hello world")
    print(session.text, session.stats)

    # Resume from a local file path
    session = run_gemini_cli_headless("Continue...", session_to_resume="data/sessions/user_1.json")
"""

import subprocess
import os
import json
import tempfile
import shutil
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger("gemini_cli_headless")

@dataclass
class GeminiSession:
    """
    Represents a completed Gemini CLI session interaction.
    """
    text: str
    session_id: str
    session_path: str
    stats: Dict[str, Any] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)

def _get_cli_chat_dir(project_name: str) -> str:
    """Returns the internal Gemini CLI chat directory for a given project."""
    return os.path.join(os.path.expanduser("~"), ".gemini", "tmp", project_name, "chats")

def run_gemini_cli_headless(
    prompt: str,
    model_id: Optional[str] = None,
    files: Optional[List[str]] = None,
    session_to_resume: Optional[str] = None,
    project_name: str = "fdds",
    extra_args: Optional[List[str]] = None
) -> GeminiSession:
    """
    Standalone wrapper for the Gemini CLI in headless mode.
    
    Args:
        prompt: The text prompt to send.
        model_id: Optional model name (e.g. 'gemini-1.5-pro').
        files: Optional list of file paths to attach.
        session_to_resume: Either a UUID string OR a path to a .json session file.
        project_name: The name used by CLI to scope the project (defaults to 'fdds').
        extra_args: Any additional flags to pass to the CLI.
        
    Returns:
        GeminiSession object containing response, ID, path, and stats.
    """
    
    session_id_to_use = None
    cli_dir = _get_cli_chat_dir(project_name)
    
    # 1. Resolve session_to_resume (UUID or File Path)
    if session_to_resume:
        # Check if it looks like a file path
        if session_to_resume.lower().endswith('.json') or os.path.isfile(session_to_resume):
            if not os.path.exists(session_to_resume):
                raise FileNotFoundError(f"Session file not found: {session_to_resume}")
                
            with open(session_to_resume, 'r', encoding='utf-8') as f:
                data = json.load(f)
                session_id_to_use = data.get("sessionId")
            
            if not session_id_to_use:
                raise ValueError(f"File {session_to_resume} is not a valid Gemini session (missing sessionId)")
            
            # Sync to CLI internal dir
            os.makedirs(cli_dir, exist_ok=True)
            target_path = os.path.join(cli_dir, f"session-{session_id_to_use}.json")
            # Copy only if different or newer
            if not os.path.exists(target_path) or os.path.getmtime(session_to_resume) > os.path.getmtime(target_path):
                shutil.copy2(session_to_resume, target_path)
        else:
            # Assume it's a UUID or 'latest'
            session_id_to_use = session_to_resume

    # 2. Create temporary file for prompt to avoid CLI length limits
    temp_prompt_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix=".txt", delete=False, encoding='utf-8') as tf:
            tf.write(prompt)
            temp_prompt_path = tf.name

        # 3. Construct Command
        cmd_executable = "gemini.cmd" if os.name == 'nt' else "gemini"
        cmd = [cmd_executable, "--yolo", "--output-format", "json"]
        
        if model_id: cmd.extend(["--model", model_id])
        if session_id_to_use: cmd.extend(["--resume", session_id_to_use])
        if extra_args: cmd.extend(extra_args)

        # Build prompt with file attachments
        cli_prompt = f"@{temp_prompt_path}"
        if files:
            for f_path in files:
                if os.path.exists(f_path):
                    cli_prompt += f" @{os.path.abspath(f_path)}"
        
        cmd.extend(["--prompt", cli_prompt])

        # 4. Execute
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', check=False)

        # 5. Parse Output
        if not result.stdout.strip():
            raise RuntimeError(f"CLI returned empty output. Stderr: {result.stderr}")

        output = result.stdout.strip()
        # Handle cases where CLI might print some non-json text before the JSON block
        if not output.startswith('{'):
            start_idx = output.find('{')
            if start_idx != -1: output = output[start_idx:]
            else: raise RuntimeError(f"CLI output did not contain JSON: {output}")
        
        response_data = json.loads(output)
        
        if "error" in response_data and response_data["error"]:
            err = response_data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Gemini Error: {msg}")

        # 6. Build Result Object
        final_session_id = response_data.get("session_id") or session_id_to_use
        final_session_path = os.path.join(cli_dir, f"session-{final_session_id}.json")
        
        # Extract stats from trace if available
        trace = response_data.get("trace", {})
        stats = trace.get("stats", {})
        
        return GeminiSession(
            text=response_data.get("text", ""),
            session_id=final_session_id,
            session_path=final_session_path,
            stats=stats,
            raw_data=response_data
        )

    finally:
        if temp_prompt_path and os.path.exists(temp_prompt_path):
            try: os.remove(temp_prompt_path)
            except: pass

if __name__ == "__main__":
    # Example standalone usage
    try:
        session = run_gemini_cli_headless("Say hello!")
        print(f"AI: {session.text}")
        print(f"ID: {session.session_id}")
        print(f"Stats: {session.stats}")
    except Exception as e:
        print(f"Error: {e}")
