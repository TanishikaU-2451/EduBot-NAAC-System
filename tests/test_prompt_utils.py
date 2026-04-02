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
    naac_metadata = [{"criterion": "4", "indicator": "4.1.1", "section_header": "Lab Readiness"}]
    mvsr_metadata = [
        {
            "document": "LabUpgrade.pdf",
            "category": "Infrastructure",
            "year": "2023",
            "section_header": "Equipment Upgrade",
        }
    ]
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
    assert "[NAAC Chunk 1 | criterion=4 | indicator=4.1.1 | section header=Lab Readiness]" in prompt
    assert "[College Evidence Chunk 1 | document=LabUpgrade.pdf | category=Infrastructure | section header=Equipment Upgrade]" in prompt
    assert "doc=LabUpgrade.pdf, category=Infrastructure, year=2023, section=Equipment Upgrade" in prompt
    assert "[Short-Term 1] (user) Focus on electronics department." in prompt
    assert "[Long-Term 1] (assistant, sim=0.84) Remember to cite modernization" in prompt
    assert "Do not repeat the same condition, evidence, judgment, or recommendation" in prompt


def test_parse_compliance_response_returns_structured_payload():
    llm_output = (
        "<comprehensive_audit>Evidence is recent but lacks inventory list.</comprehensive_audit>"
        "<status>Partially Supported</status>"
    )
    naac_metadata = [{"criterion": "4", "indicator": "4.1.1"}]
    mvsr_metadata = [{"document": "LabUpgrade.pdf"}]

    structured = parse_compliance_response(llm_output, naac_metadata, mvsr_metadata)

    assert structured["naac_requirement"] == ""
    assert structured["mvsr_evidence"] == ""
    assert structured["naac_mapping"] == ""
    assert structured["compliance_analysis"] == "Evidence is recent but lacks inventory list."
    assert structured["status"] == "Partially Supported"
    assert structured["recommendations"] == ""
    assert structured["query_processed"] is True
    assert structured["parse_warnings"] == []
    assert structured["context_sources"] == {"naac_sources": 1, "mvsr_sources": 1}


def test_parse_compliance_response_flags_missing_sections():
    llm_output = "<compliance_analysis>Only narrative returned.</compliance_analysis>"

    structured = parse_compliance_response(llm_output, [], [])

    assert structured["query_processed"] is False
    assert len(structured["parse_warnings"]) == 1
    assert "Missing <status> section" in structured["parse_warnings"][0]


def test_parse_compliance_response_deduplicates_repeated_condition_blocks():
    llm_output = (
        "<comprehensive_audit>"
        "NAAC Condition 1: IQAC Guidelines\n"
        "College Evidence: IQAC exists.\n"
        "Judgment: Satisfied\n"
        "Recommendation: None\n\n"
        "NAAC Condition 2: Alternate wording\n"
        "College Evidence: IQAC exists.\n"
        "Judgment: Satisfied\n"
        "Recommendation: None\n\n"
        "Specific Weak Claims or Gaps\n"
        "- Missing detailed outcome mapping.\n"
        "- Missing detailed outcome mapping.\n"
        "</comprehensive_audit>"
        "<status>Gap Identified</status>"
    )

    structured = parse_compliance_response(llm_output, [], [])

    assert "NAAC Conditions 1, 2:" in structured["compliance_analysis"]
    assert structured["compliance_analysis"].count("Recommendation: None") == 1
    assert structured["compliance_analysis"].count("Missing detailed outcome mapping.") == 1


def test_format_error_response_shape():
    response = format_error_response("Backend timeout")

    assert response["status"] == "Processing Error"
    assert response["query_processed"] is False
    assert response["compliance_analysis"].startswith("Analysis failed: Backend timeout")
    assert response["error"] == "Backend timeout"
