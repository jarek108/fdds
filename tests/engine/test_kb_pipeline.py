import os
import json
import pytest
from unittest.mock import patch
from tests.integration.utils import run_sync_pipeline

@patch("src.create_master_session.run_gemini_cli_headless")
@patch("src.create_master_session.get_or_create_hash_file")
@patch("src.create_document_traces.create_document_traces")
def test_kb_compilation_integrity(mock_trace_run, mock_hash, mock_run, test_workspace):
    """
    ENGINE TEST: Verifies that the Python pipeline correctly compiles 
    PDF traces and corrections into the master knowledge base and session.
    Zero API calls.
    """
    # 1. Setup mock response for the Master Session initialization
    from gemini_cli_headless import GeminiSession
    mock_session_file = os.path.join(test_workspace["root"], "mock_session.json")
    with open(mock_session_file, "w") as f: json.dump({"sessionId": "mock-id"}, f)
    
    mock_run.return_value = GeminiSession(
        text="Mocked Session Initialization",
        session_id="mock-session-id",
        session_path=mock_session_file
    )

    # 2. Setup: Add a mock trace AND a matching empty PDF file
    pdf_path = os.path.join(test_workspace["docs"], "test.pdf")
    with open(pdf_path, "w") as f: f.write("empty")
    
    mock_hash.return_value = "abc123hash"

    trace_dir = os.path.join(test_workspace["traces"], "400_gemini-3-flash-preview")
    os.makedirs(trace_dir, exist_ok=True)
    
    mock_trace = {
        "source_file": "test.pdf",
        "zawartosc": "This is the document content.",
        "tytul": "Test Doc"
    }
    # Trace filename must match the mock_hash return value
    with open(os.path.join(trace_dir, "abc123hash.json"), "w", encoding="utf-8") as f:
        json.dump(mock_trace, f)

    # 3. Action: Run the pipeline
    run_sync_pipeline(test_workspace)

    # 4. Assert: Master Knowledge Base (Markdown)
    kb_path = test_workspace["paths"]["master_knowledge_base"]
    with open(kb_path, "r", encoding="utf-8") as f:
        kb_content = f.read()
    
    assert "This is the document content." in kb_content
    assert '<document id="doc_1">' in kb_content

    # 5. Assert: Master Session (JSON)
    assert mock_run.called
    _, kwargs = mock_run.call_args
    assert "This is the document content." in kwargs["system_instruction"]

