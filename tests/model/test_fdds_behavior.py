import os
import pytest
from src.utils.gemini_client import run_gemini_cli_headless
from tests.integration.utils import run_sync_pipeline

@pytest.mark.model
def test_model_knowledge_recall(test_workspace, mock_env):
    """
    MODEL TEST: Verifies the LLM's ability to recall specific facts 
    from a provided context.
    """
    # Pure model test: No engine pipeline, just direct API call with context
    system_instruction = (
        "Jesteś asystentką FDDS. Korzystaj z poniższej wiedzy:\n"
        "SEKRET: Niebieski ptak lata o północy."
    )

    response = run_gemini_cli_headless(
        prompt="Kiedy lata niebieski ptak?",
        model_id=test_workspace["config"]["answer_model"],
        system_instruction=system_instruction,
        api_key=mock_env
    )
    assert "północy" in response.text.lower()

@pytest.mark.model
def test_model_citation_behavior(test_workspace, mock_env):
    """
    MODEL TEST: Verifies the LLM correctly uses the [doc_N] citation format.
    """
    system_instruction = (
        "ZASADA: Podawaj źródło jako [doc_N].\n\n"
        "<document id=\"doc_1\">\n"
        "  <tresc>Stolicą Polski jest Warszawa.</tresc>\n"
        "</document>"
    )

    response = run_gemini_cli_headless(
        prompt="Jaka jest stolica Polski? Podaj źródło.",
        model_id=test_workspace["config"]["answer_model"],
        system_instruction=system_instruction,
        api_key=mock_env
    )
    assert "[doc_1]" in response.text
