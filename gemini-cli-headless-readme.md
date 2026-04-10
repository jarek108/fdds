# gemini-cli-headless

A standalone, zero-dependency Python wrapper for executing the official Node.js Google Gemini CLI (`@google/gemini-cli`) in fully programmatic, headless mode.

## Why this wrapper?
While the official Python SDKs (`google-genai`) are excellent for building API-driven applications, they often impose strict, unconfigurable safety guardrails (blocking sensitive topics like abuse prevention) and require complex context-caching implementations for session history.

The **Gemini CLI** inherently bypasses many of these cloud limitations out-of-the-box and handles robust file-based session management. This wrapper provides a typed, Pythonic bridge to the CLI's `--json` and `--yolo` flags, allowing you to easily build complex RAG (Retrieval-Augmented Generation) pipelines, automate local file analysis, and effortlessly resume context-rich conversations across different projects.

## Key Features
*   **Zero Dependencies:** Relies purely on Python standard libraries (`subprocess`, `json`, `tempfile`). No need for `requests` or `python-dotenv`.
*   **Smart Session Resumption:** Pass either a raw UUID (`"abc-123"`) or a local JSON file path (`"data/user_session.json"`). If a path is provided, the wrapper automatically injects your local file into the CLI's internal workspace before execution, allowing portable, file-based conversation history.
*   **Structured Output:** Automatically parses the CLI's JSON stdout into a `GeminiSession` dataclass containing the AI's response, the session ID, and detailed token statistics (input, output, cached, thoughts).
*   **Bypass Length Limits:** Long prompts are automatically saved to temporary files and attached via the `@path` syntax, preventing OS-level terminal length restrictions.

## Installation
Currently available via GitHub:
```bash
pip install git+https://github.com/jarek108/gemini-cli-headless-python.git
```

*(Requires Node.js and `@google/gemini-cli` installed globally: `npm install -g @google/gemini-cli`)*

## Quick Start
```python
import shutil
from gemini_cli_headless import run_gemini_cli_headless

# Start a new conversation
session = run_gemini_cli_headless("Explain quantum computing in one sentence.")
print(f"AI: {session.text}")

# Save the session locally
shutil.copy2(session.session_path, "my_context.json")

# Resume the conversation later from your local file!
new_session = run_gemini_cli_headless(
    prompt="Now explain it to a 5-year-old.",
    session_to_resume="my_context.json"
)
```