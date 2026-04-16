---
id: QAR-refactor-headless-wrapper
recipient: QA
parent_request: IRQ.md
---

# Validation Strategy
The validation will focus on ensuring the updated `gemini_cli_headless.py` correctly handles streaming output and strict security policies without breaking existing workflows (tracing and serving).

# Feature-Specific Validation Criteria
- [ ] **Streaming Verification**: Verify that `run_gemini_cli_headless` with `stream_output=True` prints output to the console in real-time.
- [ ] **Policy Verification**: Verify that the generated `--policy` file contains correctly escaped YAML (e.g., `name: "*"`) and that the CLI doesn't throw "Access Denied" errors for its own temporary prompt files.
- [ ] **Import Integrity**: Run a syntax check (`python -m py_compile`) on `src/create_document_traces.py`, `src/create_master_session.py`, and `src/start_server.py` to ensure imports are valid.
- [ ] **Regression Test**: Execute `src/create_document_traces.py` with `--max-docs 1` to verify successful CLI interaction.
- [ ] **Cleanup Check**: Confirm `final_fix.py` no longer exists in the root directory.

# Specific Risk Areas
- **Deadlocks**: The change from `process.communicate()` to `readline()` loop must be carefully checked to ensure it handles both stdout and stderr (which are merged in this case) correctly without hanging.
- **YAML Escaping**: Incorrect escaping in the policy file can cause the Gemini CLI to fail to parse its configuration.

# Mandatory Rituals
- **Experimentation**: Any test scripts used for validation should be placed in `playground/`.
