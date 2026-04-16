---
id: IRQ-refactor-headless-wrapper
recipient: Doer
implementing_actor: Doer
priority: high
---

# Task Overview
Finalize the refactoring of the headless wrapper by migrating improvements from a temporary fix file to the project's utility and cleaning up.

# Scope of Work
- [ ] **Update `src/utils/gemini_cli_headless.py`**:
    - Replace the current implementation with the improved logic found in `final_fix.py` (specifically the content of the `content` variable).
    - **Robust Streaming**: Ensure the `subprocess` execution uses a `readline()` loop to support `stream_output=True` without deadlocks on large outputs.
    - **Policy Handling**: Ensure the policy generation correctly escapes tool names with quotes (e.g., `- name: "*"`) and includes the temporary execution directory in the `allowedPaths` whitelist to prevent permission errors when reading the prompt file.
- [ ] **Verify Imports**:
    - Confirm that `src/create_document_traces.py`, `src/create_master_session.py`, and `src/start_server.py` are correctly importing from `src.utils.gemini_cli_headless`.
    - All three files currently appear to have the correct imports, but verify they function correctly with the updated wrapper.
- [ ] **Cleanup**:
    - Delete the temporary `final_fix.py` file from the project root once the migration is successful.
- [ ] **Validation**:
    - Ensure that running `src/create_document_traces.py` and `src/start_server.py` still works without regressions in communication with the Gemini CLI.

# Out of Scope
- Do not change the public API (function signatures) of `run_gemini_cli_headless` unless absolutely necessary for the fix.
- Do not modify the business logic of KB generation in `create_document_traces.py` beyond import verification.

# Architectural Constraints (Project Knowledge)
- **Playground Usage**: Temporary scripts must stay in `playground/`. `final_fix.py` is currently in the root and must be deleted.
- **Headless Mode**: The wrapper must remain compatible with the `gemini --yolo -o json` execution pattern.

# Definition of Done
- `src/utils/gemini_cli_headless.py` updated with robust streaming and policy fixes.
- `final_fix.py` deleted.
- Import paths verified in dependent scripts.
- No regressions in server startup or document tracing.
