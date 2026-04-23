import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.main import app
from src.utils.config import PATHS

client = TestClient(app)

@patch("src.api.chat.run_gemini_cli_headless")
@patch("src.api.chat.shutil.copy2")
def test_ask_question_injects_persona(mock_copy, mock_run, test_workspace):
    """
    ENGINE TEST: Verifies that the /ask endpoint correctly reads the master system instruction
    and injects it as a system instruction override.
    """
    # 1. Setup: Create a fake master system instruction
    kb_content = "# FAKE SYSTEM INSTRUCTION\nThis is the FDDS persona."
    kb_path = test_workspace["paths"]["master_system_instruction"]
    os.makedirs(os.path.dirname(kb_path), exist_ok=True)
    with open(kb_path, "w", encoding="utf-8") as f:
        f.write(kb_content)
    
    # Setup mock master session file
    master_session_path = test_workspace["paths"]["master_session_file"]
    os.makedirs(os.path.dirname(master_session_path), exist_ok=True)
    with open(master_session_path, "w", encoding="utf-8") as f:
        json.dump({"sessionId": "master-id"}, f)

    # 2. Setup mock response
    from gemini_cli_headless import GeminiSession
    mock_run.return_value = GeminiSession(
        text="I am the FDDS assistant.",
        session_id="new-user-session",
        session_path="/tmp/session.json"
    )

    # 3. Action: Call the API
    response = client.post("/ask", json={
        "question": "Hello?",
        "chatId": "user-123"
    })

    # 4. Assert
    assert response.status_code == 200
    assert mock_run.called
    _, kwargs = mock_run.call_args
    
    # CRITICAL: Verify the persona is being injected
    assert kwargs["system_instruction_override"] == kb_content
    assert kwargs["allowed_tools"] == []
    assert kwargs["isolate_from_hierarchical_pollution"] is True
