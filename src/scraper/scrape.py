import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
from collections import deque
import json
import time
import sys
import argparse

def canonicalize_url(url):
    """
    Cleans a URL by removing fragments and query parameters, 
    and stripping trailing slashes to ensure uniqueness.
    """
    parsed = urlparse(url)
    # Remove fragments and query parameters to avoid 'spider traps'
    new_parsed = parsed._replace(fragment='', query='')
    canonical = urlunparse(new_parsed)
    if canonical.endswith('/'):
        canonical = canonical[:-1]
    return canonical

def is_valid_subpath(url, base_url):
    """
    Ensures the URL is within the same domain and starts with the same path as the base_url.
    """
    parsed_url = urlparse(url)
    parsed_base = urlparse(base_url)
    
    # Stay within the same domain
    if parsed_url.netloc != parsed_base.netloc:
        return False
    
    # Stay within the same starting path (e.g., if we start at /oferta, don't go to /kontakt)
    if not parsed_url.path.startswith(parsed_base.path):
        return False
        
    return True

def is_static_resource(url):
    """
    Skips common static resource extensions.
    """
    extensions = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.docx', '.xlsx', '.mp4', '.mp3')
    return url.lower().endswith(extensions)

def scrape_fdds(start_url, max_depth=2):
    start_url = canonicalize_url(start_url)
    visited = set()
    
    # The root of our tree
    root_node = {
        "url": start_url,
        "title": "Starting Page",
        "children": []
    }
    
    # Queue for BFS: (current_url, current_depth, parent_node_list)
    queue = deque([(start_url, 0, root_node)])
    visited.add(start_url)
    
    print(f"Starting BFS crawl from: {start_url} (Max Depth: {max_depth})")

    while queue:
        url, depth, current_node = queue.popleft()
        
        print(f"[{depth}] Scraping: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                print(f"  Skipped: Status {response.status_code}")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title = soup.title.string.strip() if soup.title else "No Title"
            current_node["title"] = title
            
            if depth >= max_depth:
                continue

            # Find all links
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                absolute_url = urljoin(url, href)
                canonical_child = canonicalize_url(absolute_url)
                
                # Validation rules
                if canonical_child in visited:
                    continue
                if not is_valid_subpath(canonical_child, start_url):
                    continue
                if is_static_resource(canonical_child):
                    # We could log resources here later, but for now we skip them for BFS
                    continue
                
                visited.add(canonical_child)
                
                # Create child node
                child_node = {
                    "url": canonical_child,
                    "title": "Loading...",
                    "children": []
                }
                current_node["children"].append(child_node)
                
                # Add to queue
                queue.append((canonical_child, depth + 1, child_node))
            
            # Polite delay
            time.sleep(0.1)
            
        except Exception as e:
            print(f"  Error scraping {url}: {e}")

    return root_node

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BFS Web Crawler for FDDS Structure mapping.")
    parser.add_argument("url", help="The starting URL (e.g., https://fdds.pl/oferta)")
    parser.add_argument("--depth", type=int, default=2, help="Maximum depth of the crawl (default: 2)")
    parser.add_argument("--output", default="fdds_sitemap.json", help="Output filename (default: fdds_sitemap.json)")
    
    args = parser.parse_args()
    
    result_tree = scrape_fdds(args.url, args.depth)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result_tree, f, indent=2, ensure_ascii=False)
        
    print(f"\nCrawl complete! Sitemap saved to {args.output}")
