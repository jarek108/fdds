"""
Interacts with the FDDS Moodle platform to scrape HTML structures, map course hierarchies, 
and autonomously download raw source documents (PDFs, brochures, scenarios).

Prerequisite: 
Requires 'moodle_url' and paths configured in `config/config.json`.

Usage Examples:
    # Map the Moodle platform with default settings (max 50 nodes, depth 3)
    python src/crawler.py

    # Map with custom limits
    python src/crawler.py --nodes 100 --depth 5 --url https://edukacja.fdds.pl/

Arguments:
    --url     Starting URL for the crawl.
    --depth   Maximum depth of the BFS crawl.
    --nodes   Maximum number of nodes to process.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs
from collections import deque
import json
import time
import sys
import argparse
import os
import re
import logging
from typing import Dict, List, Optional, Tuple, Set, Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from src.utils.config import get_config, setup_logging

logger = logging.getLogger("moodle_scraper")

class UrlManager:
    """Handles URL canonicalization and visitability checks."""
    
    ALLOWED_PARAMS = {'categoryid', 'id', 'course'}
    VISITABLE_PATHS = {
        '/course/index.php',
        '/course/view.php',
        '/local/easylogin/index.php',
        '/mod/page/view.php'
    }

    @staticmethod
    def canonicalize(url: str) -> str:
        """Cleans a URL by removing fragments and irrelevant query parameters."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        query_parts = []
        for p in UrlManager.ALLOWED_PARAMS:
            if p in params:
                query_parts.append(f"{p}={params[p][0]}")
        
        new_query = "&".join(query_parts)
        new_parsed = parsed._replace(fragment='', query=new_query)
        canonical = urlunparse(new_parsed)
        return canonical.rstrip('/')

    @staticmethod
    def is_visitable(url: str, base_netloc: str) -> bool:
        """Checks if the URL is a Moodle structural node on the same domain."""
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != base_netloc:
            return False
        return any(parsed.path.endswith(v) for v in UrlManager.VISITABLE_PATHS)

    @staticmethod
    def get_safe_filename(url: str) -> str:
        """Converts a URL into a safe filename."""
        parsed = urlparse(url)
        path_query = parsed.path + "_" + parsed.query
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', path_query)
        return safe_name.strip('_') + ".html"


class CacheManager:
    """Handles HTML storage and base tag injection."""
    
    def __init__(self, cache_dir: str, base_href: str):
        self.cache_dir = cache_dir
        self.base_href = base_href
        os.makedirs(cache_dir, exist_ok=True)

    def save_html(self, url: str, html_content: str) -> str:
        """Saves HTML content to disk with a <base> tag injected."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Inject <base> tag so relative links work offline
        if not soup.find('base'):
            base_tag = soup.new_tag('base', href=self.base_href)
            if soup.head:
                soup.head.insert(0, base_tag)
        
        filename = UrlManager.get_safe_filename(url)
        file_path = os.path.join(self.cache_dir, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
            
        return os.path.join("html_cache", filename) # Store relative to data/


class MoodleCrawler:
    """Core logic for crawling Moodle structure."""

    def __init__(self, start_url: str, max_depth: int = 3, max_nodes: int = 100):
        config = get_config()
        self.paths = config['paths']
        self.start_url = UrlManager.canonicalize(start_url)
        self.base_netloc = urlparse(self.start_url).netloc
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        
        if "moodle_url" not in config:
            raise KeyError("Missing required 'moodle_url' in config/config.json")
        self.cache = CacheManager(self.paths['html_cache_dir'], config['moodle_url'])
        self.output_file = self.paths['moodle_map_file']
        
        self.root_node = None
        self.visited: Dict[str, Dict] = {}
        self.queue: deque = deque()
        self.nodes_processed = 0

    def load_state(self):
        """Loads existing crawl state from the map file."""
        if not os.path.exists(self.output_file):
            self._init_fresh_state()
            return

        logger.info(f"Resuming from {self.output_file}...")
        with open(self.output_file, 'r', encoding='utf-8') as f:
            self.root_node = json.load(f)

        def walk(node, depth):
            url = node["url"]
            self.visited[url] = node
            if node.get("local_html_file") is None:
                if depth <= self.max_depth:
                    self.queue.append((url, depth, node))
            else:
                for child in node.get("children", []):
                    walk(child, depth + 1)

        walk(self.root_node, 0)
        logger.info(f"Reconstructed: {len(self.visited)} nodes, {len(self.queue)} pending.")

    def _init_fresh_state(self):
        """Initializes a new crawl state."""
        self.root_node = {
            "url": self.start_url,
            "title": "Root",
            "node_type": "root",
            "requires_login": False,
            "local_html_file": None,
            "children": []
        }
        self.visited = {self.start_url: self.root_node}
        self.queue = deque([(self.start_url, 0, self.root_node)])
        logger.info(f"Starting fresh crawl from: {self.start_url}")

    def _check_requires_login(self, response_url: str, html: str) -> bool:
        """Detects if a page requires authentication."""
        if 'login' in response_url.lower():
            return True
        indicators = ['id="login"', 'name="loginform"', 'Zaloguj się', 'Guest access', 'Musisz się zalogować']
        return any(ind in html for ind in indicators)

    def crawl(self):
        """Executes the crawl loop."""
        logger.info(f"Crawl Limits: Depth={self.max_depth}, Nodes={self.max_nodes}")
        
        try:
            while self.queue and self.nodes_processed < self.max_nodes:
                url, depth, current_node = self.queue.popleft()
                
                if current_node.get("local_html_file"):
                    continue

                self.nodes_processed += 1
                logger.info(f"[{self.nodes_processed}/{self.max_nodes}] (D:{depth}) Scraping: {url}")
                
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    response = requests.get(url, headers=headers, timeout=15)
                    
                    if response.status_code != 200:
                        current_node["local_html_file"] = f"ERROR_{response.status_code}"
                        continue

                    html = response.text
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Update Metadata
                    current_node["title"] = soup.title.get_text(strip=True) if soup.title else "No Title"
                    current_node["requires_login"] = self._check_requires_login(response.url, html)
                    
                    path = urlparse(url).path
                    if 'index.php' in path: current_node["node_type"] = "category"
                    elif 'view.php' in path: current_node["node_type"] = "course/page"
                    elif 'easylogin' in path: current_node["node_type"] = "login_landing"

                    # Save to Cache
                    rel_path = self.cache.save_html(url, html)
                    current_node["local_html_file"] = rel_path

                    # Discovery
                    if not current_node["requires_login"]:
                        for a in soup.find_all('a', href=True):
                            child_url = UrlManager.canonicalize(urljoin(url, a['href']))
                            
                            if child_url not in self.visited and UrlManager.is_visitable(child_url, self.base_netloc):
                                child_node = {
                                    "url": child_url, "title": "Pending...", "node_type": "unknown",
                                    "requires_login": False, "local_html_file": None, "children": []
                                }
                                current_node["children"].append(child_node)
                                self.visited[child_url] = child_node
                                if depth + 1 <= self.max_depth:
                                    self.queue.append((child_url, depth + 1, child_node))
                    
                    self.save_map()
                    time.sleep(0.2)
                    
                except Exception as e:
                    logger.error(f"Error scraping {url}: {e}")
                    current_node["local_html_file"] = f"EXCEPTION_{str(e)[:20]}"

        except KeyboardInterrupt:
            logger.info("Interrupted. Saving state...")
            self.save_map()

    def save_map(self):
        """Writes the current crawl map to disk."""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.root_node, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Modular Moodle Crawler")
    parser.add_argument("--url", default="https://edukacja.fdds.pl/", help="Starting URL")
    parser.add_argument("--depth", type=int, default=3, help="Max depth")
    parser.add_argument("--nodes", type=int, default=50, help="Max nodes")
    args = parser.parse_args()
    
    crawler = MoodleCrawler(args.url, args.depth, args.nodes)
    crawler.load_state()
    crawler.crawl()
    logger.info("Scrape cycle complete.")
