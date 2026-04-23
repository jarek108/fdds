import os
import sys

# Add project root to sys.path immediately to ensure 'src' package is found
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import time
from dotenv import load_dotenv

# Load environment variables from the correct path relative to this script
load_dotenv(os.path.join(project_root, 'config/.env'))

# --- FAIL FAST: API Key Check ---
if not os.environ.get("GEMINI_API_KEY"):
    print("FATAL: GEMINI_API_KEY environment variable is not set.")
    sys.exit(1)

from gemini_cli_headless import run_gemini_cli_headless
from src.utils.config import get_config, setup_logging, PATHS

from src.utils.hashes import get_or_create_hash_file
from src.utils.calc_stats import calculate_cost, parse_session_stats

logger = logging.getLogger("doc_tracing")

def process_single_document(pdf_path: str, trace_dir: str, model_id: str, max_tokens: int, force_regeneration: bool) -> Dict[str, Any]:
    """Extracts summary/trace from a single PDF and saves it as <hash>.json using Gemini CLI."""
    try:
        # 1. Get/Calculate Hash
        file_hash = get_or_create_hash_file(pdf_path)
        if not file_hash:
            return {"source": pdf_path, "status": "error", "message": "Could not calculate hash"}

        trace_path = os.path.join(trace_dir, f"{file_hash}.json")
        
        # 2. Check if trace already exists
        if os.path.exists(trace_path) and not force_regeneration:
            return {"source": pdf_path, "status": "skipped", "hash": file_hash}

        try:
            print(f"ANALYZING: {os.path.basename(pdf_path)}...", flush=True)
        except UnicodeEncodeError:
            pass
        
        system_instruction = "You are a specialized Knowledge Extraction Engine. Your task is to analyze the provided PDF and return a clean JSON summary in Polish. DO NOT include any conversational text or markdown blocks."
        
        prompt = f"""
Return a JSON object containing:
{{
  "tytul": "Exact title of the document",
  "tresc": "Detailed summary focusing on facts, numbers, and procedures (approx {max_tokens} tokens). 
           CRITICAL: You MUST include any phone numbers mentioned in the text (especially 800 100 100 or 116 111) as they are vital for intervention."
}}
"""
        
        # 3. Use gemini-cli-headless library directly
        session = run_gemini_cli_headless(
            prompt=prompt,
            model_id=model_id,
            files=[pdf_path],
            system_instruction_override=system_instruction,
            stream_output=False,
            allowed_tools=[],
            isolate_from_hierarchical_pollution=True
        )
        
        text = session.text.strip()
        
        # Clean up markdown if present
        if text.startswith("```json"): text = text[7:]
        if text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        text = text.strip()

        # Robust JSON extraction
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)

        # FIX FOR WINDOWS ENCODING CORRUPTION:
        # Sometimes the JSON contains mojibake or replacement characters like  
        # from the subprocess stdout buffer misinterpreting UTF-8 as CP1252.
        # We need to strictly parse it. If it fails, the error will be caught 
        # and logged correctly below.
        parsed_data = json.loads(text)
        title = parsed_data.get("tytul", "").strip()
        content = parsed_data.get("tresc", "").strip()
        
        if not title or not content:
            raise ValueError("Missing 'tytul' or 'tresc' in JSON.")

        # Success!
        s = parse_session_stats(session.stats, model_id)
        trace_data = {
            "source_hash": file_hash,
            "original_filename": os.path.basename(pdf_path),
            "tytul": title,
            "zawartosc": content,
            "stats": s,
            "cost": calculate_cost(model_id, s.get("input", 0), s.get("output", 0)),
            "model": model_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }

        with open(trace_path, 'w', encoding='utf-8') as f:
            json.dump(trace_data, f, indent=2, ensure_ascii=False)
            
        return {"source": pdf_path, "status": "success", "cost": trace_data["cost"], "hash": file_hash}

    except Exception as e:
        logger.error(f"Critical error processing {pdf_path}: {e}")
        return {"source": pdf_path, "status": "error", "message": str(e)}

def create_document_traces(docs_dir: str, max_docs: int = None, max_cost: float = None, max_tokens: int = None, force_regeneration: bool = False, workers: int = 5):
    """Orchestrates the parallel processing of PDF documents."""
    config = get_config()
    model_id = config["doc_tracing_model"]
    
    if max_tokens is None:
        max_tokens = config.get("trace_length", 200)
    
    trace_root = PATHS['traces_dir']
    trace_job_dir = os.path.normpath(os.path.join(trace_root, f"{max_tokens}_{model_id}"))
    os.makedirs(trace_job_dir, exist_ok=True)
    print(f"DEBUG: Writing traces to: {trace_job_dir}", flush=True)

    print(f"STEP 1/2: Scanning documents...", flush=True)

    # Collect all PDF files recursively
    pdf_files = []
    for root, _, files in os.walk(docs_dir):
        if '.hidden' in root: continue
        for file in files:
            if file.lower().endswith('.pdf') and not file.endswith('.hidden'):
                pdf_files.append(os.path.join(root, file))

    if max_docs:
        pdf_files = pdf_files[:max_docs]

    total_files = len(pdf_files)
    print(f"Found {total_files} PDF documents.", flush=True)
    
    total_cost = 0.0
    processed_count = 0
    skipped_count = 0
    error_count = 0
    
    print(f"Analyzing documents (workers: {workers})...", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_single_document, pdf, trace_job_dir, model_id, max_tokens, force_regeneration): pdf for pdf in pdf_files}
        
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            filename = os.path.basename(result["source"])
            
            if result["status"] == "success":
                processed_count += 1
                total_cost += result.get("cost", 0)
                try:
                    print(f"[{i}/{total_files}] DONE: {filename}", flush=True)
                except UnicodeEncodeError:
                    print(f"[{i}/{total_files}] DONE: {filename.encode('ascii', 'replace').decode('ascii')}", flush=True)
            elif result["status"] == "skipped":
                skipped_count += 1
                try:
                    print(f"[{i}/{total_files}] SKIP: {filename} (already traced)", flush=True)
                except UnicodeEncodeError:
                    print(f"[{i}/{total_files}] SKIP: {filename.encode('ascii', 'replace').decode('ascii')} (already traced)", flush=True)
                else:
                    error_count += 1
                    try:
                        print(f"[{i}/{total_files}] ERROR: {filename} - {result.get('message')}", flush=True)
                    except UnicodeEncodeError:
                        print(f"[{i}/{total_files}] ERROR: {filename.encode('ascii', 'replace').decode('ascii')} - {str(result.get('message')).encode('ascii', 'replace').decode('ascii')}", flush=True)
            
            if max_cost and total_cost >= max_cost:
                print(f"!!! Cost limit reached ({total_cost:.2f} USD). Stopping.", flush=True)
                break

    print(f"\n--- Tracing Summary ---", flush=True)
    print(f"Total: {total_files}", flush=True)
    print(f"Newly processed: {processed_count}", flush=True)
    print(f"Already existed: {skipped_count}", flush=True)
    print(f"Errors: {error_count}", flush=True)
    print(f"Total Cost: {total_cost:.4f} USD\n", flush=True)

if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Extract structured knowledge from PDFs using Gemini CLI.")
    parser.add_argument("--dir", default=PATHS['documents_dir'], help="Directory containing PDF documents.")
    parser.add_argument("--max-docs", type=int, help="Maximum number of documents to process.")
    parser.add_argument("--max-cost", type=float, help="Stop if total cost exceeds this USD amount.")
    parser.add_argument("--max-tokens", type=int, help="Target token count for each trace summary.")
    parser.add_argument("--force-regeneration", action="store_true", help="Reprocess documents even if trace exists.")
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel threads.")
    args = parser.parse_args()
    create_document_traces(args.dir, args.max_docs, args.max_cost, args.max_tokens, args.force_regeneration, args.workers)
