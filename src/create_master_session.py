import os
import sys

# Add project root to sys.path immediately to ensure 'src' package is found
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import logging
import argparse
import urllib.parse
import shutil
import time
import hashlib
import tempfile
import uuid
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(project_root, 'config/.env'))

# --- FAIL FAST: API Key Check ---
if not os.environ.get("GEMINI_API_KEY"):
    print("FATAL: GEMINI_API_KEY environment variable is not set.")
    sys.exit(1)

from gemini_cli_headless import run_gemini_cli_headless
from src.utils.config import get_config, setup_logging, PATHS
from src.utils.hashes import get_or_create_hash_file
from src.utils.calc_stats import parse_session_stats

logger = logging.getLogger("master_session")

def create_master_session(trace_dir: str = None, docs_dir: str = None):
    """Compiles individual JSON traces into a unified KB and creates a cached session."""
    print(f"STEP 2/2: Building Knowledge Base and Session...", flush=True)
    
    config = get_config()
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
    
    if trace_dir is None:
        trace_root = PATHS['traces_dir']
        trace_dir = os.path.join(trace_root, f"{config['trace_length']}_{config['doc_tracing_model']}")
    
    if docs_dir is None:
        docs_root = PATHS['documents_dir']
    else:
        docs_root = docs_dir
    base_url_prefix = config.get('base_url_prefix', '/documents/')
    
    print(f"Source folder: {docs_root}", flush=True)
    print(f"Traces folder: {trace_dir}", flush=True)

    all_docs = []
    
    # 1. Scan documents recursively
    for root, _, files in os.walk(docs_root):
        if '.hidden' in root: continue
        
        for file in files:
            if file.lower().endswith('.pdf') and not file.endswith('.hidden'):
                pdf_path = os.path.join(root, file)
                rel_pdf_path = os.path.relpath(pdf_path, docs_root)
                
                # 2. Get hash for the document
                file_hash = get_or_create_hash_file(pdf_path)
                if not file_hash: continue
                
                # 3. Look for trace by hash
                trace_path = os.path.join(trace_dir, f"{file_hash}.json")
                if os.path.exists(trace_path):
                    try:
                        with open(trace_path, 'r', encoding='utf-8') as f:
                            trace_data = json.load(f)
                            # Store with current relative path for URL generation
                            trace_data["current_rel_path"] = rel_pdf_path
                            all_docs.append(trace_data)
                    except Exception as e:
                        print(f"ERROR reading trace {trace_path}: {e}", flush=True)
                else:
                    print(f"WARNING: No trace found for: {rel_pdf_path}", flush=True)

    # Build human and LLM versions of KB
    human_kb_parts = [
        "# Baza Wiedzy FDDS\n\n",
        f"**Katalog źródłowy:** {os.path.relpath(trace_dir, project_root)}\n",
        f"**Data utworzenia:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n",
        "Ten dokument zawiera skondensowaną wiedzę z materiałów Fundacji Dajemy Dzieciom Siłę.\n\n"
    ]

    base_instruction_path = PATHS['base_instruction_file']
    if os.path.exists(base_instruction_path):
        with open(base_instruction_path, 'r', encoding='utf-8') as f:
            llm_kb_parts = [f.read().strip() + "\n\n", "# Baza Wiedzy FDDS\n\n", "Poniżej znajdują się dokumenty źródłowe, każdy oznaczony jako <document id=\"doc_N\">. Używaj tych identyfikatorów do linkowania.\n\n"]
    else:
        logger.warning(f"Base instruction file not found at {base_instruction_path}. Using fallback persona.")
        llm_kb_parts = [
            "# INSTRUKCJA SYSTEMOWA\n",
            "Jesteś asystentką Bazy Wiedzy Fundacji Dajemy Dzieciom Siłę (FDDS).\n\n",
            "# Baza Wiedzy FDDS\n\n"
        ]

    # Read live corrections first
    correction_path = PATHS['correction_file']
    
    correction_header = "\n\n# Bieżące Poprawki (Aktualizacje na żywo)\n\nPoniższe informacje to najnowsze poprawki, które mają najwyższy priorytet i nadpisują ewentualne sprzeczne informacje z pozostałych dokumentów:\n\n"
    has_corrections = False
    if os.path.exists(correction_path):
        try:
            with open(correction_path, 'r', encoding='utf-8') as f:
                correction_content = f.read().strip()
            if correction_content:
                print("Including live corrections...", flush=True)
                human_kb_parts.append(correction_header + correction_content + "\n\n---\n\n")
                llm_kb_parts.append(correction_header + correction_content + "\n\n---\n\n")
                has_corrections = True
        except Exception as e:
            print(f"Failed to read corrections: {e}", flush=True)

    if not all_docs:
        print("WARNING: No documents with valid traces found. Creating empty KB.", flush=True)
        llm_kb_parts.append("\n\n(Baza wiedzy jest obecnie pusta. Nie masz żadnych dokumentów źródłowych.)\n")
    else:
        print(f"Compiling {len(all_docs)} documents into Markdown...", flush=True)
        for i, doc in enumerate(all_docs, 1):
            doc_id = f"doc_{i}"
            url = base_url_prefix + urllib.parse.quote(doc["current_rel_path"].replace('\\', '/'))
            
            # Use the title generated by the LLM during the tracing phase
            fallback_title = os.path.splitext(doc.get("original_filename", "Dokument"))[0].replace('_', ' ').replace('-', ' ')
            raw_title = doc.get("tytul", fallback_title)

            # Post-process title to fix ALL CAPS issues
            alpha_chars = [c for c in raw_title if c.isalpha()]
            if alpha_chars and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > 0.4:
                title = raw_title.capitalize()
            else:
                title = raw_title

            # Human version
            human_kb_parts.append(f"<document id=\"{doc_id}\">\n")
            human_kb_parts.append(f"  <url>{url}</url>\n")
            human_kb_parts.append(f"  <tytul>{title}</tytul>\n")
            human_kb_parts.append(f"  <tresc>\n{doc['zawartosc']}\n  </tresc>\n")
            human_kb_parts.append(f"</document>\n\n")

            # LLM version
            llm_kb_parts.append(f"<document id=\"{doc_id}\">\n")
            llm_kb_parts.append(f"  <tytul>{title}</tytul>\n")
            llm_kb_parts.append(f"  <tresc>\n{doc['zawartosc']}\n  </tresc>\n")
            llm_kb_parts.append(f"</document>\n\n")

    # Save Markdown versions
    kb_output_path = PATHS['master_knowledge_base']
    instruction_output_path = PATHS['master_system_instruction']
    
    os.makedirs(os.path.dirname(kb_output_path), exist_ok=True)
    with open(kb_output_path, 'w', encoding='utf-8') as f:
        f.writelines(human_kb_parts)
    
    system_md_content = "".join(llm_kb_parts)
    with open(instruction_output_path, 'w', encoding='utf-8') as f:
        f.write(system_md_content)
        
    print(f"Knowledge Base saved: {kb_output_path}", flush=True)
    print(f"System Instruction saved: {instruction_output_path}", flush=True)

    # Create Master Session for LLM
    print(f"Creating Master Session for {config['answer_model']} (this may take 10-30s)...", flush=True)
    
    policy_path = os.path.join(PATHS['run_dir'], "restrictive_policy.toml")
    os.makedirs(os.path.dirname(policy_path), exist_ok=True)
    if not os.path.exists(policy_path):
        with open(policy_path, 'w', encoding='utf-8') as f:
            f.write('[[rule]]\ntoolName = "*"\ndecision = "deny"\npriority = 100\ndenyMessage = "NO TOOLS"\n')

    session = run_gemini_cli_headless(
        prompt="OK",
        model_id=config["answer_model"],
        system_instruction_override="".join(llm_kb_parts),
        allowed_tools=[],
        stream_output=False,
        isolate_from_hierarchical_pollution=True,
        extra_args=["--admin-policy", policy_path]
    )
    
    master_session_path = PATHS['master_session_file']
    os.makedirs(os.path.dirname(master_session_path), exist_ok=True)
    shutil.copy2(session.session_path, master_session_path)
    
    # Stats
    s = parse_session_stats(session.stats, config["answer_model"])
    
    # Ensure consistent path separators for fingerprinting (replace \ with /)
    fingerprint_list = sorted([f"{d['current_rel_path'].replace(os.sep, '/')}:{d.get('source_hash','')}" for d in all_docs])
    
    kb_stats = {
        "token_count": s.get("input", 0) + s.get("cached", 0),
        "doc_count": len(all_docs),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": config["answer_model"],
        "trace_dir": os.path.relpath(trace_dir, project_root).replace(os.sep, '/'),
        "fingerprint_hash": hashlib.sha256(json.dumps(fingerprint_list).encode('utf-8')).hexdigest()
    }
    
    stats_path = PATHS['kb_stats']
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(kb_stats, f, indent=2)
    
    print(f"Sync complete! KB Size: {kb_stats['token_count']} tokens.", flush=True)
    print(f"Session cached: {master_session_path}", flush=True)

if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Compile KB and create Master Session.")
    parser.add_argument("dir", nargs='?', help="Trace directory.")
    args = parser.parse_args()
    create_master_session(args.dir)
