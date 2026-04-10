"""
Calculates token usage and estimated API costs for Gemini models.
Supports auditing local session files or individual token counts.

Usage Examples:
    # Use as a library
    from src.utils.calc_stats import calculate_cost
    usd = calculate_cost("gemini-1.5-pro", 1000, 500, 2000)

    # Audit a directory of session JSONs via CLI
    python src/utils/calc_stats.py data/sessions/
"""

import json
import argparse
import os
import glob
from datetime import datetime

# Pricing table per 1,000,000 tokens
PRICING = {
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50, "cached": 0.875},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30, "cached": 0.01875},
    "gemini-3.1-pro": {"input": 3.50, "output": 10.50, "cached": 0.875},
    "gemini-3.1-flash": {"input": 0.075, "output": 0.30, "cached": 0.01875},
    "gemini-3-pro": {"input": 3.50, "output": 10.50, "cached": 0.875},
    "gemini-3-flash": {"input": 0.075, "output": 0.30, "cached": 0.01875}
}

def calculate_cost(model_name: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    cost = 0.0
    price_key = None
    # Normalize model name for matching (e.g. gemini-3.1-pro-preview -> gemini-3.1-pro)
    for k in PRICING.keys():
        if k in model_name:
            price_key = k
            break
    
    # Fallback for version differences (e.g. if we have 3.1-pro and found 3.1-pro-preview)
    if not price_key:
        if "pro" in model_name.lower(): price_key = "gemini-3.1-pro"
        elif "flash" in model_name.lower(): price_key = "gemini-3.1-flash"

    if price_key:
        p = PRICING[price_key]
        cost = (input_tokens / 1_000_000 * p["input"]) + \
               (output_tokens / 1_000_000 * p["output"]) + \
               (cached_tokens / 1_000_000 * p["cached"])
    return cost

def analyze_session(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error parsing JSON {file_path}: {e}")
        return None

    # 1. Basic Metadata
    messages = data.get('messages', [])
    if not messages:
        return None
        
    model_name = messages[-1].get('model', 'unknown')
    
    # 2. Token Counts (for the LAST turn only)
    last_tokens = messages[-1].get('tokens', {})
    input_tokens = last_tokens.get('input', 0)
    output_tokens = last_tokens.get('output', 0)
    cached_tokens = last_tokens.get('cached', 0)

    # 3. Time duration of the LAST message (the answer)
    duration = "unknown"
    if len(messages) >= 2:
        def parse_iso(iso_str):
            return datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        
        try:
            start_dt = parse_iso(messages[-2].get('timestamp'))
            end_dt = parse_iso(messages[-1].get('timestamp'))
            duration = end_dt - start_dt
        except:
            pass

    # 4. Cost Estimation
    cost = calculate_cost(model_name, input_tokens, output_tokens, cached_tokens)
    
    return {
        "file": os.path.basename(file_path),
        "model": model_name,
        "input": input_tokens,
        "output": output_tokens,
        "cached": cached_tokens,
        "duration": str(duration).split('.')[0], 
        "cost": round(cost, 6)
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate stats from saved Gemini CLI session JSON files.")
    parser.add_argument("input", help="Path to a single session JSON file or a directory containing them.")
    
    args = parser.parse_args()
    
    files = []
    if os.path.isdir(args.input):
        files = glob.glob(os.path.join(args.input, "*.json"))
    else:
        files = [args.input]

    if not files:
        print("No session files found.")
    else:
        print(f"{'FILE':<35} | {'MODEL':<20} | {'INPUT':>8} | {'OUTPUT':>8} | {'TIME':>10} | {'COST ($)':>10}")
        print("-" * 110)
        
        grand_total_cost = 0.0
        for f in files:
            stats = analyze_session(f)
            if stats:
                print(f"{stats['file'][:35]:<35} | {stats['model'][:20]:<20} | {stats['input']:>8} | {stats['output']:>8} | {stats['duration']:>10} | {stats['cost']:>10.6f}")
                grand_total_cost += stats['cost']
        
        print("-" * 110)
        print(f"{'TOTAL ESTIMATED COST:':>88} | {grand_total_cost:>10.6f}")
