# FDDS AI Agents - Architectural Guidelines

## Core Mandate: Headless Engine Only

This project utilizes `gemini-cli-headless` as its **exclusive** AI engine. 

### 🚫 STRICT PROHIBITION
Do **NEVER** incorporate or use the following libraries for AI processing in this project:
- `google-generativeai` (Python SDK) - **EXCEPTION:** Allowed ONLY for raw audio transcription in `src/start_server.py` due to CLI limitations.
- `google-genai` (New Python SDK)
- LangChain, LlamaIndex, or other heavy orchestration frameworks.

### 🛡️ Rationale: The Guardrail Problem
The educational materials provided by **Fundacja Dajemy Dzieciom Siłę (FDDS)** deal with sensitive, heavy, and vital topics such as:
- Child abuse prevention
- Violence and sexual exploitation
- Suicide prevention

Standard SDKs and high-level AI libraries often trigger **unconfigurable, aggressive safety filters** (false-positive blocks) when encountering these legitimate educational materials. This causes the system to fail or censor vital information needed for child protection.

### ⚙️ The Solution: Gemini CLI Headless
The `gemini-cli-headless` wrapper is used because:
1. **Context Resilience:** It provides better tuning for sensitive educational contexts, allowing the AI to process heavy documents without being censored, while still adhering to Google's core safety policies.
2. **Zero-Trust Sandboxing:** It provides a physical Tier-4 sandbox (`allowed_tools=[]`) that ensures agents cannot perform unauthorized operations on the host filesystem.
3. **Deterministic Behavior:** It eliminates hierarchical context pollution and "zombie knowledge" through surgical environment isolation.

---
*If you need to add a new AI feature, integrate it using the established headless pattern with `gemini-cli-headless`.*
