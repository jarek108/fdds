import json
import argparse
import sys
from collections import Counter

def analyze_moodle_map(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # Depth-based stats
    # Structure: { depth_int: { "total": 0, "category": 0, "course": 0, "pending": 0, "locked": 0, "files": 0, "leafs": 0 } }
    depth_stats = {}

    def get_depth_node(depth):
        if depth not in depth_stats:
            depth_stats[depth] = {
                "total": 0, "category": 0, "course": 0, 
                "pending": 0, "locked": 0, "files": 0, "leafs": 0
            }
        return depth_stats[depth]

    def traverse(node, depth):
        s = get_depth_node(depth)
        s["total"] += 1
        
        ntype = node.get("node_type", "unknown")
        title = node.get("title", "")
        children = node.get("children", [])
        
        if title == "Pending...":
            s["pending"] += 1
        else:
            if not children:
                s["leafs"] += 1
                
            if ntype == "category":
                s["category"] += 1
            elif "course" in ntype or "login" in ntype:
                s["course"] += 1
        
        if node.get("requires_login"):
            s["locked"] += 1
            
        resources = node.get("resources_found", [])
        s["files"] += len(resources)
        
        for child in children:
            traverse(child, depth + 1)

    traverse(data, 0)

    # Print Report
    print(f"\n{'='*95}")
    print(f" MOODLE MAP ANALYSIS: {file_path}")
    print(f"{'='*95}")
    
    # Table Header
    header = f"{'Depth':<8} | {'Nodes':<6} | {'Category':<10} | {'Course/Lnd':<10} | {'Leafs':<6} | {'Pending':<8} | {'Locked':<7} | {'Files':<6}"
    print(header)
    print("-" * len(header))

    total_all = Counter()

    for depth in sorted(depth_stats.keys()):
        s = depth_stats[depth]
        print(f"Level {depth:<2} | {s['total']:<6} | {s['category']:<10} | {s['course']:<10} | {s['leafs']:<6} | {s['pending']:<8} | {s['locked']:<7} | {s['files']:<6}")
        for k, v in s.items():
            total_all[k] += v

    print("-" * len(header))
    s = total_all
    print(f"{'TOTAL':<8} | {s['total']:<6} | {s['category']:<10} | {s['course']:<10} | {s['leafs']:<6} | {s['pending']:<8} | {s['locked']:<7} | {s['files']:<6}")
    print(f"{'='*95}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Moodle sitemap JSON stats.")
    parser.add_argument("file", help="Path to the moodle_map.json file")
    
    args = parser.parse_args()
    analyze_moodle_map(args.file)
