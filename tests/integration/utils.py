import os
import shutil
from unittest.mock import patch
from src.create_document_traces import create_document_traces
from src.create_master_session import create_master_session

def run_sync_pipeline(test_workspace):
    """Helper to run the full sync pipeline with absolute paths."""
    # Note: PATHS are already patched via conftest.py
    test_config = test_workspace["config"].copy()
    
    with patch("src.utils.config.get_config", return_value=test_config):
        with patch("src.create_document_traces.get_config", return_value=test_config):
            with patch("src.create_master_session.get_config", return_value=test_config):
                # A. Tracing
                create_document_traces(
                    docs_dir=test_workspace["docs"],
                    max_tokens=test_config["trace_length"],
                    workers=1,
                    force_regeneration=True
                )
                
                # B. Master Session
                trace_dir = os.path.join(test_workspace["traces"], f"{test_config['trace_length']}_{test_config['doc_tracing_model']}")
                create_master_session(trace_dir=trace_dir, docs_dir=test_workspace["docs"])
