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

    source_extract_block = _build_source_extract_block(
        naac_context=naac_context,
        naac_metadata=naac_metadata,
        mvsr_context=mvsr_context,
        mvsr_metadata=mvsr_metadata,
    )

    naac_metric_ids = _collect_metric_ids(naac_context, naac_metadata)
    mvsr_metric_ids = _collect_metric_ids(mvsr_context, mvsr_metadata)
    naac_metric_snapshot = ", ".join(naac_metric_ids[:20]) if naac_metric_ids else "None detected"
    mvsr_metric_snapshot = ", ".join(mvsr_metric_ids[:20]) if mvsr_metric_ids else "None detected"

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
12) In audit mode, every major finding must include at least one source citation tag like [NAAC-2] or [MVSR-4].
13) In audit mode, map findings to criterion and metric IDs whenever present (for example 2.3.1, 6.5.2). If unavailable, write "Metric ID not found in retrieved context".
14) In audit mode, quantify evidence gaps whenever possible (counts, percentages, years, accepted vs rejected values).

User query:
{user_query}

Detected response mode:
{response_mode}

Retrieved metadata snapshot:
- NAAC: {naac_meta_summary}
- College evidence: {mvsr_meta_summary}

Retrieved metric snapshot:
- NAAC metric IDs: {naac_metric_snapshot}
- College evidence metric IDs: {mvsr_metric_snapshot}

Conversation memory:
{memory_block}

Retrieved context:
{context_block}

Source extracts for citation (use these IDs in your answer):
{source_extract_block}

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
    strong_audit_keywords = [
        "audit",
        "compliance analysis",
        "compliance gap",
        "gap",
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
        "dvv",
        "scoring",
        "score risk",
        "eligibility",
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
    statement_direct_prefixes = [
        "number of",
        "count of",
        "total number",
        "list of",
        "name of",
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

    if any(keyword in query for keyword in strong_audit_keywords):
        return "audit"

    if any(query.startswith(prefix) for prefix in direct_prefixes):
        return "direct_answer"

    if any(query.startswith(prefix) for prefix in statement_direct_prefixes):
        return "direct_answer"

    if any(phrase in query for phrase in direct_phrases):
        return "direct_answer"

    if re.match(r"^(what|which|who|when|where|why|how|is|are|does|do|can|did)\b", query):
        return "direct_answer"

    if _looks_like_short_factual_statement(query):
        return "direct_answer"

    if len(query.split()) <= 12 and not query.endswith("."):
        return "direct_answer"

    return "audit"


def _looks_like_short_factual_statement(query: str) -> bool:
    """Detect compact factual prompts that should return short direct answers."""
    words = [word for word in re.findall(r"[a-z0-9%]+", query) if word]
    if not words:
        return False

    if len(words) > 16:
        return False

    factual_markers = {
        "number",
        "count",
        "total",
        "list",
        "name",
        "courses",
        "course",
        "students",
        "student",
        "faculty",
        "program",
        "programs",
        "year",
        "years",
        "percentage",
        "percent",
        "ratio",
    }

    audit_markers = {
        "gap",
        "audit",
        "analysis",
        "analyze",
        "evaluate",
        "compare",
        "comparison",
        "remediation",
        "weakness",
        "dvv",
        "risk",
        "eligibility",
        "compliance",
    }

    if any(marker in query for marker in audit_markers):
        return False

    return any(marker in words for marker in factual_markers)


def _build_task_instructions(response_mode: str) -> str:
    if response_mode == "direct_answer":
        return (
            "Answer the user's exact question using the retrieved document context as AduBot. "
            "If the answer is a single fact, count, name, date, value, or yes/no, return only that answer in one line. "
            "Add one short supporting sentence only if it is truly needed for clarity. "
            "Do not expand a factual question into audit sections, commentary, or long explanations."
        )

    return (
        "Critically verify whether the college or university report satisfies applicable NAAC requirements using a metric-based audit style. "
        "Map every material gap to criterion and metric IDs, compare SSR claims vs retrieved accepted evidence, explain likely DVV-style downgrades, "
        "and provide exact corrective actions with evidence format, owner role, and timeline. Be thorough but non-repetitive."
    )


def _build_output_instructions(response_mode: str) -> str:
    if response_mode == "direct_answer":
        return """Return output using ONLY these XML tags and in this order.
For narrow factual questions:
- Put only the answer inside <comprehensive_audit> when one line is enough.
- Return exactly one line when the answer is a single value (for example "682 courses.").
- Do not add bullets, headings, numbering, or section labels.
- Do NOT add headings such as "Direct Answer", "Supporting Evidence", "Relevant NAAC Checkpoints", or bullets unless the user explicitly asks for a detailed explanation.
- Good example:
<comprehensive_audit>682 courses.</comprehensive_audit>
- If the context is incomplete, use one or two short sentences maximum.
<comprehensive_audit>Short direct answer only, grounded in the retrieved context.</comprehensive_audit>
<status>One of: Fully Supported, Partially Supported, Insufficient Evidence, Processing Error.</status>"""

    return """Audit workflow to follow:
A) Extract relevant NAAC checkpoints and metric IDs from the retrieved context.
B) Build a metric-wise matrix with NAAC expectation, SSR claim, retrieved evidence, and gap status.
C) For each row, cite at least one source ID like [NAAC-1] or [MVSR-3].
D) Explain claim-vs-accepted mismatch in DVV style: what was claimed, what is supported, what is rejected or unsupported.
E) Quantify every possible deficiency (counts, percentages, number of years, number of documents, pending submissions).
F) Name missing document artifacts explicitly (for example signed IQAC minutes, LMS logs, AQAR year-wise files, audit reports, utilization certificates).
G) Provide corrective actions that are executable: owner role, exact evidence format, timeline, and acceptance check.
H) Remove duplicate bullets, duplicate paragraphs, and duplicate conclusions before finalizing.

Return output using ONLY these XML tags and in this order. Write markdown inside the first tag using these exact sections:
1. Criterion-wise Metric Gap Matrix
2. Metric-wise Findings (Claim vs Retrieved Evidence vs DVV Risk)
3. Document-Level Missing Evidence
4. Prioritized Corrective Action Plan
5. Eligibility and Scoring Risk Summary
6. Conclusion

Formatting rules inside <comprehensive_audit>:
- In section 1, include a markdown table with columns:
    Criterion | Metric ID | NAAC Expectation (quoted) | SSR Claim (quoted) | Retrieved Evidence (quoted) | Gap Status | Citation
- Use exact quote snippets from retrieved text for NAAC expectation and SSR claim whenever possible.
- If a metric ID is not present in retrieved context, write "Metric ID not found in retrieved context".
- In section 4, each action must include: Owner, Evidence to produce, Format, Deadline.
- Keep content specific and extracted, not generic.

<comprehensive_audit>Single, unified metric-based audit with mandatory citations and actionable remediation.</comprehensive_audit>
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


def _build_source_extract_block(
    naac_context: List[str],
    naac_metadata: List[Dict[str, Any]],
    mvsr_context: List[str],
    mvsr_metadata: List[Dict[str, Any]],
) -> str:
    """Build a citation-ready source extract list to reduce generic responses."""
    lines: List[str] = []

    for idx, (text, meta) in enumerate(zip(naac_context[:6], naac_metadata[:6]), start=1):
        descriptor = _build_extract_descriptor(meta)
        excerpt = _truncate_extract(text, max_length=260)
        lines.append(f"[NAAC-{idx}] {descriptor}\nExcerpt: \"{excerpt}\"")

    for idx, (text, meta) in enumerate(zip(mvsr_context[:8], mvsr_metadata[:8]), start=1):
        descriptor = _build_extract_descriptor(meta)
        excerpt = _truncate_extract(text, max_length=260)
        lines.append(f"[MVSR-{idx}] {descriptor}\nExcerpt: \"{excerpt}\"")

    if not lines:
        return "No source extracts available."
    return "\n\n".join(lines)


def _build_extract_descriptor(metadata: Dict[str, Any]) -> str:
    criterion = str(metadata.get("criterion", "") or "").strip()
    indicator = str(metadata.get("indicator", "") or "").strip()
    section = str(metadata.get("section_header", "") or "").strip()
    source_file = str(metadata.get("source_file") or metadata.get("file_name") or metadata.get("document") or metadata.get("document_title") or "").strip()
    start_page = metadata.get("start_page")
    end_page = metadata.get("end_page")

    parts: List[str] = []
    if criterion:
        parts.append(f"criterion={criterion}")
    if indicator:
        parts.append(f"metric={indicator}")
    if section:
        parts.append(f"section={section}")
    if source_file:
        parts.append(f"source={source_file}")

    if start_page not in (None, "", "N/A"):
        if end_page not in (None, "", "N/A") and end_page != start_page:
            parts.append(f"pages={start_page}-{end_page}")
        else:
            parts.append(f"page={start_page}")

    return " | ".join(parts) if parts else "no metadata"


def _truncate_extract(text: str, max_length: int = 260) -> str:
    normalized = re.sub(r"\s+", " ", (text or "")).strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def _collect_metric_ids(context_rows: List[str], metadata_rows: List[Dict[str, Any]]) -> List[str]:
    """Collect criterion or metric IDs from both metadata and raw chunk text."""
    metric_ids = set()

    for metadata in metadata_rows:
        indicator = str(metadata.get("indicator", "") or "").strip()
        if indicator:
            for metric_id in _extract_metric_ids(indicator):
                metric_ids.add(metric_id)

        criterion = str(metadata.get("criterion", "") or "").strip()
        if criterion and re.fullmatch(r"[1-7]", criterion):
            metric_ids.add(f"{criterion}.x.x")

    for row in context_rows:
        for metric_id in _extract_metric_ids(row):
            metric_ids.add(metric_id)

    return sorted(metric_ids, key=_metric_sort_key)


def _extract_metric_ids(text: str) -> List[str]:
    pattern = re.compile(r"\b[1-7]\.\d(?:\.\d)?\b")
    return sorted(set(pattern.findall(text or "")), key=_metric_sort_key)


def _metric_sort_key(metric: str) -> tuple[int, int, int]:
    parts = metric.split(".")
    numeric_parts = [int(part) for part in parts if part.isdigit()]
    while len(numeric_parts) < 3:
        numeric_parts.append(0)
    return numeric_parts[0], numeric_parts[1], numeric_parts[2]


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
    candidate = _extract_compact_factual_answer(candidate, user_query)
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
    if not _is_count_style_query(query):
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


def _extract_compact_factual_answer(text: str, user_query: str) -> str:
    """Force direct answers into a compact single-line factual output when possible."""
    candidate = re.sub(r"\s+", " ", (text or "")).strip()
    if not candidate:
        return ""

    query = (user_query or "").strip().lower()
    if _is_count_style_query(query):
        compact = _extract_numeric_value_with_unit(candidate, query)
        if compact:
            return compact

    if len(candidate) > 180:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", candidate) if part.strip()]
        if sentences:
            candidate = sentences[0]

    if not candidate.endswith((".", "!", "?")):
        candidate = f"{candidate}."

    return candidate


def _is_count_style_query(query: str) -> bool:
    return any(phrase in query for phrase in ["how many", "number of", "count of", "total number"])


def _extract_numeric_value_with_unit(text: str, query: str) -> str:
    """Extract the tightest number+unit phrase for count-style direct answers."""
    # Pattern 1: explicit result clause.
    clause_match = re.search(
        r"(?:is|are|was|were|:|=)\s*([0-9][0-9,]*(?:\.[0-9]+)?\s+[a-zA-Z%][a-zA-Z0-9%\- ]{0,28})",
        text,
        flags=re.IGNORECASE,
    )
    if clause_match:
        compact = clause_match.group(1).strip()
        compact = re.sub(r"\s+", " ", compact)
        return compact if compact.endswith((".", "!", "?")) else f"{compact}."

    unit_map = [
        ("course", r"courses?"),
        ("student", r"students?"),
        ("faculty", r"faculty"),
        ("program", r"programs?"),
        ("year", r"years?"),
        ("percent", r"%|percent"),
        ("percentage", r"%|percent"),
    ]

    selected_unit_pattern = r"courses?|students?|faculty|programs?|years?|%|percent"
    for query_token, unit_pattern in unit_map:
        if query_token in query:
            selected_unit_pattern = unit_pattern
            break

    fallback_match = re.search(
        rf"\b([0-9][0-9,]*(?:\.[0-9]+)?)\s+({selected_unit_pattern})\b",
        text,
        flags=re.IGNORECASE,
    )
    if fallback_match:
        value = fallback_match.group(1)
        unit = fallback_match.group(2)
        compact = f"{value} {unit}".strip()
        compact = re.sub(r"\s+", " ", compact)
        return compact if compact.endswith((".", "!", "?")) else f"{compact}."

    return ""
