---
id: QAR-EXTRACT-TRACE-RL
recipient: QA
parent_request: IRQ.md
---

# Validation Strategy
Verify the presence, format, and quality of the extracted Polish trace against the specified requirements.

# Feature-Specific Validation Criteria
- [ ] File Existence: Confirm `data/traces/contrastive_learning_rl_trace.txt` exists.
- [ ] Language: Verify the text is written in high-quality technical Polish.
- [ ] Format: Check for the presence of "Tytuł: " and "Treść: " headers.
- [ ] Length: Estimate token count (should be roughly 400 tokens).
- [ ] Content: Ensure the summary focuses on facts and technical guidelines from the RL paper.
- [ ] Context: Check for the inclusion of FDDS help lines if relevant.

# Specific Risk Areas
- [ ] Accuracy: Ensure the summary accurately reflects the paper "Contrastive Learning as Goal-Conditioned RL".
- [ ] Encoding: Ensure no character corruption in the Polish text.

# Mandatory Rituals
- Check `playground/` for any leftover temporary files and ensure they don't pollute the project root.
