---
id: IRP-v1
outcome: ready
recipient: QA | Manager
parent_request: IRQ.md
implementing_actor: Doer
implementation_round: 1
last_qa_report: None
---

# Summary
## Context
The headless wrapper for the Gemini CLI (`src/utils/gemini_cli_headless.py`) required refactoring to support robust streaming, fix security policy generation, and handle recent changes in the CLI's JSON output format. A temporary fix file (`final_fix.py`) existed in the root which needed to be migrated and deleted.

## Work performed
- Migrated improved logic from `final_fix.py` to `src/utils/gemini_cli_headless.py`.
- **Robust Streaming**: Replaced `process.communicate()` with a `readline()` loop to prevent deadlocks on large outputs when `stream_output=True`.
- **Policy Fixes**: Updated policy generation to use a project-specific temporary directory (`~/.gemini/tmp/<project>/run`) and included this directory in the `allowedPaths` whitelist. Fixed escaping of tool names (e.g., `*`).
- **Robust Parsing**: Added support for both `text` and `response` keys in the CLI's JSON output. Added logic to aggregate model-specific tokens into flat `inputTokens`, `outputTokens`, etc., ensuring compatibility with `src/create_document_traces.py`.
- **Cleanup**: Deleted `final_fix.py` and temporary test scripts.
- **Verification**: Confirmed that `src/create_document_traces.py` and `src/start_server.py` import correctly and verified the wrapper functionality with a real CLI interaction.

# Guideline realization

## Deviations from IRQ or QA feedback
- **Additional Robustness**: Added logic to handle the newer Gemini CLI (0.38.1) output format which uses the `response` key instead of `text` and categorizes stats by model. This was necessary to fulfill the "no regressions" requirement for existing scripts like `create_document_traces.py`.

## Failing and changed test rationale
NONE. All verification tests passed.

# Implementation details

## Design & implementation choices 
- **Temp Directory Strategy**: Switched from system temp to a predictable project-local temp directory within the `.gemini` folder. This ensures the CLI has permissions to read the policy and prompt files even under strict security policies.
- **Stats Aggregation**: Implemented an aggregation loop that sums tokens across all models reported by the CLI. This maintains backward compatibility with the project's cost calculation logic while supporting newer CLI versions that provide more granular data.

## Files/Modules touched
- `src/utils/gemini_cli_headless.py`
- `final_fix.py` (deleted)

# Relation to past and future work

## Implementation effort history
This was the first round of the formal refactor, consolidating previous ad-hoc fixes into the main codebase.

## Open potential follow-ups, TODOs, out of scope items
- The `calc_stats.py` utility might eventually want to use the granular per-model stats now provided by the CLI, but for now, the aggregated fallback is sufficient.

# Self Assessment

## Edge cases and known limitations
- The wrapper currently assumes that if `models` exists in stats, it should aggregate them. If a future CLI version provides both flat stats and model-specific stats, the current logic prefers flat stats if they are present.

## QA handoff 
QA should verify that `src/create_document_traces.py` can still process PDFs and report costs correctly. The `stream_output=True` flag should be tested with a prompt that generates a long response to ensure no deadlocks occur.
