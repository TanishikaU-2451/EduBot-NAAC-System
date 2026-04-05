from apps.backend.llm.prompt_utils import build_compliance_prompt, parse_compliance_response


def test_parse_direct_answer_keeps_one_line_answer():
    generated = """
<comprehensive_audit>
1. Direct Answer
The number of courses offered by MVSR across all programs during the last five years is 682 courses.

2. Supporting Evidence
The SSR mentions the verified count as 682.
</comprehensive_audit>
<status>Fully Supported</status>
"""

    parsed = parse_compliance_response(
        generated,
        naac_metadata=[],
        mvsr_metadata=[],
        user_query="tell me number of courses offered by mvsr across all programs during the last five years",
    )

    assert parsed["compliance_analysis"] == "682 courses."
    assert parsed["status"] == "Fully Supported"


def test_parse_audit_response_keeps_audit_structure():
    generated = """
<comprehensive_audit>
1. Relevant NAAC Checkpoints
Checkpoint A

2. Audit Findings
Finding A
</comprehensive_audit>
<status>Gap Identified</status>
"""

    parsed = parse_compliance_response(
        generated,
        naac_metadata=[],
        mvsr_metadata=[],
        user_query="compare the mvsr file with the naac file and identify the gaps",
    )

    assert "Relevant NAAC Checkpoints" in parsed["compliance_analysis"]
    assert "Audit Findings" in parsed["compliance_analysis"]
    assert parsed["status"] == "Gap Identified"


def test_audit_prompt_demands_metric_matrix_and_source_citations():
    prompt = build_compliance_prompt(
        user_query="identify naac gaps in ssr with dvv style findings",
        naac_context=[
            "Metric 6.5.2 requires quality assurance initiatives to be documented year-wise with outcomes.",
        ],
        mvsr_context=[
            "SSR claims IQAC completed 5 quality audits, but uploaded minutes show only 2 records for 2021-2023.",
        ],
        naac_metadata=[
            {
                "criterion": "6",
                "indicator": "6.5.2",
                "section_header": "Quality Assurance",
                "source_file": "naac_manual.pdf",
                "start_page": 152,
                "end_page": 153,
            }
        ],
        mvsr_metadata=[
            {
                "criterion": "6",
                "section_header": "IQAC Minutes",
                "document": "SSR 2023",
                "source_file": "mvsr_ssr.pdf",
                "start_page": 211,
                "end_page": 214,
            }
        ],
        memory_context=None,
    )

    assert "Criterion-wise Metric Gap Matrix" in prompt
    assert "Claim vs Retrieved Evidence vs DVV Risk" in prompt
    assert "[NAAC-1]" in prompt
    assert "[MVSR-1]" in prompt
    assert "Metric ID not found in retrieved context" in prompt


def test_parse_statement_count_query_returns_single_line_value():
    generated = """
<comprehensive_audit>
The institution offered a total of 682 courses across all programs during the last five years based on the SSR dataset.
</comprehensive_audit>
<status>Fully Supported</status>
"""

    parsed = parse_compliance_response(
        generated,
        naac_metadata=[],
        mvsr_metadata=[],
        user_query="Number of courses offered by mvsr across all programs during the last five years",
    )

    assert parsed["compliance_analysis"] == "682 courses."
    assert parsed["status"] == "Fully Supported"
