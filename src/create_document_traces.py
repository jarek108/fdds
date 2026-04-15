import os
import json
import logging
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from gemini_cli_headless import run_gemini_cli_headless
from src.utils.config import get_config, setup_logging
from src.utils.hashes import get_or_create_hash_file
from src.utils.calc_stats import calculate_cost

logger = logging.getLogger("doc_tracing")

def process_single_document(pdf_path: str, trace_dir: str, model_id: str, max_tokens: int, force_regeneration: bool) -> Dict[str, Any]:
    """Extracts summary/trace from a single PDF and saves it as <hash>.json."""
    try:
        # 1. Get/Calculate Hash
        file_hash = get_or_create_hash_file(pdf_path)
        if not file_hash:
            return {"source": pdf_path, "status": "error", "message": "Could not calculate hash"}

        trace_path = os.path.join(trace_dir, f"{file_hash}.json")
        
        # 2. Check if trace already exists
        if os.path.exists(trace_path) and not force_regeneration:
            return {"source": pdf_path, "status": "skipped", "hash": file_hash}

        # Clear signal for logging
        print(f"ANALYZING: {os.path.basename(pdf_path)}...", flush=True)
        
        prompt = f"""
Przeanalizuj dołączony dokument PDF i przygotuj jego 'ślad' (trace) dla bazy wiedzy.
Twoim celem jest wyciągnięcie esencji wiedzy w formie skondensowanej, ale bardzo konkretnej.

WYMAGANIA:
1. JĘZYK: Odpowiadaj wyłącznie w języku polskim.
2. TYTUŁ: Podaj dokładny, oficjalny tytuł dokumentu. Bądź zwięzły, nie dodawaj żadnych komentarzy przed ani po tytule.
3. TREŚĆ: Skup się na faktach, liczbach, wytycznych, procedurach i kluczowych przesłaniach. Jeśli dokument wspomina o innych programach FDDS, numerach telefonów (116 111, 800 100 100) lub stronach www, koniecznie je uwzględnij. Unikaj nadmiarowego formatowania Markdown (używaj tylko podstawowych list lub akapitów).
4. LIMIT: Twoja odpowiedź powinna mieć około {max_tokens} tokenów (bądź zwięzły, ale merytoryczny).

STRUKTURA ODPOWIEDZI (ŚCISŁY FORMAT):
Tytuł: [Tutaj wpisz tylko tytuł]
Treść: [Tutaj wpisz treść merytoryczną]

ZAKAZ: Nie pisz "Oto analiza...", "Zgodnie z wytycznymi...", "Dokument dotyczy...". Zacznij od razu od "Tytuł:".
"""
        
        session = run_gemini_cli_headless(
            prompt=prompt,
            model_id=model_id,
            files=[pdf_path]
        )
        
        text = session.text.strip()
        title = "Brak tytułu"
        content = text
        
        if "Tytuł:" in text and "Treść:" in text:
            parts = text.split("Treść:", 1)
            title = parts[0].replace("Tytuł:", "").strip()
            content = parts[1].strip()
        elif "Tytuł:" in text: # Fallback if Treść is missing
            title = text.replace("Tytuł:", "").strip()

        # Calculate cost
        s = session.stats
        cost = calculate_cost(
            model_id, 
            s.get("inputTokens", 0), 
            s.get("outputTokens", 0) + s.get("thoughtTokens", 0), 
            s.get("cachedTokens", 0)
        )

        trace_data = {
            "source_hash": file_hash,
            "original_filename": os.path.basename(pdf_path),
            "tytul": title,
            "zawartosc": content,
            "stats": s,
            "cost": cost,
            "model": model_id,
            "timestamp": session.raw_data.get("timestamp")
        }

        with open(trace_path, 'w', encoding='utf-8') as f:
            json.dump(trace_data, f, indent=2, ensure_ascii=False)
            
        return {"source": pdf_path, "status": "success", "cost": cost, "hash": file_hash}
    except Exception as e:
        logger.error(f"Error processing {pdf_path}: {e}")
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
