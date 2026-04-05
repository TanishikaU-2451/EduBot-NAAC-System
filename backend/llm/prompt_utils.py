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
    response_mode = _determine_response_mode(user_query)
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
        if role.lower() != "user":
            continue
        content = _truncate_memory_content(str(memory.get("content", "")).strip(), 240)
        if content:
            memory_lines.append(f"[Short-Term {idx}] ({role}) {content}")
    for idx, memory in enumerate(long_term_memories[:4], start=1):
        role = str(memory.get("role", "user"))
        if role.lower() != "user":
            continue
        content = _truncate_memory_content(str(memory.get("content", "")).strip(), 240)
        similarity = memory.get("similarity")
        if content:
            memory_lines.append(f"[Long-Term {idx}] ({role}, sim={similarity}) {content}")

    memory_block = "\n".join(memory_lines) if memory_lines else "No memory context available."
    task_instructions = _build_task_instructions(response_mode)
    output_instructions = _build_output_instructions(response_mode)

    return f"""You are AduBot, a focused NAAC compliance answer bot.
Your job is to answer questions about NAAC requirements and institutional evidence using only the retrieved context.

Primary task:
{task_instructions}

Operating rules:
1) Treat NAAC requirement context as normative criteria when the user is asking for compliance or audit analysis.
2) Treat college report/evidence context as claims or factual evidence to be validated against the user query.
3) Answer only from the retrieved context and conversation memory shown below. Do not invent facts.
4) If context is insufficient, say so plainly and list what is missing.
5) IMPORTANT RULE FOR EVIDENCE LINKS: If the college evidence text mentions "View Document", "Link", or provides a URL/hyperlink, assume the relevant documentary evidence is already attached. Do not penalize missing attachment content when such markers are present.
6) Do not repeat the same condition, evidence, judgment, recommendation, or conclusion in multiple places.
7) If multiple retrieved chunks say the same thing, merge them into one point.
8) Prefer a precise answer over an exhaustive but repetitive answer.
9) If the user asks a narrow factual question, do not turn it into a full institutional audit.
10) For direct factual questions, answer in the shortest correct form possible. If one line is enough, return one line only.
11) AduBot should sound clear, exact, and helpful, not essay-like.

User query:
{user_query}

Detected response mode:
{response_mode}

Retrieved metadata snapshot:
- NAAC: {naac_meta_summary}
- College evidence: {mvsr_meta_summary}

Conversation memory:
{memory_block}

Retrieved context:
{context_block}

{output_instructions}
"""


def parse_compliance_response(
    generated_text: str,
    naac_metadata: List[Dict[str, Any]],
    mvsr_metadata: List[Dict[str, Any]],
    user_query: str = "",
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

    response_mode = _determine_response_mode(user_query)
    comprehensive_audit = _cleanup_comprehensive_audit(comprehensive_audit)
    if response_mode == "direct_answer":
        comprehensive_audit = _normalize_direct_answer(comprehensive_audit, user_query=user_query)

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


def _determine_response_mode(user_query: str) -> str:
    query = (user_query or "").strip().lower()
    audit_keywords = [
        "audit",
        "compliance",
        "gap",
        "checkpoint",
        "condition",
        "criterion",
        "analyze",
        "analysis",
        "evaluate",
        "compare",
        "comparison",
        "difference",
        "differences",
        "weak claim",
        "weakness",
        "weaknesses",
        "remediation",
        "recommendation",
        "satisfied",
    ]
    direct_prefixes = [
        "what",
        "which",
        "who",
        "when",
        "where",
        "why",
        "how",
        "is",
        "are",
        "does",
        "do",
        "can",
        "did",
        "tell me",
        "give me",
        "show me",
        "list",
        "provide",
        "share",
        "mention",
    ]
    direct_phrases = [
        "how many",
        "number of",
        "count of",
        "total number",
        "name of",
        "list of",
        "which courses",
        "which program",
        "what is the number",
    ]

    if any(keyword in query for keyword in audit_keywords):
        return "audit"

    if any(query.startswith(prefix) for prefix in direct_prefixes):
        return "direct_answer"

    if any(phrase in query for phrase in direct_phrases):
        return "direct_answer"

    if re.match(r"^(what|which|who|when|where|why|how|is|are|does|do|can|did)\b", query):
        return "direct_answer"

    if len(query.split()) <= 12 and not query.endswith("."):
        return "direct_answer"

    return "audit"


def _build_task_instructions(response_mode: str) -> str:
    if response_mode == "direct_answer":
        return (
            "Answer the user's exact question using the retrieved document context as AduBot. "
            "If the answer is a single fact, count, name, date, value, or yes/no, return only that answer in one line. "
            "Add one short supporting sentence only if it is truly needed for clarity. "
            "Do not expand a factual question into audit sections, commentary, or long explanations."
        )

    return (
        "Critically verify whether the college/university report satisfies applicable NAAC requirements. "
        "Identify specific mistakes, missing evidence, weak claims, or contradictions, and provide exact "
        "corrective actions. Be thorough but non-repetitive."
    )


def _build_output_instructions(response_mode: str) -> str:
    if response_mode == "direct_answer":
        return """Return output using ONLY these XML tags and in this order.
For narrow factual questions:
- Put only the answer inside <comprehensive_audit> when one line is enough.
- Do NOT add headings such as "Direct Answer", "Supporting Evidence", "Relevant NAAC Checkpoints", or bullets unless the user explicitly asks for a detailed explanation.
- Good example:
<comprehensive_audit>682 courses.</comprehensive_audit>
- If the context is incomplete, use one or two short sentences maximum.
<comprehensive_audit>Short direct answer only, grounded in the retrieved context.</comprehensive_audit>
<status>One of: Fully Supported, Partially Supported, Insufficient Evidence, Processing Error.</status>"""

    return """Audit workflow to follow:
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
<status>One of: Fully Supported, Partially Supported, Gap Identified, Insufficient Evidence, Processing Error.</status>"""


def _truncate_memory_content(text: str, max_length: int) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


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


def _normalize_direct_answer(text: str, user_query: str = "") -> str:
    """Collapse verbose direct-answer outputs into a short bot-style answer."""
    if not text or not text.strip():
        return ""

    extracted = _extract_direct_answer_section(text)
    candidate = extracted or text
    candidate = re.sub(
        r"(?im)^\s*(?:#+\s*)?(?:\d+[.)]\s*)?(direct answer|supporting evidence|missing evidence or uncertainty)\s*$",
        "",
        candidate,
    )

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", candidate) if part.strip()]
    candidate = paragraphs[0] if paragraphs else candidate.strip()
    lines = [line.strip() for line in candidate.splitlines() if line.strip()]
    candidate = " ".join(lines)
    candidate = re.sub(r"^(?:[-*]\s*|\d+[.)]\s*)", "", candidate).strip()
    candidate = re.sub(r"\s+", " ", candidate)

    if len(candidate) > 180:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", candidate) if part.strip()]
        if sentences:
            candidate = sentences[0]

    candidate = _compress_count_style_answer(candidate, user_query)
    return candidate.strip()


def _extract_direct_answer_section(text: str) -> str:
    """Extract the body of a 'Direct Answer' section when the model still emits headings."""
    lines = text.splitlines()
    capture = False
    captured: List[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if re.match(r"^(?:#+\s*)?(?:1[.)]\s*)?direct answer\s*$", line, re.IGNORECASE):
            capture = True
            continue
        if capture and re.match(
            r"^(?:#+\s*)?(?:2[.)]\s*)?(supporting evidence|missing evidence or uncertainty)\s*$",
            line,
            re.IGNORECASE,
        ):
            break
        if capture:
            captured.append(raw_line)

    return "\n".join(captured).strip()


def _compress_count_style_answer(text: str, user_query: str) -> str:
    """Shorten count-style factual answers when the query asked only for a number/value."""
    query = (user_query or "").strip().lower()
    if not any(phrase in query for phrase in ["how many", "number of", "count of", "total number"]):
        return text

    match = re.match(
        r"^(?:the\s+)?(?:number|count|total number)\b.*?\b(?:is|was|are|were)\s+(.+?)(?:\s*\.)?$",
        text.strip(),
        re.IGNORECASE,
    )
    if not match:
        return text

    compressed = match.group(1).strip()
    if not compressed:
        return text

    if len(compressed.split()) > 8:
        return text

    return compressed if compressed.endswith((".", "!", "?")) else f"{compressed}."
