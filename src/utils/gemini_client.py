
import os
import logging
from gemini_cli_headless import run_gemini_cli_headless as _run_original, GeminiSession

logger = logging.getLogger("fdds.gemini")

def run_gemini_cli_headless(
    prompt: str,
    model_id: str = None,
    files: list = None,
    session_to_resume: str = None,
    system_instruction: str = None,
    allowed_paths: list = None,
    allowed_tools: list = None,
    stream_output: bool = False, # Default to False for stability
    **kwargs
) -> GeminiSession:
    """
    FDDS Wrapper for Gemini CLI Headless.
    Ensures consistent settings across the application and uses Tier-4 Isolation.
    """
    api_key = kwargs.pop("api_key", os.environ.get("GEMINI_API_KEY"))
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set.")

    # MANDATORY FDDS SECURITY POLICY (Tier-4 Sandbox)
    # 1. We disable tools by default for all answering/summarization tasks
    # 2. we enforce hierarchical isolation to prevent context leakage
    # 3. We use project_name='fdds' to ensure consistent session directory naming
    
    # We ignore allowed_paths because of the upstream static compiler bug
    # documented in gemini-cli-headless.
    
    return _run_original(
        prompt=prompt,
        model_id=model_id,
        files=files,
        session_to_resume=session_to_resume,
        system_instruction_override=system_instruction,
        allowed_paths=None, 
        allowed_tools=allowed_tools if allowed_tools is not None else [],
        stream_output=stream_output,
        api_key=api_key,
        project_name="fdds",
        isolate_from_hierarchical_pollution=True,
        **kwargs
    )
