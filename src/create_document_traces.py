import os
import json
import logging
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import time

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from gemini_cli_headless import run_gemini_cli_headless
from src.utils.config import get_config, setup_logging
from src.utils.hashes import get_or_create_hash_file
from src.utils.calc_stats import calculate_cost

logger = logging.getLogger("doc_tracing")

def process_single_document(pdf_path: str, trace_dir: str, model_id: str, max_tokens: int, force_regeneration: bool) -> Dict[str, Any]:
    """Extracts summary/trace from a single PDF and saves it as <hash>.json using strict JSON output."""
    try:
        # 1. Get/Calculate Hash
        file_hash = get_or_create_hash_file(pdf_path)
        if not file_hash:
            return {"source": pdf_path, "status": "error", "message": "Could not calculate hash"}

        trace_path = os.path.join(trace_dir, f"{file_hash}.json")
        
        # 2. Check if trace already exists
        if os.path.exists(trace_path) and not force_regeneration:
            return {"source": pdf_path, "status": "skipped", "hash": file_hash}

        print(f"ANALYZING: {os.path.basename(pdf_path)}...", flush=True)
        
        prompt = f"""
Przeanalizuj dołączony dokument PDF i przygotuj jego 'ślad' (trace) dla bazy wiedzy.
Twoim celem jest wyciągnięcie esencji wiedzy w formie skondensowanej, ale bardzo konkretnej.

WYMAGANIA MERYTORYCZNE:
1. JĘZYK: Odpowiadaj wyłącznie w języku polskim.
2. TREŚĆ: Skup się na faktach, liczbach, wytycznych, procedurach i kluczowych przesłaniach. Jeśli dokument wspomina o innych programach FDDS, numerach telefonów (116 111, 800 100 100) lub stronach www, koniecznie je uwzględnij.
3. LIMIT: Twoja odpowiedź powinna mieć około {max_tokens} tokenów (bądź zwięzły, ale merytoryczny).

WYMAGANIA FORMATOWANIA (KRYTYCZNE):
Musisz odpowiedzieć WYŁĄCZNIE poprawnym obiektem JSON. Nie używaj znaczników formatowania Markdown (takich jak ```json). Nie dodawaj absolutnie żadnych wstępów, podsumowań ani komentarzy przed lub po obiekcie JSON.

Zwróć dokładnie taką strukturę:
{{
  "tytul": "Tutaj wpisz DOKŁADNY, oficjalny tytuł dokumentu. Absolutny zakaz dodawania własnych słów czy komentarzy. WAŻNE: Tytuł nie może być w całości pisany WIELKIMI LITERAMI (używaj standardowej pisowni, np. tylko pierwsza litera wielka).",
  "tresc": "Tutaj wpisz treść merytoryczną sformatowaną za pomocą znaków nowej linii (\\n) i podstawowych wypunktowań."
}}
"""
        
        max_retries = 3
        cost = 0.0
        s = {}
        
        for attempt in range(max_retries):
            session = run_gemini_cli_headless(
                prompt=prompt,
                model_id=model_id,
                files=[pdf_path]
            )
            
            # Accumulate stats across retries
            s_current = session.stats
            cost += calculate_cost(
                model_id, 
                s_current.get("inputTokens", 0), 
                s_current.get("outputTokens", 0) + s_current.get("thoughtTokens", 0), 
                s_current.get("cachedTokens", 0)
            )
            
            # Update cumulative stats
            for k, v in s_current.items():
                if isinstance(v, (int, float)):
                    s[k] = s.get(k, 0) + v
            
            text = session.text.strip()
            
            # Clean up potential markdown formatting that models sometimes stubbornly include
            if text.startswith('```json'):
                text = text[7:]
            elif text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()
            
            try:
                parsed_data = json.loads(text)
                title = parsed_data.get("tytul", "").strip()
                content = parsed_data.get("tresc", "").strip()
                
                # Validation
                if not title or not content:
                    raise ValueError("Missing 'tytul' or 'tresc' in JSON.")
                
                if len(title) > 200 or "Poniżej przedstawiam" in title or "Zgodnie z" in title:
                    raise ValueError(f"Title seems polluted with conversational noise (length: {len(title)}).")
                
                # If we get here, the JSON is valid and clean
                trace_data = {
                    "source_hash": file_hash,
                    "original_filename": os.path.basename(pdf_path),
                    "tytul": title,
                    "zawartosc": content,
                    "stats": s,
                    "cost": cost,
                    "model": model_id,
                    "timestamp": session.raw_data.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ"))
                }

                with open(trace_path, 'w', encoding='utf-8') as f:
                    json.dump(trace_data, f, indent=2, ensure_ascii=False)
                    
                return {"source": pdf_path, "status": "success", "cost": cost, "hash": file_hash}
                
            except (json.JSONDecodeError, ValueError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Retry {attempt + 1}/{max_retries} for {os.path.basename(pdf_path)} due to: {e}")
                    # Modify prompt slightly to strongly enforce the rule on retry
                    prompt += "\nOSTATNIA ODPOWIEDŹ BYŁA BŁĘDNA. MUSISZ ZWRÓCIĆ TYLKO I WYŁĄCZNIE CZYSTY JSON. ŻADNEGO TEKSTU POZA KLAMRAMI { }."
                else:
                    logger.error(f"Failed to process {pdf_path} after {max_retries} attempts. Last error: {e}")
                    return {"source": pdf_path, "status": "error", "message": f"Validation failed: {str(e)}"}
                    
    except Exception as e:
        logger.error(f"Critical error processing {pdf_path}: {e}")
        return {"source": pdf_path, "status": "error", "message": str(e)}

def create_document_traces(docs_dir: str, max_docs: int = None, max_cost: float = None, max_tokens: int = None, force_regeneration: bool = False, workers: int = 5):
    """Orchestrates the parallel processing of PDF documents."""
    config = get_config()
    model_id = config["doc_tracing_model"]
    
    if max_tokens is None:
        max_tokens = config.get("trace_length", 200)
    
    trace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../', config['paths']['traces_dir']))
    trace_job_dir = os.path.join(trace_root, f"{max_tokens}_{model_id}")
    os.makedirs(trace_job_dir, exist_ok=True)

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
                print(f"[{i}/{total_files}] DONE: {filename}", flush=True)
            elif result["status"] == "skipped":
                skipped_count += 1
                print(f"[{i}/{total_files}] SKIP: {filename} (already traced)", flush=True)
            else:
                error_count += 1
                print(f"[{i}/{total_files}] ERROR: {filename} - {result.get('message')}", flush=True)
            
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
    parser.add_argument("--dir", default="data/documents", help="Directory containing PDF documents.")
    parser.add_argument("--max-docs", type=int, help="Maximum number of documents to process.")
    parser.add_argument("--max-cost", type=float, help="Stop if total cost exceeds this USD amount.")
    parser.add_argument("--max-tokens", type=int, help="Target token count for each trace summary.")
    parser.add_argument("--force-regeneration", action="store_true", help="Reprocess documents even if trace exists.")
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel threads.")
    args = parser.parse_args()
    create_document_traces(args.dir, args.max_docs, args.max_cost, args.max_tokens, args.force_regeneration, args.workers)
