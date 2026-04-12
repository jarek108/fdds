"""
Centralized configuration manager for the FDDS project.
Handles project root discovery, config.json loading, path resolution, 
and global logging initialization.
"""

import os
import json
import logging

def get_project_root():
    """Returns the absolute path to the project root."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))

def get_config():
    """Loads configuration from config/config.json."""
    root = get_project_root()
    config_path = os.path.join(root, 'config', 'config.json')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")
        
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
        
    # Resolve relative paths to absolute
    paths = config['paths']
    for key in paths:
        if not os.path.isabs(paths[key]):
            paths[key] = os.path.abspath(os.path.join(root, paths[key]))
            
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
