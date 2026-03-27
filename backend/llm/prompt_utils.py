"""Shared prompt helpers for compliance LLM clients."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_compliance_prompt(
    user_query: str,
    naac_context: List[str],
    mvsr_context: List[str],
    naac_metadata: List[Dict[str, Any]],
    mvsr_metadata: List[Dict[str, Any]],
    memory_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Construct the structured NAAC compliance prompt."""
    context_parts: List[str] = []

    if naac_context:
        naac_chunks: List[str] = []
        for idx, text in enumerate(naac_context[:6], start=1):
            naac_chunks.append(f"[NAAC Chunk {idx}]\n{text}")
        context_parts.append("NAAC REQUIREMENT CONTEXT:\n" + "\n\n".join(naac_chunks))

    if mvsr_context:
        mvsr_chunks: List[str] = []
        for idx, text in enumerate(mvsr_context[:8], start=1):
            mvsr_chunks.append(f"[College Evidence Chunk {idx}]\n{text}")
        context_parts.append("COLLEGE REPORT / EVIDENCE CONTEXT:\n" + "\n\n".join(mvsr_chunks))

    context_block = (
        "\n\n".join(context_parts)
        if context_parts
        else "No retrieved context is available. Mark evidence sufficiency as low and avoid unsupported claims."
    )

    naac_meta_summary = ", ".join(
        [f"criterion={m.get('criterion', 'N/A')}, indicator={m.get('indicator', 'N/A')}" for m in naac_metadata[:5]]
    ) or "N/A"
    mvsr_meta_summary = ", ".join(
        [
            f"doc={m.get('document', 'N/A')}, category={m.get('category', 'N/A')}, year={m.get('year', 'N/A')}"
            for m in mvsr_metadata[:5]
        ]
    ) or "N/A"

    short_term_memories = []
    long_term_memories = []
    if memory_context and isinstance(memory_context, dict):
        short_term_memories = memory_context.get("short_term", []) or []
        long_term_memories = memory_context.get("long_term", []) or []

    memory_lines: List[str] = []
    for idx, memory in enumerate(short_term_memories[-6:], start=1):
        role = str(memory.get("role", "user"))
        content = str(memory.get("content", "")).strip()
        if content:
            memory_lines.append(f"[Short-Term {idx}] ({role}) {content}")
    for idx, memory in enumerate(long_term_memories[:4], start=1):
        role = str(memory.get("role", "user"))
        content = str(memory.get("content", "")).strip()
        similarity = memory.get("similarity")
        if content:
            memory_lines.append(f"[Long-Term {idx}] ({role}, sim={similarity}) {content}")

    memory_block = "\n".join(memory_lines) if memory_lines else "No memory context available."

    prompt = f"""You are a NAAC compliance audit assistant.

Primary task:
Verify whether a college/university NAAC report satisfies applicable NAAC requirements.
Identify mistakes, missing evidence, weak claims, or contradictions in the submitted report context.
Provide corrective actions that are specific and practical for accreditation preparation.

Operating rules:
1) Treat NAAC requirement context as normative criteria.
2) Treat college report/evidence context as claims to be validated.
3) Do not assume compliance if evidence is weak or missing.
4) If context is insufficient, explicitly say "Insufficient evidence" and list what must be provided.
5) Prefer precision over verbosity.

User query:
{user_query}

Retrieved metadata snapshot:
- NAAC: {naac_meta_summary}
- College evidence: {mvsr_meta_summary}

Conversation memory:
{memory_block}

Retrieved context:
{context_block}

Audit workflow to follow:
A) Extract the relevant NAAC conditions/checkpoints for this query.
B) Check each condition against available college evidence.
C) Mark each condition as Satisfied / Partially Satisfied / Not Satisfied / Insufficient Evidence.
D) Identify specific mistakes (incorrect, unsupported, missing, contradictory statements).
E) Provide prioritized remediation steps and documentation suggestions.

Return output using ONLY these XML tags and in this order:
<naac_requirement>List concise NAAC conditions/checkpoints being evaluated.</naac_requirement>
<mvsr_evidence>Summarize evidence found in the uploaded college report/evidence relevant to each checkpoint.</mvsr_evidence>
<naac_mapping>Map checkpoints to criterion/indicator and show per-checkpoint status: Satisfied/Partially Satisfied/Not Satisfied/Insufficient Evidence.</naac_mapping>
<compliance_analysis>Explain end-to-end audit judgement, mistakes found, risk level, and confidence caveats.</compliance_analysis>
<status>One of: Fully Supported, Partially Supported, Gap Identified, Insufficient Evidence, Processing Error.</status>
<recommendations>Prioritized corrective actions with what document/proof to add or fix for each gap.</recommendations>
"""

    return prompt


def parse_compliance_response(
    generated_text: str,
    naac_metadata: List[Dict[str, Any]],
    mvsr_metadata: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Parse the XML-like response produced by the LLM."""

    def extract_section(text: str, tag: str) -> str:
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"
        start = text.find(start_tag)
        end = text.find(end_tag)

        if start != -1 and end != -1:
            return text[start + len(start_tag) : end].strip()
        return ""

    naac_requirement = extract_section(generated_text, "naac_requirement")
    mvsr_evidence = extract_section(generated_text, "mvsr_evidence")
    naac_mapping = extract_section(generated_text, "naac_mapping")
    compliance_analysis = extract_section(generated_text, "compliance_analysis")
    status = extract_section(generated_text, "status")
    recommendations = extract_section(generated_text, "recommendations")

    if not compliance_analysis and generated_text.strip():
        compliance_analysis = generated_text.strip()

    parse_warnings: List[str] = []
    if not naac_requirement:
        parse_warnings.append("Missing <naac_requirement> section in LLM output")
    if not mvsr_evidence:
        parse_warnings.append("Missing <mvsr_evidence> section in LLM output")
    if not naac_mapping:
        parse_warnings.append("Missing <naac_mapping> section in LLM output")
    if not status:
        parse_warnings.append("Missing <status> section in LLM output")
    if not recommendations:
        parse_warnings.append("Missing <recommendations> section in LLM output")

    query_processed = len(parse_warnings) == 0

    return {
        "naac_requirement": naac_requirement,
        "mvsr_evidence": mvsr_evidence,
        "naac_mapping": naac_mapping,
        "compliance_analysis": compliance_analysis,
        "status": status,
        "recommendations": recommendations,
        "query_processed": query_processed,
        "parse_warnings": parse_warnings,
        "context_sources": {
            "naac_sources": len(naac_metadata),
            "mvsr_sources": len(mvsr_metadata),
        },
    }


def format_error_response(error_message: str) -> Dict[str, Any]:
    return {
        "naac_requirement": "",
        "mvsr_evidence": "",
        "naac_mapping": "",
        "compliance_analysis": f"Analysis failed: {error_message}",
        "status": "Processing Error",
        "recommendations": "",
        "query_processed": False,
        "error": error_message,
    }
