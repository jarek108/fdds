import os
import json
import logging
import threading
import re
from typing import Dict, Any
from src.utils.config import PATHS

logger = logging.getLogger("storage")

class StorageManager:
    def __init__(self):
        self.chat_mapping: Dict[str, str] = {}
        self.chat_mapping_lock = threading.Lock()
        self.doc_index: Dict[str, Dict[str, str]] = {}
        self.doc_index_lock = threading.Lock()
        
        self.mapping_file = os.path.join(PATHS['sessions_dir'], 'chat_sessions.json')
        self.load_chat_mapping()
        self.load_doc_index()

    def load_chat_mapping(self):
        with self.chat_mapping_lock:
            if os.path.exists(self.mapping_file):
                try:
                    with open(self.mapping_file, 'r', encoding='utf-8') as f:
                        self.chat_mapping.update(json.load(f))
                except Exception as e:
                    logger.error(f"Failed to load session mapping: {e}")

    def save_chat_mapping(self):
        with self.chat_mapping_lock:
            try:
                os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
                with open(self.mapping_file, 'w', encoding='utf-8') as f:
                    json.dump(self.chat_mapping, f)
            except Exception as e:
                logger.error(f"Failed to save session mapping: {e}")

    def load_doc_index(self):
        kb_path = PATHS['master_knowledge_base']
        if not os.path.exists(kb_path):
            logger.warning(f"Master knowledge base not found at {kb_path}. Links will not be translated.")
            return

        new_index = {}
        try:
            with open(kb_path, 'r', encoding='utf-8') as f:
                content = f.read()
                blocks = re.split(r'<document id="', content)[1:]
                for block in blocks:
                    id_match = re.match(r'(doc_\d+)">', block)
                    if id_match:
                        doc_id = id_match.group(1)
                        url_match = re.search(r'<url>(.*?)</url>', block, flags=re.DOTALL)
                        title_match = re.search(r'<tytul>(.*?)</tytul>', block, flags=re.DOTALL)
                        
                        if url_match and title_match:
                            new_index[doc_id] = {
                                "url": url_match.group(1).strip(),
                                "tytul": title_match.group(1).strip()
                            }
            
            with self.doc_index_lock:
                self.doc_index = new_index
            logger.info(f"Loaded {len(self.doc_index)} document references from master KB.")
        except Exception as e:
            logger.error(f"Failed to parse master KB index: {e}")

    def translate_doc_links(self, text: str) -> str:
        with self.doc_index_lock:
            if not self.doc_index:
                return text

            def replacer(m):
                doc_id = m.group(1)
                doc_info = self.doc_index.get(doc_id)
                if doc_info:
                    return f"[{doc_info['tytul']}]({doc_info['url']})"
                return m.group(0)

            text = re.sub(r'\[(?:\s*doc_\d+\s*,?\s*)+\]', lambda m: m.group(0)[1:-1], text)
            text = re.sub(r'(?<!\]\()\b(doc_\d+)\b', replacer, text)
            return text

# Singleton instance
storage = StorageManager()
