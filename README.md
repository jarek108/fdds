# FDDS AI Assistant & Knowledge Base

An intelligent, high-performance, and cost-effective AI Assistant designed to answer user inquiries based on the extensive educational materials provided by the **Fundacja Dajemy Dzieciom Siłę (FDDS)**.

## 🎯 Project Overview

Directly querying Large Language Models (LLMs) with massive raw binary files (like PDFs) on every user request is computationally expensive, slow, and scales poorly. To solve this, this project implements a highly optimized architecture:

1. **Pre-processing & Extraction:** The system reads and analyzes each PDF document exactly once during an initialization phase to extract core topics, actionable facts, and critical guidelines.
2. **Dense Knowledge Base:** Extracted insights are compiled in-memory into a lightweight, token-efficient text format.
3. **Session Cloning (Warm Start):** By leveraging Context Caching and Session Cloning, the system maintains a "Master Session" primed with the knowledge base. User sessions are cloned from this master session, ensuring instantaneous response times, strict data isolation between users, and drastically reduced API costs.

---

## 🏗️ System Architecture

The application is modularized into three core pillars:

### 1. Data Scraping & Ingestion
Located in `src/`. The `crawler.py` script securely interacts with the FDDS Moodle platform to scrape HTML structures, map course hierarchies, and autonomously download raw source documents.

### 2. Knowledge Processing
Located in `src/`. The caching layer orchestrates the knowledge extraction pipeline:
* **Trace Generation:** A robust LLM (e.g., Gemini 1.5 Pro) processes raw PDFs to generate individual JSON "traces" (via `src/utils/gemini_cli_headless.py`) containing summaries, context, and core content.
* **Correction Layer:** Live, high-priority manual overrides can be maintained via `data/correction.txt`. These act as hotfixes to outdated or conflicting data across all scraped documents without requiring expensive re-parsing of raw PDFs.
* **Compilation:** Traces and the Correction Layer are merged in-memory into a single, comprehensive Markdown text block.
* **Master Session Initialization:** The final compiled knowledge base is injected into the LLM context to establish the cached master session (`master_session.json`). To prevent hallucinated titles, the LLM is instructed to only return raw references like `[doc_1]`.

### 3. API & Web UI Serving
Located in `src/`. A concurrent, multi-threaded Python HTTP server handles:
* **Chat Endpoints (`/ask`):** Clones sessions for isolated multi-user chatting. Post-processes LLM responses to safely translate raw `[doc_1]` references into full, clickable Markdown URLs (`[Real Title](URL)`) using the master index.
* **Admin Panel (`/admin`):** A comprehensive web UI for managing the knowledge base. It allows administrators to upload PDFs, create folders, hide/delete documents, and trigger a one-click synchronization (`Sync KB`) that automatically handles trace generation and master session compilation in the background. It features a real-time KB synchronization status indicator based on content fingerprints.
* **Live Corrections (`/correction`):** A dedicated UI to edit global, high-priority knowledge overrides (`data/correction.txt`). Saving updates automatically triggers a background rebuild of the Master Session.
* **Static Assets:** Securely serves local static assets, audio files, and PDF materials.

---

## 🛠️ Why Gemini CLI as the Engine?

While traditional SDKs (`google-genai`) or end-user tools like NotebookLM are popular, **Gemini CLI** was chosen as the core engine for this specific project due to several critical advantages:

1. **Handling Sensitive Educational Contexts:** The educational materials from FDDS deal extensively with sensitive and heavy topics, such as child abuse prevention, violence, and suicide prevention. While standard SDKs and cloud APIs often trigger overly aggressive, unconfigurable safety filters (false-positive blocks) on legitimate educational materials, Gemini CLI provides better out-of-the-box tuning for these contexts. This allows the AI to process vital educational documents without being continuously censored, while still strictly adhering to Google's safety policies and Terms of Service (we are not bypassing or disabling required safety guardrails, but rather utilizing an interface optimized for complex context).
2. **Overcoming NotebookLM's Limitations:** NotebookLM is an excellent SaaS tool, but it imposes a hard limit of 200 source documents per notebook. By building a custom pipeline with Gemini CLI, we can compile an unlimited number of documents into a single, highly dense Master Session.
3. **Granular Control & Automation:** Unlike closed SaaS platforms, the CLI acts as a programmable layer. It inherently supports autonomous execution (`--yolo`), built-in JSON parsing (`-o json`), and instant context caching (via file-based session cloning with `-r`), allowing us to build the complex "Master Session" architecture, the Correction Layer, and custom link post-processing that wouldn't be possible otherwise.

## 🧪 Testing Strategy
A comprehensive End-to-End (E2E) testing strategy is defined in [QAR.md](QAR.md). This strategy details approximately 40 robust test cases covering everything from Document Lifecycle and Knowledge Base hotfixing to Multi-tenant isolation and Quota enforcement using live LLM models in sandboxed environments.

---

## 🚀 Getting Started

### Prerequisites
* **Python 3.9+**
* **Gemini CLI:** Must be installed and authenticated (`gemini --version` should execute successfully).
* **Environment Variables:** Copy the `config/.env.example` file to `config/.env` and provide your API key.
  ```bash
  cp config/.env.example config/.env
  # Then edit config/.env with your favorite editor
  ```

### ⚡ Quick Start (TL;DR)
If you want to run the entire pipeline with default settings, simply start the server and use the built-in Admin Panel to manage your documents and sync the Knowledge Base automatically.

```bash
# Start the server (runs on port 8000 by default)
python src/start_server.py
```
Then navigate to [http://localhost:8000/admin](http://localhost:8000/admin) to upload PDFs and click **"🔄 Synchronizuj Bazę Wiedzy"** to automatically generate traces and compile the Master Session.

---

### Step-by-Step Instructions

This system operates as a strict pipeline. Each step depends on the output of the previous one.

#### 1. Crawl Platform & Map Structure (Optional)
* **What it does:** Scans the FDDS Moodle platform to build a structural map of courses and pages and downloads raw PDFs to `data/documents/`.
* **Command:** `python src/crawler.py`

#### 2. Start the Application Server
* **What it does:** Hosts the frontend Web UI, Admin Panel, API endpoints, and handles isolated user sessions.

```bash
python src/start_server.py
```

#### 3. Build the Knowledge Base via Admin Panel
* Navigate to the Admin Panel: [http://localhost:8000/admin](http://localhost:8000/admin)
* **What it does:** The Admin Panel provides a visual tree of all documents. You can upload new PDFs, create folders, or hide files. 
* **Action:** Click **"🔄 Synchronizuj Bazę Wiedzy"**. The server will automatically:
  1. Generate lightweight JSON traces for any *new* or *modified* PDFs using the LLM (saving API costs by skipping unchanged files).
  2. Compile all traces into a single Master Knowledge Base (`master_knowledge_base.md`).
  3. Initialize the cached 'Master Session' (`master_session.json`) for instant user chat initialization.
* **Status:** A real-time red/green indicator will show if your Knowledge Base is perfectly synced with your files.

#### 4. Access the Interface
* **Chat UI:** Navigate to [http://localhost:8000/](http://localhost:8000/) in your web browser to interact with the Assistant.
* **Admin Panel:** Navigate to [http://localhost:8000/admin](http://localhost:8000/admin) to manage files and KB synchronization.
* **Live Corrections UI:** Navigate to [http://localhost:8000/correction](http://localhost:8000/correction) to hotfix the knowledge base.

---

## 📂 Project Structure

```text
.
├── config/                 # Configuration files
│   ├── config.json         # Central configuration file (paths, model settings, URLs).
│   ├── models.json         # Models pricing and specifications.
│   ├── .env                # API keys and secrets (not tracked by git).
│   └── .env.example        # Example environment variables template.
├── public/                 # Frontend assets (served by the HTTP server).
│   ├── index.html          # Main Web UI for the chat interface.
│   └── assets/             # Static assets like images and logos.
├── data/                   # Data storage for scraped content and generated caches.
│   ├── documents/          # Raw downloaded documents (PDFs, scenarios).
│   ├── traces/             # Individual JSON knowledge traces per PDF.
│   ├── sessions/           # Live user session mappings and histories.
│   └── master_session.json # The master session used for context cloning.
└── src/                    # Source code modularized by domain.
    ├── crawler.py                    # Interacts with Moodle to map courses and download PDFs.
    ├── create_master_session.py      # Merges JSON traces into KB and primes the master session.
    ├── create_document_traces.py     # Processes raw PDFs to extract insights into JSON traces.
    ├── start_server.py               # Hosts the Web UI, API endpoints, and manages session cloning.
    └── utils/                        # Shared helper modules (CLI wrappers, config, stats).
        ├── gemini_headless_adapter.py # Thin adapter for the gemini-cli-headless PyPI package.
        ├── calc_stats.py             # Calculates LLM token usage and estimated API costs.
        ├── config.py                 # Centralized configuration loader and logging setup.
        └── ...                       # Additional temporary inspection and mapping utilities.
```

## 📊 Cost Optimization & Analytics
The system inherently tracks LLM usage per user interaction. Token consumption (input, output, cached, and thought tokens) and estimated API costs are automatically calculated and appended to the chat response payload for real-time frontend monitoring. You can also run the standalone script `python src/utils/calc_stats.py data/sessions/` to audit historical session costs.