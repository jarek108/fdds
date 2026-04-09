"""
Extracts knowledge from raw PDFs into lightweight JSON traces using parallel processing.

Prerequisite: 
Requires raw PDF documents to be present in the `data/documents/` directory (or a custom directory).

This script relies on the Google Generative AI SDK (configured via `src/utils/run_gemini.py`)
to read PDF files and generate structured JSON summaries ("traces") that capture the essence
of each document. These traces are later used to build the master knowledge base.

Usage Examples:
    # Process all PDFs using default settings (5 workers, ~200 tokens per summary)
    python src/processor/create_document_traces.py

    # Process a maximum of 10 documents, targeting a 500-token summary length
    python src/processor/create_document_traces.py --max-docs 10 --max-tokens 500

    # Force regeneration of traces even if they already exist, using 10 parallel workers
    python src/processor/create_document_traces.py --force-regeneration --workers 10

    # Process a specific directory with a cost limit
    python src/processor/create_document_traces.py --dir custom/pdf/path --max-cost 2.50

Arguments:
    --dir                 Optional: Custom directory containing PDFs to process. Defaults to `data/documents/`.
    --max-docs            Optional: Limit the maximum number of documents to process. Useful for testing.
    --max-cost            Optional: Stop processing if the estimated API cost exceeds this dollar amount.
    --max-tokens          Target length for the "Zawartość" section of the summary (default: 200).
    --force-regeneration  If set, overwrites existing JSON trace files instead of skipping them.
    --workers             Number of parallel threads to use for API requests (default: 5).
"""

import os
import glob
import time
import json
import argparse
import sys
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.utils.run_gemini import run_gemini
from src.utils.config import get_config, setup_logging
from src.utils.calc_stats import calculate_cost

logger = logging.getLogger("create_document_traces")

# Shared state for parallel execution
print_lock = threading.Lock()
stats_lock = threading.Lock()
stop_flag = threading.Event()

totals = {
    "cost": 0.0,
    "input": 0,
    "output": 0,
    "cached": 0,
    "docs_processed": 0,
    "skipped_docs": 0
}

# Preserve the user's customized prompt
BASE_PROMPT = """Jesteś ekspertem ds. analizy dokumentów i edukacji w Fundacji Dajemy Dzieciom Siłę (FDDS). Twoim zadaniem jest przeczytanie załączonego dokumentu i przygotowanie dla niego skondensowanej "metryczki wiedzy" (trace file). 

Ta metryczka zostanie wczytana do pamięci szybkiego asystenta AI, który będzie na jej podstawie odpowiadał na pytania użytkowników. Musi być zwięzła, nasycona faktami i napisana w sposób naturalny, gotowy do zaprezentowania człowiekowi.

Przeanalizuj cały dokument i wygeneruj odpowiedź składającą się tylko z poniższych sekcji. Nie dodawaj żadnych wstępów, powitań, ani znaczników formatowania Markdown takich jak nagłówki (np. ###). Po prostu rozpocznij każdą sekcję (Tytuł, Zawartość) od jej nazwy.


Tytuł: Krótka, human-friendly nazwa dokumentu (ale niekoniecznie pliku!)

Zawartość (około {max_tokens} tokenów):

We wstępie opisz krótko cel, Odbiorców (np. rodzice małych dzieci, nastolatkowie, nauczyciele, profesjonaliści).

Teraz wydobądź najważniejszą wiedzę z dokumentu. Skup się na konkretach: zasady, wytyczne, kroki postępowania, statystyki, zjawiska lub definicje. Pomiń "lanie wody", wstępy historyczne czy informacje redakcyjne. Wyobraź sobie, że notujesz "mięso" dla kogoś, kto ma tylko minutę na przygotowanie się do wykładu z tego tematu. Zachowaj profesjonalny, wspierający ton charakterystyczny dla FDDS.

Na koniec dodaj powiązania z innymi tematami, programami lub dokumentami FDDS. Zrób to tylko jeśli jest coś faktycznie istotnego w tym konkretnym przypadku.

Pamiętaj nie przekraczać {max_tokens} tokenów dla całości.
"""

def parse_model_response(text: str) -> Dict[str, str]:
    """Parses the raw AI response into structured sections."""
    sections = {"tytul": "", "zawartosc": ""}
    
    # Clean up AI prologue
    search_anchor = "Tytuł" if "Tytuł" in text else "Zawartość"
    if search_anchor in text:
        text = text[text.find(search_anchor):]
    
    current_section = None
    buffer = []
    
    for line in text.split('\n'):
        lower_line = line.lower().strip()
        if lower_line.startswith("tytuł") or lower_line.startswith("tytul"):
            current_section = "tytul"
            buffer = [line.split(':', 1)[1].strip() if ':' in line else ""]
        elif lower_line.startswith("zawartość") or lower_line.startswith("zawartosc"):
            if current_section: sections[current_section] = "\n".join(buffer).strip()
            current_section = "zawartosc"
            buffer = [line.split(':', 1)[1].strip() if ':' in line else ""]
        else:
            if current_section:
                buffer.append(line)
                
    if current_section:
        sections[current_section] = "\n".join(buffer).strip()
        
    return sections

def process_single_pdf(pdf_path: str, documents_dir: str, job_dir: str, session_folder: str, model: str, 
                       max_tokens: int, force_regeneration: bool):
    """Worker function to process one PDF."""
    global totals
    
    if stop_flag.is_set():
        return

    rel_pdf_path = os.path.relpath(pdf_path, documents_dir).replace('\\', '/')
    trace_rel_path = rel_pdf_path.rsplit('.', 1)[0] + ".json"
    trace_path = os.path.join(job_dir, trace_rel_path)
    
    # Check if file exists to skip processing
    if os.path.exists(trace_path) and not force_regeneration:
        with stats_lock:
            totals["skipped_docs"] += 1
            totals["docs_processed"] += 1
            current_idx = totals["docs_processed"]
        with print_lock:
            print(f"{current_idx:<3} | {'00:00':<8} | {'-':<10} | {'-':<10} | {'-':<8} | {'-':<5} | {'-':<8} | {'-':<8} | {'SKIP':<6} | {rel_pdf_path}")
        return

    start_time = time.time()
    formatted_prompt = BASE_PROMPT.format(max_tokens=max_tokens)
    instruction_text = f"{formatted_prompt.strip()}\nANALIZUJ DOKUMENT:"

    answer, result_info, error = run_gemini(model, prompt=instruction_text, session_folder=session_folder, files=[pdf_path])
    
    duration = time.time() - start_time
    time_str = f"{int(duration // 60):02d}:{int(duration % 60):02d}"
    
    if error or not answer:
        with print_lock:
            print(f"{'ERR':<3} | {time_str:<8} | {'-':<10} | {'-':<10} | {'-':<8} | {'-':<5} | {'-':<8} | {'-':<8} | {'ERROR':<6} | {rel_pdf_path}")
            if error: logger.error(f"Error in {rel_pdf_path}: {error}")
        return
        
    session_id = result_info.get("session_id", "N/A")
    stats_raw = result_info.get("stats", {}) or {}
    model_stats = stats_raw.get("models", {}).get(model, {}).get("tokens", {})
    
    in_tk, out_tk, cached_tk, thought_tk = (
        model_stats.get("input", 0), 
        model_stats.get("candidates", 0), 
        model_stats.get("cached", 0), 
        model_stats.get("thoughts", 0)
    )
    
    cost = calculate_cost(model, in_tk, out_tk + thought_tk, cached_tk)
    structured_data = parse_model_response(answer)
    
    # Validate that we actually extracted something meaningful
    if not structured_data.get("zawartosc"):
        with print_lock:
            print(f"{'ERR':<3} | {time_str:<8} | {session_id[:8]:<10} | {thought_tk:<10} | {in_tk:<8} | {out_tk:<5} | {cached_tk:<8} | ${cost:.4f} | {'ERROR':<6} | {rel_pdf_path}")
            logger.error(f"Model returned invalid or empty format for {rel_pdf_path}. Raw answer: {repr(answer)}")
        return

    structured_data.update({
        "source": rel_pdf_path,
        "session_id": session_id,
        "model": model,
        "tokens": {"in": in_tk, "out": out_tk, "cached": cached_tk, "thoughts": thought_tk},
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })
        
    os.makedirs(os.path.dirname(trace_path), exist_ok=True)
    with open(trace_path, 'w', encoding='utf-8') as f:
        json.dump(structured_data, f, indent=2, ensure_ascii=False)
        
    with stats_lock:
        totals["docs_processed"] += 1
        totals["cost"] += cost
        totals["input"] += in_tk
        totals["output"] += out_tk + thought_tk
        totals["cached"] += cached_tk
        current_idx = totals["docs_processed"]
        
    with print_lock:
        print(f"{current_idx:<3} | {time_str:<8} | {session_id[:8]:<10} | {thought_tk:<10} | {in_tk:<8} | {out_tk:<5} | {cached_tk:<8} | ${cost:.4f} | {'OK':<6} | {rel_pdf_path}")

def create_document_traces(target_dir: Optional[str] = None, max_docs: Optional[int] = None, 
               max_cost: Optional[float] = None, max_tokens: int = 200, 
               force_regeneration: bool = False, workers: int = 5) -> None:
    """Processes PDF documents in parallel and generates structured trace files (JSON)."""
    config = get_config()
    paths = config['paths']
    
    documents_dir = target_dir or paths['documents_dir']
    traces_root = paths['traces_dir']
    if "doc_tracing_model" not in config:
        raise KeyError("Missing required 'doc_tracing_model' in config/config.json")
    model = config["doc_tracing_model"]
    
    # Create job-specific directory
    job_dir_name = f"{max_tokens}_{model.replace('.', '_')}"
    job_dir = os.path.join(traces_root, job_dir_name)
    os.makedirs(job_dir, exist_ok=True)

    # Generate a unique folder for this specific run's sessions
    run_timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    session_folder = f"{run_timestamp}_trace_creation"

    pdf_files = glob.glob(os.path.join(documents_dir, "**/*.pdf"), recursive=True)
    if not pdf_files:
        logger.warning(f"No PDFs found in {documents_dir}")
        return

    print(f"Starting Knowledge Extraction for {len(pdf_files)} documents using {model}...")
    print(f"  Parallel workers: {workers}")
    print(f"  Target summary length: ~{max_tokens} tokens per document")
    print(f"  Output directory: {job_dir}")
    if max_docs: print(f"  Limit: Max Documents = {max_docs}")
    if max_cost: print(f"  Limit: Max Cost = ${max_cost:.2f}")
    print("-" * 120)
    
    header = f"{'#':<3} | {'Time':<8} | {'Session':<10} | {'Thought Tk':<10} | {'In':<8} | {'Out':<5} | {'Cached':<8} | {'Cost':<8} | {'Status':<6} | {'Document'}"
    print(header)
    print("-" * len(header))

    # Use ThreadPoolExecutor for parallel processing
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = []
    
    try:
        # Submit tasks while respecting the max_docs limit
        submitted_count = 0
        for pdf_path in pdf_files:
            if stop_flag.is_set():
                break
            if max_docs and submitted_count >= max_docs:
                break
            
            rel_pdf_path = os.path.relpath(pdf_path, documents_dir).replace('\\', '/')
            trace_rel_path = rel_pdf_path.rsplit('.', 1)[0] + ".json"
            trace_path = os.path.join(job_dir, trace_rel_path)

            # Pre-check skip to keep counting accurate
            if os.path.exists(trace_path) and not force_regeneration:
                with stats_lock:
                    totals["skipped_docs"] += 1
                    totals["docs_processed"] += 1
                    current_idx = totals["docs_processed"]
                with print_lock:
                    print(f"{current_idx:<3} | {'00:00':<8} | {'-':<10} | {'-':<10} | {'-':<8} | {'-':<5} | {'-':<8} | {'-':<8} | {'SKIP':<6} | {rel_pdf_path}")
                continue

            futures.append(executor.submit(
                process_single_pdf, 
                pdf_path, documents_dir, job_dir, session_folder, model, 
                max_tokens, force_regeneration
            ))
            submitted_count += 1
        
        # Monitor completion and cost limits
        for future in as_completed(futures):
            if stop_flag.is_set():
                break
            try:
                future.result() # Wait for completion and catch errors
            except Exception as e:
                logger.error(f"Worker thread failed: {e}")
                
            # Cost limit check
            with stats_lock:
                if max_cost and totals["cost"] >= max_cost:
                    stop_flag.set()
                    break
    except KeyboardInterrupt:
        with print_lock:
            print(f"\n[!] CTRL+C detected. Shutting down gracefully...")
        stop_flag.set()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    print("=" * 120)
    print("BATCH PROCESSING COMPLETE")
    print(f"Newly Processed: {totals['docs_processed'] - totals['skipped_docs']} | Skipped: {totals['skipped_docs']}")
    print(f"Total Tokens In: {totals['input']} | Out: {totals['output']} | Cost: ${totals['cost']:.6f}")
    print(f"\n[!] To update the knowledge base, run:\n    python src/processor/create_master_session.py {job_dir}")
    print("=" * 120)

if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Build knowledge base traces for PDFs.")
    parser.add_argument("--dir", help="Directory containing PDFs to process.")
    parser.add_argument("--max-docs", type=int, help="Limit number of documents.")
    parser.add_argument("--max-cost", type=float, help="Limit maximum cost.")
    parser.add_argument("--max-tokens", type=int, default=200, help="Target summary length.")
    parser.add_argument("--force-regeneration", action="store_true", help="Force overwrite existing traces.")
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel threads.")
    args = parser.parse_args()
    create_document_traces(args.dir, args.max_docs, args.max_cost, args.max_tokens, args.force_regeneration, args.workers)
