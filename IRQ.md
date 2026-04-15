---
id: IRQ-EXTRACT-TRACE-RL
recipient: Doer
implementing_actor: Doer
priority: high
---

# Task Overview
Extract a detailed Polish technical summary (trace) from the document 'Contrastive Learning as Goal-Conditioned RL.pdf' and save it as a text file in the project's data directory.

# Scope of Work
- [ ] Read and process 'data/documents/Materiały edu/Contrastive Learning as Goal-Conditioned RL.pdf'.
- [ ] Generate a summary in Polish focusing on technical facts and guidelines.
- [ ] Ensure the summary is approximately 400 tokens in length.
- [ ] Format the output exactly as:
    Tytuł: [Polish Title]
    Treść: [Polish Summary Content]
- [ ] Include FDDS-specific help lines if applicable to the context.
- [ ] Save the result to `data/traces/contrastive_learning_rl_trace.txt`.

# Out of Scope
- [ ] Do not modify any existing source code in `src/`.
- [ ] Do not create permanent script files outside of the `playground/` directory.
- [ ] Do not translate the entire document; only extract a summary.

# Architectural Constraints (Project Knowledge)
- Use `playground/` for any temporary extraction scripts if needed.
- Adhere to the `Tytuł: ... Treść: ...` formatting convention.

# Definition of Done
- A text file `data/traces/contrastive_learning_rl_trace.txt` exists.
- The content is in Polish, formatted correctly, and satisfies the token length requirement (~400 tokens).
- The summary captures the technical essence of the source PDF.
