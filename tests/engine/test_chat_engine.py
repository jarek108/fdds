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
    # 1. Setup: Create a fake master knowledge base
    persona_content = "# FAKE SYSTEM INSTRUCTION\nThis is the FDDS persona."
    
    # Setup mock master system instruction file
    instruction_path = test_workspace["paths"]["master_system_instruction"]
    os.makedirs(os.path.dirname(instruction_path), exist_ok=True)
    with open(instruction_path, "w", encoding="utf-8") as f:
        f.write(persona_content)

    # Setup mock master session file
    master_session_path = test_workspace["paths"]["master_session_file"]
    os.makedirs(os.path.dirname(master_session_path), exist_ok=True)
    with open(master_session_path, "w", encoding="utf-8") as f:
        json.dump({
            "sessionId": "master-id"
        }, f)

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
    data = response.json()
    assert "answer" in data
    assert "stats" in data
    stats = data["stats"]
    assert "input" in stats
    assert "output" in stats
    assert "cached" in stats
    assert "thoughts" in stats
    assert "cost" in stats
    
    assert mock_run.called
    _, kwargs = mock_run.call_args
    
    # CRITICAL: Verify the persona is being injected from the .md file
    assert kwargs["system_instruction_override"] == persona_content
    assert kwargs["allowed_tools"] == []
    assert kwargs["isolate_from_hierarchical_pollution"] is True
