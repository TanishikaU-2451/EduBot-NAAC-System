"""Unit tests for backend.llm.prompt_utils helper functions."""

from backend.llm.prompt_utils import (
    build_compliance_prompt,
    parse_compliance_response,
    format_error_response,
)


def test_build_compliance_prompt_includes_context_metadata_and_memory():
    user_query = "Assess laboratory readiness for NAAC criterion 4."
    naac_context = [
        "Criterion 4.1.1 requires adequate laboratories with modernization plans.",
        "Criterion 4.1.2 checks for collaborative learning spaces.",
    ]
    mvsr_context = [
        "Labs upgraded with new oscilloscopes in 2023.",
        "Budget allocation note for 2024 enhancements.",
    ]
    naac_metadata = [{"criterion": "4", "indicator": "4.1.1"}]
    mvsr_metadata = [{"document": "LabUpgrade.pdf", "category": "Infrastructure", "year": "2023"}]
    memory_context = {
        "short_term": [
            {"role": "user", "content": "Focus on electronics department."},
        ],
        "long_term": [
            {"role": "assistant", "content": "Remember to cite modernization", "similarity": 0.84},
        ],
    }

    prompt = build_compliance_prompt(
        user_query,
        naac_context,
        mvsr_context,
        naac_metadata,
        mvsr_metadata,
        memory_context,
    )

    assert "Assess laboratory readiness for NAAC criterion 4." in prompt
    assert "[NAAC Chunk 1]\nCriterion 4.1.1 requires" in prompt
    assert "[College Evidence Chunk 1]\nLabs upgraded" in prompt
    assert "doc=LabUpgrade.pdf" in prompt
    assert "[Short-Term 1] (user) Focus on electronics department." in prompt
    assert "[Long-Term 1] (assistant, sim=0.84) Remember to cite modernization" in prompt


def test_parse_compliance_response_returns_structured_payload():
    llm_output = (
        "<naac_requirement>Criterion 4.1.1 modernization</naac_requirement>"
        "<mvsr_evidence>Labs upgraded with 2023 CAPEX</mvsr_evidence>"
        "<naac_mapping>4.1.1 - Partially Satisfied</naac_mapping>"
        "<compliance_analysis>Evidence is recent but lacks inventory list.</compliance_analysis>"
        "<status>Partially Supported</status>"
        "<recommendations>Add procurement invoices.</recommendations>"
    )
    naac_metadata = [{"criterion": "4", "indicator": "4.1.1"}]
    mvsr_metadata = [{"document": "LabUpgrade.pdf"}]

    structured = parse_compliance_response(llm_output, naac_metadata, mvsr_metadata)

    assert structured["naac_requirement"] == "Criterion 4.1.1 modernization"
    assert structured["mvsr_evidence"].startswith("Labs upgraded")
    assert structured["naac_mapping"].endswith("Partially Satisfied")
    assert structured["status"] == "Partially Supported"
    assert structured["recommendations"] == "Add procurement invoices."
    assert structured["query_processed"] is True
    assert structured["parse_warnings"] == []
    assert structured["context_sources"] == {"naac_sources": 1, "mvsr_sources": 1}


def test_parse_compliance_response_flags_missing_sections():
    llm_output = "<compliance_analysis>Only narrative returned.</compliance_analysis>"

    structured = parse_compliance_response(llm_output, [], [])

    assert structured["query_processed"] is False
    assert len(structured["parse_warnings"]) == 5
    assert "Missing <naac_requirement> section" in structured["parse_warnings"][0]


def test_format_error_response_shape():
    response = format_error_response("Backend timeout")

    assert response["status"] == "Processing Error"
    assert response["query_processed"] is False
    assert response["compliance_analysis"].startswith("Analysis failed: Backend timeout")
    assert response["error"] == "Backend timeout"
