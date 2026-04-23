import pytest
import os
import shutil
import tempfile
import json
import time
from unittest.mock import patch

@pytest.fixture(scope="session", autouse=True)
def set_utf8_encoding():
    """Ensures that the test environment uses UTF-8 encoding on Windows."""
    os.environ["PYTHONIOENCODING"] = "utf-8"
    yield

@pytest.fixture
def test_workspace():
    """Creates a temporary isolated workspace for FDDS tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Create directory structure
        docs_dir = os.path.join(tmp_dir, "data/sources/documents")
        traces_dir = os.path.join(tmp_dir, "data/cache/traces")
        sessions_dir = os.path.join(tmp_dir, "data/temp/sessions")
        os.makedirs(docs_dir, exist_ok=True)
        os.makedirs(traces_dir, exist_ok=True)
        os.makedirs(sessions_dir, exist_ok=True)
        
        # 2. Create a minimal mock config
        config = {
            "answer_model": "gemini-3-flash-preview",
            "doc_tracing_model": "gemini-3-flash-preview",
            "trace_length": 400,
            "base_url_prefix": "/documents/"
        }
        
        # 3. Define mock paths
        mock_paths = {
            "sources_dir": os.path.join(tmp_dir, "data/sources"),
            "documents_dir": docs_dir,
            "moodle_map_file": os.path.join(tmp_dir, "data/sources/moodle_map.json"),
            "correction_file": os.path.join(tmp_dir, "data/sources/correction.txt"),
            "base_instruction_file": os.path.join(tmp_dir, "config/system_instruction.md"),
            "active_setup_dir": os.path.join(tmp_dir, "data/active_setup"),
            "master_session_file": os.path.join(tmp_dir, "data/active_setup/master_session.json"),
            "master_knowledge_base": os.path.join(tmp_dir, "data/active_setup/master_knowledge_base.md"),
            "master_system_instruction": os.path.join(tmp_dir, "data/active_setup/master_system_instruction.md"),
            "kb_stats": os.path.join(tmp_dir, "data/active_setup/kb_stats.json"),
            "cache_dir": os.path.join(tmp_dir, "data/cache"),
            "traces_dir": traces_dir,
            "html_cache_dir": os.path.join(tmp_dir, "data/cache/html_cache"),
            "pdf_cache_template": os.path.join(tmp_dir, "data/cache/pdf_cache_template.json"),
            "temp_dir": os.path.join(tmp_dir, "data/temp"),
            "sessions_dir": sessions_dir,
            "server_logs_dir": os.path.join(tmp_dir, "data/temp/server_logs"),
            "user_audio_dir": os.path.join(tmp_dir, "data/temp/user_audio"),
            "run_dir": os.path.join(tmp_dir, "data/temp/run")
        }
        
        # 4. Patch get_config and PATHS constant during the test
        with patch("src.utils.config.get_config", return_value=config):
            with patch("src.utils.config.PATHS", mock_paths):
                # We must also patch create_master_session and others if they import PATHS
                with patch("src.create_master_session.PATHS", mock_paths):
                    with patch("src.create_document_traces.PATHS", mock_paths):
                        with patch("src.api.chat.PATHS", mock_paths):
                            with patch("src.api.admin.PATHS", mock_paths):
                                with patch("src.api.config.PATHS", mock_paths):
                                    with patch("src.services.storage.PATHS", mock_paths):
                                        yield {
                                            "root": tmp_dir,
                                            "docs": docs_dir,
                                            "traces": traces_dir,
                                            "sessions": sessions_dir,
                                            "config": config,
                                            "paths": mock_paths
                                        }

@pytest.fixture
def mock_env():
    """Ensures API keys are available from the OS environment for the tests."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        pytest.fail("GEMINI_API_KEY environment variable not set. Tests cannot run.")
    return key

@pytest.fixture(autouse=True)
def slow_down_tests():
    """Adds a small delay between tests to avoid hitting quota too fast."""
    yield
    time.sleep(2)
