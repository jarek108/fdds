"""
Centralized configuration manager for the FDDS project.
Handles project root discovery, config.json loading, and system path constants.
"""

import os
import json
import logging

def get_project_root():
    """Returns the absolute path to the project root."""
    # We are in src/utils/config.py, root is ../../
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))

ROOT = get_project_root()

# System path constants - these are architectural and NOT user-configurable.
PATHS = {
    # Sources (Persistent Truth)
    "sources_dir": os.path.join(ROOT, "data/sources"),
    "documents_dir": os.path.join(ROOT, "data/sources/documents"),
    "moodle_map_file": os.path.join(ROOT, "data/sources/moodle_map.json"),
    "correction_file": os.path.join(ROOT, "data/sources/correction.txt"),
    
    # Active Setup (The live "Brain" used by the server)
    "active_setup_dir": os.path.join(ROOT, "data/active_setup"),
    "master_session_file": os.path.join(ROOT, "data/active_setup/master_session.json"),
    "master_knowledge_base": os.path.join(ROOT, "data/active_setup/master_knowledge_base.md"),
    "kb_stats": os.path.join(ROOT, "data/active_setup/kb_stats.json"),
    
    # Cache (Safe to delete, improves performance)
    "cache_dir": os.path.join(ROOT, "data/cache"),
    "traces_dir": os.path.join(ROOT, "data/cache/traces"),
    "html_cache_dir": os.path.join(ROOT, "data/cache/html_cache"),
    "pdf_cache_template": os.path.join(ROOT, "data/cache/pdf_cache_template.json"),
    
    # Temp (Transient runtime state)
    "temp_dir": os.path.join(ROOT, "data/temp"),
    "sessions_dir": os.path.join(ROOT, "data/temp/sessions"),
    "server_logs_dir": os.path.join(ROOT, "data/temp/server_logs"),
    "user_audio_dir": os.path.join(ROOT, "data/temp/user_audio"),
    "run_dir": os.path.join(ROOT, "data/temp/run")
}

def get_config():
    """Loads functional configuration from config/config.json."""
    config_path = os.path.join(ROOT, 'config', 'config.json')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")
        
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
        
    # Paths are now handled by the PATHS constant above.
    # We remove the legacy paths section if it exists in the JSON.
    if 'paths' in config:
        del config['paths']
            
    return config

def setup_logging(level=logging.INFO):
    """Initializes project-wide logging."""
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    # Suppress verbose logs from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
