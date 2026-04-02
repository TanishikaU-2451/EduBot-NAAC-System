"""Shared prompt helpers for compliance LLM clients."""

from __future__ import annotations

import re
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
        for idx, (text, meta) in enumerate(zip(naac_context[:6], naac_metadata[:6]), start=1):
            label = _format_chunk_label(
                "NAAC Chunk",
                idx,
                meta,
                ["criterion", "indicator", "section_header"],
            )
            naac_chunks.append(f"{label}\n{text}")
        context_parts.append("NAAC REQUIREMENT CONTEXT:\n" + "\n\n".join(naac_chunks))

    if mvsr_context:
        mvsr_chunks: List[str] = []
        for idx, (text, meta) in enumerate(zip(mvsr_context[:8], mvsr_metadata[:8]), start=1):
            label = _format_chunk_label(
                "College Evidence Chunk",
                idx,
                meta,
                ["document", "category", "section_header"],
            )
            mvsr_chunks.append(f"{label}\n{text}")
        context_parts.append("COLLEGE REPORT / EVIDENCE CONTEXT:\n" + "\n\n".join(mvsr_chunks))

    context_block = (
        "\n\n".join(context_parts)
        if context_parts
        else "No retrieved context is available. Mark evidence sufficiency as low and avoid unsupported claims."
    )

    naac_meta_summary = _summarize_metadata(
        naac_metadata[:5],
        [("criterion", "criterion"), ("indicator", "indicator"), ("section_header", "section")],
    ) or "N/A"
    mvsr_meta_summary = _summarize_metadata(
        mvsr_metadata[:5],
        [("document", "doc"), ("category", "category"), ("year", "year"), ("section_header", "section")],
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

    prompt = f"""You are an expert, meticulous NAAC compliance audit critic.

Primary task:
Critically verify whether the college/university NAAC report satisfies applicable NAAC requirements.
Identify specific mistakes, missing evidence, weak claims, or contradictions in the submitted report.
Provide exact corrective actions showing what must be added or fixed.
Be thorough but non-repetitive.

Operating rules:
1) Treat NAAC requirement context as normative criteria.
2) Treat college report/evidence context as claims to be validated.
3) Do not assume compliance if evidence is missing, UNLESS rule 5 applies.
4) If context is insufficient, explicitly list what is missing point-by-point.
5) IMPORTANT RULE FOR EVIDENCE LINKS: If the college evidence text mentions "View Document", "Link", or provides a URL/hyperlink, assume the relevant documentary evidence is already attached. Do not penalize missing attachment content when such markers are present.
6) Do not repeat the same condition, evidence, judgment, or recommendation in multiple places.
7) If multiple NAAC chunks express the same rule, merge them into one checkpoint.
8) If two findings have the same evidence, same judgment, and same recommendation, combine them into a single finding.
9) Prefer 4-6 unique findings over many repetitive findings.

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
B) Merge overlapping or duplicate conditions into one checkpoint before writing the answer.
C) Check each unique checkpoint against available college evidence.
D) Mark each checkpoint as Satisfied / Partially Satisfied / Not Satisfied / Insufficient Evidence.
E) Identify specific mistakes, unsupported claims, gaps, or contradictions.
F) Provide prioritized remediation steps with exact additions needed.
G) Remove duplicate bullets, duplicate paragraphs, and duplicate conclusions before finalizing the answer.

Return output using ONLY these XML tags and in this order. Write markdown inside the first tag using these exact sections:
1. Relevant NAAC Checkpoints
2. Audit Findings
3. Specific Weak Claims or Gaps
4. Prioritized Remediation Steps
5. Missing or Insufficient Evidence
6. Conclusion
In "Audit Findings", merge duplicate conditions as a combined finding such as "Conditions 1-3" when the evidence and judgment are the same.
<comprehensive_audit>Single, unified audit. No repeated headings, no repeated bullets, no repeated recommendations, no repeated conclusion sentences.</comprehensive_audit>
<status>One of: Fully Supported, Partially Supported, Gap Identified, Insufficient Evidence, Processing Error.</status>
"""

    try:
        import os

        debug_path = os.path.join(os.getcwd(), "LLM_PROMPT_DEBUG.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write("=" * 20 + " SYSTEM PROMPT " + "=" * 20 + "\n")
            f.write(f"Query: {user_query}\n")
            f.write(f"NAAC Chunks: {len(naac_context)}\n")
            f.write(f"MVSR Chunks: {len(mvsr_context)}\n")
            f.write("=" * 20 + " ACTUAL START " + "=" * 20 + "\n\n")
            f.write(prompt)
    except Exception as e:
        print(f"Failed to write prompt debug log: {e}")

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

    comprehensive_audit = extract_section(generated_text, "comprehensive_audit")
    status = extract_section(generated_text, "status")

    if not comprehensive_audit and generated_text.strip():
        comprehensive_audit = generated_text.replace("<status>", "").replace("</status>", "").replace(status, "").strip()

    comprehensive_audit = _cleanup_comprehensive_audit(comprehensive_audit)

    parse_warnings: List[str] = []
    if not comprehensive_audit:
        parse_warnings.append("Missing <comprehensive_audit> section in LLM output")
    if not status:
        parse_warnings.append("Missing <status> section in LLM output")

    query_processed = len(parse_warnings) == 0

    return {
        "naac_requirement": "",
        "mvsr_evidence": "",
        "naac_mapping": "",
        "compliance_analysis": comprehensive_audit,
        "status": status,
        "recommendations": "",
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


def _format_chunk_label(
    prefix: str,
    index: int,
    metadata: Dict[str, Any],
    fields: List[str],
) -> str:
    parts: List[str] = []
    for field in fields:
        value = str(metadata.get(field, "") or "").strip()
        if not value or value.upper() == "N/A":
            continue
        parts.append(f"{field.replace('_', ' ')}={value}")
    suffix = f" | {' | '.join(parts)}" if parts else ""
    return f"[{prefix} {index}{suffix}]"


def _summarize_metadata(
    rows: List[Dict[str, Any]],
    fields: List[tuple[str, str]],
) -> str:
    seen = set()
    summary_parts: List[str] = []

    for row in rows:
        parts: List[str] = []
        for key, label in fields:
            value = str(row.get(key, "") or "").strip()
            if not value or value.upper() == "N/A" or value.lower() == "none":
                continue
            parts.append(f"{label}={value}")

        if not parts:
            continue

        entry = ", ".join(parts)
        if entry in seen:
            continue

        seen.add(entry)
        summary_parts.append(entry)

    return " | ".join(summary_parts)


def _cleanup_comprehensive_audit(text: str) -> str:
    """Remove duplicated lines/blocks and merge repeated condition sections."""
    if not text or not text.strip():
        return ""

    blocks = [block.strip() for block in re.split(r"\n\s*\n+", text.strip()) if block.strip()]
    merged_blocks: List[str] = []
    seen_block_signatures = set()
    condition_signature_to_index: Dict[str, int] = {}

    for raw_block in blocks:
        block = _deduplicate_block_lines(raw_block)
        if not block:
            continue

        condition_match = _match_condition_header(block)
        if condition_match:
            condition_number, condition_title, body = condition_match
            signature = _normalize_signature(body or condition_title or block)
            existing_index = condition_signature_to_index.get(signature)

            if existing_index is not None:
                merged_blocks[existing_index] = _merge_condition_number(
                    merged_blocks[existing_index],
                    condition_number,
                )
                continue

            condition_signature_to_index[signature] = len(merged_blocks)

        block_signature = _normalize_signature(block)
        if block_signature in seen_block_signatures:
            continue

        seen_block_signatures.add(block_signature)
        merged_blocks.append(block)

    return "\n\n".join(merged_blocks).strip()


def _deduplicate_block_lines(block: str) -> str:
    lines = [line.rstrip() for line in block.splitlines()]
    deduped: List[str] = []
    seen_signatures = set()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if deduped and deduped[-1] == "":
                continue
            deduped.append("")
            continue

        signature = _normalize_signature(stripped)
        if signature in seen_signatures:
            continue

        seen_signatures.add(signature)
        deduped.append(stripped)

    while deduped and deduped[-1] == "":
        deduped.pop()

    return "\n".join(deduped).strip()


def _match_condition_header(block: str) -> Optional[tuple[str, str, str]]:
    lines = [line for line in block.splitlines() if line.strip()]
    if not lines:
        return None

    match = re.match(r"^NAAC Condition\s+(\d+)\s*:\s*(.*)$", lines[0], re.IGNORECASE)
    if not match:
        return None

    return match.group(1), match.group(2).strip(), "\n".join(lines[1:]).strip()


def _merge_condition_number(existing_block: str, new_number: str) -> str:
    lines = existing_block.splitlines()
    if not lines:
        return existing_block

    header_match = re.match(r"^NAAC Condition(?:s)?\s+([0-9,\s]+)\s*:\s*(.*)$", lines[0], re.IGNORECASE)
    if not header_match:
        return existing_block

    existing_numbers = [part.strip() for part in header_match.group(1).split(",") if part.strip()]
    if new_number not in existing_numbers:
        existing_numbers.append(new_number)

    existing_numbers = sorted(existing_numbers, key=lambda value: int(value))
    label = "NAAC Condition" if len(existing_numbers) == 1 else "NAAC Conditions"
    lines[0] = f"{label} {', '.join(existing_numbers)}: {header_match.group(2).strip()}"
    return "\n".join(lines)


def _normalize_signature(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    normalized = re.sub(r"[^a-z0-9 ]+", "", normalized)
    return normalized
