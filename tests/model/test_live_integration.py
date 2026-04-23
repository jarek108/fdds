import os
import json
import pytest
import shutil
from gemini_cli_headless import run_gemini_cli_headless
from tests.integration.utils import run_sync_pipeline

@pytest.mark.model
def test_end_to_end_cognition_with_real_instructions(test_workspace, mock_env):
    """
    MODEL TEST (E2E): Verifies that the model follows real production rules 
    (Polish language, [doc_N] citations) when fed a real compiled instruction set.
    """
    # 1. Setup: Copy real system instruction to test workspace
    real_instruction_src = os.path.join(os.path.dirname(__file__), "../../config/system_instruction.md")
    instruction_dst = test_workspace["paths"]["base_instruction_file"]
    os.makedirs(os.path.dirname(instruction_dst), exist_ok=True)
    shutil.copy2(real_instruction_src, instruction_dst)

    # 2. Setup: Add a mock document trace
    trace_dir = os.path.join(test_workspace["traces"], f"{test_workspace['config']['trace_length']}_{test_workspace['config']['doc_tracing_model']}")
    os.makedirs(trace_dir, exist_ok=True)
    
    # We need a 'real' hash or at least match the pattern
    mock_hash = "fakehash123"
    pdf_path = os.path.join(test_workspace["docs"], "secret_report.pdf")
    with open(pdf_path, "w") as f: f.write("dummy")
    
    # Manually create the hash file so create_master_session finds it
    with open(pdf_path + ".hash", "w") as f: f.write(mock_hash)

    mock_trace = {
        "source_hash": mock_hash,
        "original_filename": "secret_report.pdf",
        "tytul": "Tajny Raport FDDS",
        "zawartosc": "Najważniejsza zasada bezpieczeństwa to: Nigdy nie otwieraj drzwi nieznajomym."
    }
    with open(os.path.join(trace_dir, f"{mock_hash}.json"), "w", encoding="utf-8") as f:
        json.dump(mock_trace, f)

    # 3. Action: Run the engine pipeline to compile EVERYTHING (Real rules + Mock docs)
    run_sync_pipeline(test_workspace)

    # 4. Action: Load the compiled system instruction
    master_instruction_path = test_workspace["paths"]["master_system_instruction"]
    with open(master_instruction_path, "r", encoding="utf-8") as f:
        compiled_instructions = f.read()

    # 5. MODEL EVAL: Query the AI using the real compiled logic
    response = run_gemini_cli_headless(
        prompt="Jaka jest najważniejsza zasada bezpieczeństwa według raportu?",
        model_id=test_workspace["config"]["answer_model"],
        system_instruction_override=compiled_instructions,
        api_key=mock_env,
        allowed_tools=[],
        isolate_from_hierarchical_pollution=True
    )

    print(f"E2E Response: {response.text}")

    # 6. Asserts
    # Is it in Polish?
    assert any(word in response.text.lower() for word in ["zasada", "bezpieczeństwa", "drzwi", "nieznajomym"]), "Model failed to answer in Polish"
    # Does it use citations?
    assert "[doc_1]" in response.text, "Model failed to use the [doc_N] citation format using real instructions"
    # Is it accurate?
    assert "nieznajomym" in response.text.lower(), "Model failed to extract the correct fact"
