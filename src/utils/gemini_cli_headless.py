"""
Standalone programmatic wrapper for the Gemini CLI in headless mode.
"""

import subprocess
import os
import json
import shutil
import logging
import re
import glob
import time
import tempfile
import threading
import sys
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gemini_cli_headless")

DEFAULT_ALLOWED_TOOLS = ["read_file", "list_directory", "grep_search", "glob"]

@dataclass
class GeminiSession:
    text: str
    session_id: str
    session_path: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    raw_data: Optional[Dict[str, Any]] = None

def run_gemini_cli_headless(
    prompt: str,
    model_id: Optional[str] = None,
    files: Optional[List[str]] = None,
    session_to_resume: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    project_name: str = "fdds",
    max_retries: int = 3,
    retry_delay_seconds: float = 5.0,
    stream_output: bool = False,
    cwd: Optional[str] = None,
    api_key: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    allowed_paths: Optional[List[str]] = None
) -> GeminiSession:
    """
    Runs the Gemini CLI in headless mode and returns a GeminiSession object.
    """
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            return _execute_single_run(
                prompt=prompt,
                model_id=model_id,
                files=files,
                session_id_to_use=session_to_resume,
                extra_args=extra_args,
                project_name=project_name,
                stream_output=stream_output,
                cwd=cwd,
                api_key=api_key,
                allowed_tools=allowed_tools,
                allowed_paths=allowed_paths
            )
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(f"Gemini CLI failed (Attempt {attempt}/{max_retries}). Retrying in {retry_delay_seconds}s... Error: {e}")
                time.sleep(retry_delay_seconds)
            else:
                logger.error(f"Gemini CLI failed all {max_retries} attempts.")
                raise last_exception

def _execute_single_run(
    prompt: str,
    model_id: Optional[str] = None,
    files: Optional[List[str]] = None,
    session_id_to_use: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    project_name: str = "fdds",
    stream_output: bool = False,
    cwd: Optional[str] = None,
    api_key: Optional[str] = None,
    allowed_tools: Optional[Union[List[str], str]] = None,
    allowed_paths: Optional[Union[List[str], str]] = None
) -> GeminiSession:
    
    cli_dir = os.path.join(os.path.expanduser("~"), ".gemini", "tmp", project_name, "chats")
    os.makedirs(cli_dir, exist_ok=True)

    # --- Session Resolution & Sync ---
    if session_id_to_use:
        if session_id_to_use.lower().endswith('.json') or os.path.isfile(session_id_to_use):
            if not os.path.exists(session_id_to_use):
                raise FileNotFoundError(f"Session file not found: {session_id_to_use}")
            
            with open(session_id_to_use, 'r', encoding='utf-8') as f:
                data = json.load(f)
                extracted_id = data.get("sessionId")
            
            if not extracted_id:
                raise ValueError(f"File {session_id_to_use} is not a valid Gemini session")
                
            target_path = os.path.join(cli_dir, f"session-{extracted_id}.json")
            if not os.path.exists(target_path) or os.path.getmtime(session_id_to_use) > os.path.getmtime(target_path):
                shutil.copy2(session_id_to_use, target_path)
            
            session_id_to_use = extracted_id

    attachment_strings = []
    if files:
        for f_path in files:
            if os.path.exists(f_path):
                attachment_strings.append(f" @{os.path.abspath(f_path)}")

    cmd_executable = shutil.which("gemini")
    if not cmd_executable:
        raise EnvironmentError("The 'gemini' executable was not found in your PATH.")

    cmd = [cmd_executable, "--yolo", "-o", "json"]
    if model_id: cmd.extend(["-m", model_id])
    if session_id_to_use: 
        logger.debug(f"DEBUG: Passing -r {session_id_to_use}")
        cmd.extend(["-r", session_id_to_use])
    if extra_args: cmd.extend(extra_args)

    policy_path = None
    prompt_path = None
    
    try:
        temp_dir = os.path.join(os.path.expanduser("~"), ".gemini", "tmp", project_name, "run")
        os.makedirs(temp_dir, exist_ok=True)

        if allowed_tools is not None or allowed_paths is not None:
            tools_whitelist = allowed_tools if allowed_tools is not None else DEFAULT_ALLOWED_TOOLS
            paths_whitelist = allowed_paths if allowed_paths is not None else [cwd if cwd else os.getcwd()]
            
            if temp_dir not in paths_whitelist and "*" not in paths_whitelist:
                paths_whitelist.append(temp_dir)
            
            policy_lines = []
            if tools_whitelist != ["*"]:
                policy_lines.append("tools:")
                policy_lines.append("  - name: \"*\"")
                policy_lines.append("    action: deny")
                for tool in tools_whitelist:
                    policy_lines.append(f"  - name: \"{tool}\"")
                    policy_lines.append("    action: allow")
            
            if paths_whitelist != ["*"]:
                policy_lines.append("fileSystem:")
                policy_lines.append("  allowedPaths:")
                for p in paths_whitelist:
                    abs_p = os.path.abspath(p).replace('\\', '/')
                    policy_lines.append(f"    - \"{abs_p}\"")
            
            if policy_lines:
                with tempfile.NamedTemporaryFile(mode='w', suffix=".yaml", dir=temp_dir, delete=False, encoding='utf-8') as tf:
                    tf.write("\n".join(policy_lines))
                    policy_path = tf.name
                cmd.extend(["--policy", policy_path])

        with tempfile.NamedTemporaryFile(mode='w', suffix=".txt", dir=temp_dir, delete=False, encoding='utf-8') as tf:
            tf.write(prompt)
            for att in attachment_strings:
                tf.write(att)
            prompt_path = tf.name
        cmd.extend(["-p", f"@{prompt_path}"])

        env = os.environ.copy()
        env["TERM"] = "dumb"
        env["NO_COLOR"] = "1"
        if api_key:
            env["GEMINI_API_KEY"] = api_key

        logger.debug(f"Executing CLI command: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1
        )

        combined_output_list = []
        
        def read_output():
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                combined_output_list.append(line)
                if stream_output:
                    try:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    except UnicodeEncodeError:
                        pass 

        output_thread = threading.Thread(target=read_output)
        output_thread.start()

        while output_thread.is_alive():
            if not stream_output:
                sys.stdout.write(".")
                sys.stdout.flush()
            output_thread.join(timeout=30)
            
        process.wait()
        combined_output = "".join(combined_output_list)

        # Better JSON extraction
        # The CLI might output multiple JSON objects (e.g. error reports, cancellation messages)
        # We need to extract the LAST valid JSON object from the combined output.
        json_blocks = []
        decoder = json.JSONDecoder()
        
        idx = 0
        while idx < len(combined_output):
            # Find next potential JSON start
            next_start = combined_output.find('{', idx)
            if next_start == -1:
                break
                
            try:
                # Try decoding from this position
                obj, end_idx = decoder.raw_decode(combined_output[next_start:])
                
                # If successful, extract the exact string representation of the parsed block
                json_blocks.append(combined_output[next_start:next_start+end_idx])
                
                # Move index past this JSON object
                idx = next_start + end_idx
            except json.JSONDecodeError:
                # Not a valid JSON object, move forward one character and try again
                idx = next_start + 1
                
        if not json_blocks:
            raise RuntimeError(f"CLI did not return JSON. Output: {combined_output}")
            
        data = None
        for block in reversed(json_blocks):
            try:
                data = json.loads(block)
                # Ensure it's a dictionary (our expected structure) and not just a string/number
                if isinstance(data, dict):
                    break
                else:
                    data = None
            except json.JSONDecodeError:
                continue
                
        if not data:
            raise RuntimeError(f"Failed to parse any CLI JSON output blocks. Output: {combined_output}")
        
        text = data.get("text") or data.get("response") or ""
        raw_stats = data.get("stats") or data.get("trace", {}).get("stats", {})
        final_stats = raw_stats.copy()
        
        if "models" in raw_stats and isinstance(raw_stats["models"], dict):
            agg = {
                "inputTokens": 0, "outputTokens": 0, "cachedTokens": 0, "thoughtTokens": 0, "calls": 0
            }
            for model_stats in raw_stats["models"].values():
                t = model_stats.get("tokens")
                if isinstance(t, dict):
                    agg["inputTokens"] += t.get("input") or model_stats.get("inputTokens") or 0
                    agg["outputTokens"] += t.get("candidates") or model_stats.get("outputTokens") or 0
                    agg["cachedTokens"] += t.get("cached") or model_stats.get("cachedTokens") or 0
                    agg["thoughtTokens"] += t.get("thoughts") or model_stats.get("thoughtTokens") or 0
                else:
                    agg["inputTokens"] += model_stats.get("inputTokens") or 0
                    agg["outputTokens"] += model_stats.get("outputTokens") or 0
                    agg["cachedTokens"] += model_stats.get("cachedTokens") or 0
                    agg["thoughtTokens"] += model_stats.get("thoughtTokens") or 0
                agg["calls"] += 1
            for k, v in agg.items():
                if k not in final_stats: final_stats[k] = v
        
        return GeminiSession(
            text=text,
            session_id=data.get("session_id") or session_id_to_use,
            session_path=_find_session_file(cli_dir, data.get('session_id') or session_id_to_use or ""),
            stats=final_stats,
            raw_data=data
        )

    finally:
        pass
        # if policy_path and os.path.exists(policy_path):
        #     try: os.remove(policy_path)
        #     except: pass
        # if prompt_path and os.path.exists(prompt_path):
        #     try: os.remove(prompt_path)
        #     except: pass

def _find_session_file(directory: str, session_id: str) -> Optional[str]:
    if not session_id: return None
    
    # Try exact match first
    pattern_exact = os.path.join(directory, f"session-{session_id}.json")
    files_exact = glob.glob(pattern_exact)
    if files_exact: return files_exact[0]
    
    # Try the new timestamp-based format which uses first 8 chars of UUID
    short_id = session_id[:8]
    pattern_fuzzy = os.path.join(directory, f"session-*{short_id}*.json")
    files_fuzzy = glob.glob(pattern_fuzzy)
    return files_fuzzy[0] if files_fuzzy else None

if __name__ == "__main__":
    # Self-test
    try:
        session = run_gemini_cli_headless("Say 'Headless OK'", stream_output=True)
        print(f"\nResult: {session.text}")
    except Exception as e:
        print(f"Error: {e}")


