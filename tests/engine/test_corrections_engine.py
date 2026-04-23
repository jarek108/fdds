import os
import json
import pytest
from unittest.mock import patch
from tests.integration.utils import run_sync_pipeline

@patch("src.create_master_session.run_gemini_cli_headless")
@patch("tests.integration.utils.create_document_traces")
def test_correction_injection_engine(mock_trace, mock_run, test_workspace):
    """
    ENGINE TEST: Verifies that correction.txt is physically injected into the 
    system instruction sent to the LLM.
    """
    from gemini_cli_headless import GeminiSession
    mock_session_file = os.path.join(test_workspace["root"], "mock_session.json")
    with open(mock_session_file, "w") as f: json.dump({"sessionId": "mock-id"}, f)
    mock_run.return_value = GeminiSession(text="ok", session_id="id", session_path=mock_session_file)

    # 1. Action: Add a correction
    correction_path = test_workspace["paths"]["correction_file"]
    os.makedirs(os.path.dirname(correction_path), exist_ok=True)
    with open(correction_path, "w", encoding="utf-8") as f:
        f.write("HOTFIX: Use number 555-555.")

    # 2. Action: Run sync
    run_sync_pipeline(test_workspace)

    # 3. Assert: Verify the instruction sent to Gemini
    assert mock_run.called
    _, kwargs = mock_run.call_args
    instruction = kwargs["system_instruction_override"]
    assert "HOTFIX: Use number 555-555." in instruction
