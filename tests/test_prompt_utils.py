from backend.llm.prompt_utils import parse_compliance_response


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

    assert parsed["compliance_analysis"] == (
        "The number of courses offered by MVSR across all programs during the last five years is 682 courses."
    )
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
