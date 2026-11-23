"""
Analysis Service for FormEase.
Orchestrates multi-component document simplification via the configured AI provider:
- Executive Summary & Overview
- Section Explanations (Simple, Balanced, Detailed)
- Process Flowchart with Mermaid validation
- Key Information & Critical Obligations
- Definitions & Contextual Recommendations
- Reliability & Source Evidence Checking
- Interactive Component Refinement
"""
from typing import Dict, Any, List, Optional, Callable, Awaitable
import uuid
import re
from ..ai.ollama_client import ollama_client
from ..ai.prompts import (
    build_batched_analysis_prompt,
    build_combined_modules_prompt,
    build_focused_module_prompt,
    build_process_recovery_prompt,
    build_section_explanation_prompt,
    build_summary_prompt,
)
from ..processors.extractor import DocumentExtractionResult
from ..core.config import settings

def _analysis_text_parts(text: str, limit: int = 4200) -> List[str]:
    """Split document text into bounded, paragraph-aware model contexts."""
    paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
    parts: List[str] = []
    current = ""
    for paragraph in paragraphs:
        while len(paragraph) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) > limit and current:
            parts.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts or [""]

def _analysis_batches(extraction: DocumentExtractionResult) -> List[List[Dict[str, Any]]]:
    """Group page/section text into bounded requests without losing source metadata."""
    limit = max(2000, settings.AI_ANALYSIS_BATCH_CHARS)
    segments: List[Dict[str, Any]] = []
    for section in extraction.sections:
        for piece in _analysis_text_parts(section.text, max(1000, limit - 500)):
            segments.append({"heading": section.heading, "page_number": section.page_number, "text": piece})
    if not segments and extraction.full_text:
        segments = [{"heading": "Document", "page_number": 1, "text": piece}
                    for piece in _analysis_text_parts(extraction.full_text, max(1000, limit - 500))]
    batches: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_size = 0
    for segment in segments:
        size = len(segment["text"]) + len(segment["heading"]) + 40
        if current and current_size + size > limit:
            batches.append(current)
            current, current_size = [], 0
        current.append(segment)
        current_size += size
    if current:
        batches.append(current)
    return batches

def validate_mermaid_syntax(mermaid_str: str) -> Dict[str, Any]:
    """
    Validates and cleans Mermaid flowchart syntax to prevent client-side rendering crashes.
    Preserves Mermaid arrow syntax (--> , ==>, -.->) while removing dangerous tags.
    """
    if not mermaid_str or not isinstance(mermaid_str, str):
        return {"valid": False, "cleaned": ""}
    
    cleaned = mermaid_str.strip()
    if not (cleaned.startswith("graph ") or cleaned.startswith("flowchart ")):
        cleaned = "graph TD\n  " + cleaned
    cleaned = re.sub(r'<script.*?>.*?</script>', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'<iframe.*?>.*?</iframe>', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines or not re.fullmatch(r"(?:graph|flowchart)\s+(?:TD|TB|BT|RL|LR)", lines[0], flags=re.IGNORECASE):
        return {"valid": False, "cleaned": ""}
    node = r'[A-Za-z][\w-]*(?:\s*(?:\[[^\]\n]*\]|\{[^}\n]*\}|\(\[[^\]\n]*\]\)))?'
    edge = re.compile(rf"{node}(?:\s*(?:-->|---|==>|-.->)(?:\|[^|\n]*\|)?\s*{node})+")
    node_definition = re.compile(rf"{node}")
    if len(lines) == 1 or any(not (edge.fullmatch(line) or node_definition.fullmatch(line)) for line in lines[1:]):
        return {"valid": False, "cleaned": ""}
    return {"valid": True, "cleaned": cleaned}


def _is_provider_failure(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in (
        "ollama unavailable", "ollama inference failed", "connection failed",
        "could not connect", "request timed out", "quota is exhausted",
        "temporarily rate limited", "requires account billing", "denied this request",
        "could not connect to openrouter",
    ))


def _diagram_label(value: Any) -> str:
    """Return a single-line Mermaid label without executable markup or syntax delimiters."""
    return re.sub(r"[\[\]{}<>\"'`|\n\r]", " ", str(value or "")).strip()[:90]


def is_generic_placeholder_text(value: Any) -> bool:
    """Detect generic prose that only describes the UI or prompt instead of document content."""
    text = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    if not text:
        return True
    placeholder_patterns = (
        r"^this section provides an overview",
        r"^this section provides a concise summary",
        r"^this section explains each section",
        r"^no section",
        r"^not identified in the document",
        r"^unavailable because",
        r"^a concise summary of this part",
        r"^plain explanation of",
    )
    return any(re.search(pattern, text) for pattern in placeholder_patterns)


def _source_section_for_response(response_section: Dict[str, Any], batch: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    response_page = response_section.get("page_number")
    response_heading = str(response_section.get("heading") or "").strip().casefold()
    for source in batch:
        if isinstance(response_page, int) and response_page == source.get("page_number"):
            return source
    if response_heading:
        for source in batch:
            if response_heading == str(source.get("heading") or "").strip().casefold():
                return source
    return batch[0] if len(batch) == 1 else None


async def _generate_source_section(extraction_title: str, source: Dict[str, Any], language: str, depth: str) -> Optional[Dict[str, Any]]:
    response = await ollama_client.generate_json(build_section_explanation_prompt(
        str(source.get("heading") or "Document section"),
        str(source.get("text") or ""),
        int(source.get("page_number") or 1),
        language,
        depth,
    ))
    if not isinstance(response, dict) or response.get("json_parse_warning"):
        return None
    explanation = response.get("simplified_explanation")
    if not isinstance(explanation, str) or is_generic_placeholder_text(explanation):
        return None
    key_points = response.get("key_points") if isinstance(response.get("key_points"), list) else []
    risks = response.get("potential_risks") if isinstance(response.get("potential_risks"), list) else []
    risk_level = response.get("risk_level") if response.get("risk_level") in ("low", "medium", "high") else "low"
    return {
        "heading": str(source.get("heading") or "Document section"),
        "page_number": int(source.get("page_number") or 1),
        "simplified_explanation": explanation.strip(),
        "key_points": [item for item in key_points if isinstance(item, str) and item.strip()],
        "potential_risks": [item for item in risks if isinstance(item, str) and item.strip()],
        "risk_level": risk_level,
    }


def _has_explicit_flow_cues(sections: List[Dict[str, Any]]) -> bool:
    source = " ".join(str(section.get("text", "")) for section in sections).casefold()
    patterns = (
        r"\b(?:first|then|next|afterward|finally)\b", r"\bsteps?\s*\d*\b", r"\bstages?\s*\d*\b",
        r"\bsequence\b", r"\bworkflow\b", r"\bmoves?\s+(?:up|down|through|from)\b",
        r"\bflows?\s+through\b", r"\bpasses?\s+through\b", r"\btransforms?\s+into\b",
        r"\b(?:cycle|lifecycle|converts?|transforms?|produces?|generates?|transmits?)\b",
    )
    return any(re.search(pattern, source) for pattern in patterns)


def _extract_explicit_flow_steps(sections: List[Dict[str, Any]], title: str) -> Optional[Dict[str, Any]]:
    """Build a minimal flow only from source-listed stages or ordered sentences."""
    source = "\n".join(str(section.get("text", "")) for section in sections)
    page = next((section.get("page_number", 1) for section in sections if section.get("text")), 1)
    items: List[Any] = []
    list_match = re.search(
        r"\b(layers?|stages?|phases?|steps?)\b\s*(?:are|include|consist\s+of|:)\s*([^.;\n]+)",
        source, flags=re.IGNORECASE,
    )
    if list_match:
        group, listed = list_match.group(1).casefold(), list_match.group(2)
        candidates = [re.sub(r"^\s*(?:\d+[.)]|step\s+\d+[:.)-])\s*", "", part).strip(" :.-")
                      for part in re.split(r",|\band\b|\bthen\b", listed, flags=re.IGNORECASE)]
        candidates = [item for item in candidates if 1 <= len(item.split()) <= 8]
        direction_evidence = bool(re.search(r"\b(?:moves?|flows?|passes?|transmits?|travels?)\s+(?:up|down|through|from)\b", source, re.IGNORECASE))
        minimum = 3 if group.startswith("layer") else 2
        if len(candidates) >= minimum and (not group.startswith("layer") or direction_evidence):
            candidates = candidates[:12]
            goes_down = bool(re.search(r"\b(?:down|downward|descending|higher\s+to\s+lower)\b", source, re.IGNORECASE))
            goes_up = bool(re.search(r"\b(?:upward|ascending|lower\s+to\s+higher)\b", source, re.IGNORECASE))
            if group.startswith("layer") and goes_down and goes_up:
                items = [
                    (f"Sender — {name}", f"At the sender, data passes through the {name} layer.")
                    for name in reversed(candidates)
                ] + [
                    (f"Receiver — {name}", f"At the receiver, data passes through the {name} layer.")
                    for name in candidates
                ]
            elif group.startswith("layer") and goes_down:
                items = [(name, f"Data moves downward through the {name} layer.") for name in reversed(candidates)]
            elif group.startswith("layer") and goes_up:
                items = [(name, f"Data moves upward through the {name} layer.") for name in candidates]
            else:
                items = [(name, f"Listed {group.rstrip('s')}: {name}.") for name in candidates]

    if not items:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", source) if part.strip()]
        ordered = []
        marker = re.compile(r"^(?:first(?:ly)?|initially|step\s*\d+|\d+[.)]|then|next|after that|subsequently|finally|lastly|in the end)\b\s*[:,.-]?\s*", re.IGNORECASE)
        for sentence in sentences:
            match = marker.match(sentence)
            if match:
                detail = sentence[match.end():].strip()
                if detail:
                    ordered.append((" ".join(detail.split()[:7]).strip(" ,:."), detail))
        if len(ordered) >= 2:
            items = ordered[:12]

    if not items:
        return None
    steps = []
    for index, item in enumerate(items, 1):
        if isinstance(item, tuple):
            step_title, description = item
        else:
            words = item.split()
            step_title, description = " ".join(words[:7]).strip(" ,:."), item
        steps.append({
            "step_number": index,
            "title": step_title or f"Step {index}",
            "description": description,
            "node_type": "start" if index == 1 else "end" if index == len(items) else "step",
            "inputs": [], "outputs": [], "condition": "", "next_steps": [], "page_number": page,
        })
    return {"has_process": True, "process_title": title, "steps": steps}


def _extract_osi_flow_steps(sections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Reconstruct a full OSI send/receive path only when its required facts are present."""
    source = "\n".join(str(section.get("text", "")) for section in sections)
    if not source.strip():
        return None

    layer_names = [
        ("Application", r"\bapplication(?:\s+layer)?\b"),
        ("Presentation", r"\bpresentation(?:\s+layer)?\b"),
        ("Session", r"\bsession(?:\s+layer)?\b"),
        ("Transport", r"\btransport(?:\s+layer)?\b"),
        ("Network", r"\bnetwork(?:\s+layer)?\b"),
        ("Data Link", r"\bdata[\s-]+link(?:\s+layer)?\b"),
        ("Physical", r"\bphysical(?:\s+layer)?\b"),
    ]
    if not all(re.search(pattern, source, re.IGNORECASE) for _, pattern in layer_names):
        return None

    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", source) if sentence.strip()]
    def has_sentence(*patterns: str) -> bool:
        return any(all(re.search(pattern, sentence, re.IGNORECASE) for pattern in patterns) for sentence in sentences)

    sender_receiver = bool(
        re.search(r"\bsender\b", source, re.IGNORECASE)
        and re.search(r"\breceiver\b", source, re.IGNORECASE)
    )
    bidirectional_evidence = (
        bool(re.search(r"\bencapsulat\w*\b", source, re.IGNORECASE)
             and re.search(r"\bdecapsulat\w*\b", source, re.IGNORECASE))
        or has_sentence(r"\bsender\b", r"\b(?:down|lower|physical)\b")
        and has_sentence(r"\breceiver\b", r"\b(?:up|higher|application)\b")
    )
    if not sender_receiver or not bidirectional_evidence:
        return None

    creation_sentence = next((
        sentence for sentence in sentences
        if re.search(r"\bapplication\b", sentence, re.IGNORECASE)
        and re.search(r"\b(?:creat\w*|generat\w*|produc\w*|originat\w*)\b", sentence, re.IGNORECASE)
        and re.search(r"\bdata\b", sentence, re.IGNORECASE)
    ), None)
    medium_sentence = next((
        sentence for sentence in sentences
        if re.search(r"\b(?:medium|media|channel|cable|wire)\b", sentence, re.IGNORECASE)
        and re.search(r"\b(?:transmi\w*|send\w*|travell?ing|moves?|signals?)\b", sentence, re.IGNORECASE)
    ), None)
    delivery_sentence = next((
        sentence for sentence in sentences
        if re.search(r"\b(?:receiv\w*|destination)\b", sentence, re.IGNORECASE)
        and re.search(r"\bapplication\b", sentence, re.IGNORECASE)
        and re.search(r"\b(?:deliver\w*|pass\w*|forward\w*|reach\w*)\b", sentence, re.IGNORECASE)
        and re.search(r"\bdata\b", sentence, re.IGNORECASE)
    ), None)
    if not creation_sentence or not medium_sentence or not delivery_sentence:
        return None

    def page_for(text: str, fallback: int = 1) -> int:
        for section in sections:
            if text.casefold() in str(section.get("text", "")).casefold():
                return int(section.get("page_number") or fallback)
        return fallback

    steps = [{
        "title": "Sender application creates data",
        "description": creation_sentence,
        "node_type": "start",
        "page_number": page_for(creation_sentence),
    }]
    for layer_number, (name, pattern) in zip(range(7, 0, -1), layer_names):
        layer_page = next((
            int(section.get("page_number") or 1)
            for section in sections
            if re.search(pattern, str(section.get("text", "")), re.IGNORECASE)
        ), 1)
        steps.append({
            "title": f"{name} Layer (Layer {layer_number})",
            "description": f"Sender-side data passes through the {name} layer during encapsulation.",
            "node_type": "step",
            "page_number": layer_page,
        })
    steps.append({
        "title": "Transmission through the medium",
        "description": medium_sentence,
        "node_type": "step",
        "page_number": page_for(medium_sentence),
    })
    for layer_number, (name, pattern) in zip(range(1, 8), reversed(layer_names)):
        layer_page = next((
            int(section.get("page_number") or 1)
            for section in sections
            if re.search(pattern, str(section.get("text", "")), re.IGNORECASE)
        ), 1)
        steps.append({
            "title": f"{name} Layer (Layer {layer_number})",
            "description": f"Receiver-side data passes through the {name} layer during decapsulation.",
            "node_type": "step",
            "page_number": layer_page,
        })
    steps.append({
        "title": "Data delivered to the receiving application",
        "description": delivery_sentence,
        "node_type": "end",
        "page_number": page_for(delivery_sentence),
    })
    for index, step in enumerate(steps, start=1):
        step["step_number"] = index

    return {
        "has_process": True,
        "process_title": "OSI Data Transmission and Reception",
        "start_state": "Sending application",
        "end_state": "Receiving application",
        "steps": steps,
    }


def _build_process_mermaid(process: Dict[str, Any]) -> str:
    steps = process.get("steps", [])
    if not steps:
        return ""
    identifiers = {str(step.get("title", "")).casefold(): f"S{index}" for index, step in enumerate(steps, 1)}
    lines = ["flowchart TD"]
    for index, step in enumerate(steps, 1):
        identifier = f"S{index}"
        title = _diagram_label(step.get("title") or f"Step {index}")
        condition = _diagram_label(step.get("condition"))
        label = f"{title}: {condition}" if condition else title
        node_type = step.get("node_type", "step")
        if node_type in ("start", "end"):
            lines.append(f'  {identifier}(["{label}"])')
        elif node_type == "decision":
            lines.append(f'  {identifier}{{"{label}"}}')
        else:
            lines.append(f'  {identifier}["{label}"]')
    if process.get("start_state") and str(process["start_state"]).casefold() != str(steps[0].get("title", "")).casefold():
        lines.insert(1, f'  START(["{_diagram_label(process["start_state"])}"])')
        lines.append("  START --> S1")
    if process.get("end_state") and str(process["end_state"]).casefold() != str(steps[-1].get("title", "")).casefold():
        lines.insert(-1, f'  END(["{_diagram_label(process["end_state"])}"])')
        lines.append(f"  S{len(steps)} --> END")
    for index, step in enumerate(steps, 1):
        explicit = step.get("next_steps", [])
        edges = 0
        for next_step in explicit if isinstance(explicit, list) else []:
            target = identifiers.get(str(next_step.get("title", "")).casefold()) if isinstance(next_step, dict) else None
            if target:
                condition = _diagram_label(next_step.get("condition"))
                lines.append(f"  S{index} -->|{condition}| {target}" if condition else f"  S{index} --> {target}")
                edges += 1
        if not edges and index < len(steps):
            lines.append(f"  S{index} --> S{index + 1}")
    return "\n".join(lines)


def _generic_process_title(value: Any) -> bool:
    normalized = re.sub(r"[\W_]+", " ", str(value or "")).strip().casefold()
    return normalized in {
        "", "procedure", "process", "workflow", "process flow", "document process",
        "document workflow", "flowchart", "steps",
    }


def _process_step_summary(step: Dict[str, Any]) -> str:
    summary = step.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = step.get("description")
    return summary.strip() if isinstance(summary, str) else ""


def _normalize_process_step(step: Any, step_number: int) -> Optional[Dict[str, Any]]:
    if not isinstance(step, dict):
        return None
    title = step.get("title")
    summary = _process_step_summary(step)
    if not isinstance(title, str) or not title.strip() or not summary:
        return None

    raw_inputs_outputs = step.get("inputs_outputs")
    normalized_inputs_outputs = {}
    for field in ("inputs", "outputs"):
        values = (
            raw_inputs_outputs.get(field)
            if isinstance(raw_inputs_outputs, dict)
            and isinstance(raw_inputs_outputs.get(field), list)
            else step.get(field)
        )
        normalized_inputs_outputs[field] = [
            item.strip() for item in values
            if isinstance(item, str) and item.strip()
        ] if isinstance(values, list) else []

    def normalized_strings(field: str) -> List[str]:
        values = step.get(field)
        return [
            item.strip() for item in values
            if isinstance(item, str) and item.strip()
        ] if isinstance(values, list) else []

    brief_explanation = step.get("brief_explanation")
    if not isinstance(brief_explanation, str) or not brief_explanation.strip():
        brief_explanation = summary
    description = step.get("description")
    if not isinstance(description, str) or not description.strip():
        description = summary

    normalized = {
        **step,
        "step_number": step_number,
        "title": title.strip(),
        "summary": summary,
        "description": description.strip(),
        "brief_explanation": brief_explanation.strip(),
        "key_actions": normalized_strings("key_actions"),
        "inputs_outputs": normalized_inputs_outputs,
        "inputs": normalized_inputs_outputs["inputs"],
        "outputs": normalized_inputs_outputs["outputs"],
        "key_components_or_actors": normalized_strings("key_components_or_actors"),
    }
    if normalized.get("node_type") not in ("start", "step", "decision", "end"):
        normalized["node_type"] = "step"
    if not isinstance(normalized.get("next_steps"), list):
        normalized["next_steps"] = []
    else:
        normalized["next_steps"] = [
            item for item in normalized["next_steps"]
            if isinstance(item, dict) and isinstance(item.get("title"), str)
        ]
    return normalized


def normalize_process_flow(process: Any, document_title: str = "") -> Dict[str, Any]:
    """Validate persisted step data and always derive its diagram from those steps."""
    if not isinstance(process, dict):
        process = {}
    steps = []
    for step in process.get("steps", []) if isinstance(process.get("steps"), list) else []:
        normalized = _normalize_process_step(step, len(steps) + 1)
        if not normalized:
            continue
        steps.append(normalized)

    if not steps:
        return {
            **process,
            "has_process": False,
            "process_title": "",
            "steps": [],
            "mermaid_syntax": "",
        }

    title = process.get("process_title")
    if _generic_process_title(title):
        candidate = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", str(document_title or "").split("/")[-1]).replace("_", " ").strip()
        if _generic_process_title(candidate):
            candidate = f"{steps[0]['title']} to {steps[-1]['title']}" if len(steps) > 1 else steps[0]["title"]
        title = candidate

    normalized_flow = {
        **process,
        "has_process": True,
        "process_title": str(title or "").strip(),
        "steps": steps,
    }
    chart = validate_mermaid_syntax(_build_process_mermaid(normalized_flow))
    normalized_flow["mermaid_syntax"] = chart["cleaned"] if chart["valid"] else ""
    return normalized_flow


def _build_concept_mermaid(concept_map: Dict[str, Any]) -> str:
    concepts = concept_map.get("concepts", [])
    if not concepts:
        return ""
    direction = concept_map.get("diagram_direction")
    if direction not in {"TB", "TD", "BT", "LR", "RL"}:
        direction = "LR"
    is_layer_stack = direction in {"TB", "TD"} and len(concepts) > 1 and all(
        isinstance(item, dict) and re.search(r"\blayer\b", str(item.get("name", "")), re.IGNORECASE)
        for item in concepts
    )
    lines = [f"flowchart {direction}"]
    names = {str(item.get("name", "")).casefold(): f"C{index}" for index, item in enumerate(concepts, 1)}
    central = _diagram_label(concept_map.get("central_topic"))
    if central and central.casefold() not in names and not is_layer_stack:
        lines.append(f'  ROOT(["{central}"])')
    for index, item in enumerate(concepts, 1):
        label_parts = [_diagram_label(item.get("name"))]
        data_unit = _diagram_label(item.get("data_unit"))
        examples = item.get("protocols_hardware_standards")
        if data_unit:
            label_parts.append(f"PDU: {data_unit}")
        if isinstance(examples, list):
            example_text = ", ".join(_diagram_label(value) for value in examples[:3] if isinstance(value, str) and value.strip())
            if example_text:
                label_parts.append(f"Examples: {example_text}")
        label = re.sub(r"[\[\]{}<>\"'`|\n\r]", " ", "; ".join(label_parts)).strip()[:210]
        lines.append(f'  C{index}["{label}"]')
    relationships = list(concept_map.get("relationships", []))
    known_edges = set()
    for item in concepts:
        parent_name = str(item.get("parent", "")).casefold()
        parent = names.get(parent_name) or ("ROOT" if central and parent_name == central.casefold() and not is_layer_stack else None)
        child = names.get(str(item.get("name", "")).casefold())
        if parent and child and parent != child:
            lines.append(f"  {parent} -->|includes| {child}")
            known_edges.add((parent, child))
    for relation in relationships:
        source = names.get(str(relation.get("from", "")).casefold())
        target = names.get(str(relation.get("to", "")).casefold())
        if source and target and source != target and (source, target) not in known_edges:
            label = _diagram_label(relation.get("label"))
            lines.append(f"  {source} -->|{label}| {target}" if label else f"  {source} --> {target}")
            known_edges.add((source, target))
    return "\n".join(lines)


COMBINED_MODULES = (
    "revision_notes",
    "formulas",
    "key_information",
    "definitions",
    "recommendations",
)


def _normalize_combined_module_value(module: str, value: Any) -> Any:
    """Normalize only the same small-model shapes accepted by individual requests."""
    if isinstance(value, dict) and module in value:
        value = value[module]

    if module == "revision_notes" and isinstance(value, dict):
        if isinstance(value.get("note"), str):
            value = [value["note"]]
        elif value and all(isinstance(item, str) for item in value.values()) and all(
            "note" in str(key).casefold() for key in value
        ):
            value = list(value.values())
    elif module in ("formulas", "definitions", "recommendations") and isinstance(value, dict):
        record_key = {
            "formulas": "formula",
            "definitions": "term",
            "recommendations": "recommendation",
        }[module]
        if isinstance(value.get(record_key), str):
            value = [value]
    return value


def _merge_combined_module(results: Dict[str, Any], module: str, raw_value: Any) -> None:
    """Validate and merge one combined-module value; raise when it is malformed."""
    if raw_value is None or (isinstance(raw_value, dict) and raw_value.get("json_parse_warning")):
        raise ValueError("The model returned invalid JSON for this module.")

    value = _normalize_combined_module_value(module, raw_value)

    if module == "revision_notes":
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("Malformed revision_notes response.")
        results["revision_notes"] = list(dict.fromkeys([
            *results["revision_notes"],
            *(item.strip() for item in value if item.strip()),
        ]))
    elif module == "formulas":
        if not isinstance(value, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("formula"), str)
            for item in value
        ):
            raise ValueError("Malformed formulas response.")
        merged = [
            *results["formulas"],
            *(item for item in value if item.get("formula")),
        ]
        results["formulas"] = list({
            (item.get("formula"), item.get("page_number")): item
            for item in merged
        }.values())
    elif module == "key_information":
        if not isinstance(value, dict) or any(
            not isinstance(items, list)
            or any(not isinstance(item, str) for item in items)
            for items in value.values()
        ):
            raise ValueError("Malformed key_information response.")
        for key, items in value.items():
            results["key_information"].setdefault(key, [])
            results["key_information"][key] = list(dict.fromkeys(
                results["key_information"][key] + items
            ))
    elif module == "definitions":
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError("Malformed definitions response.")
        known = {str(item.get("term", "")).casefold() for item in results["definitions"]}
        for item in value:
            if (
                isinstance(item.get("term"), str)
                and item["term"].strip()
                and isinstance(item.get("plain_definition"), str)
                and item["plain_definition"].strip()
                and item["term"].casefold() not in known
            ):
                results["definitions"].append(item)
                known.add(item["term"].casefold())
    elif module == "recommendations":
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError("Malformed recommendations response.")
        known = {
            str(item.get("recommendation", "")).casefold()
            for item in results["recommendations"]
        }
        for item in value:
            if (
                isinstance(item.get("recommendation"), str)
                and item["recommendation"].strip()
                and item["recommendation"].casefold() not in known
            ):
                results["recommendations"].append(item)
                known.add(item["recommendation"].casefold())

class AnalysisService:
    @staticmethod
    async def analyze_document(
        extraction: DocumentExtractionResult,
        language: str = "en",
        depth: str = "balanced",
        selected_components: Optional[List[str]] = None,
        existing_result: Optional[Dict[str, Any]] = None,
        completed_batches: Optional[List[int]] = None,
        completed_module_batches: Optional[Dict[str, List[int]]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        Generates the core explanation and each advanced module in separate bounded
        requests. Successful modules are persisted independently and skipped on retry.
        """
        selected = selected_components or [
            "summary", "sections", "process", "key_info", "definitions", "recommendations", "diagrams"
        ]
        batches = _analysis_batches(extraction)
        if not batches:
            raise ValueError("The uploaded document contains no extractable text to analyze.")
        done = set(completed_batches or [])
        module_done = {key: set(value) for key, value in (completed_module_batches or {}).items()}
        previous = existing_result or {}
        base_selected = [name for name in ("summary", "sections") if name in selected]
        module_selected = []
        if "process" in selected or "diagrams" in selected:
            module_selected.append("process_flow")
        if "diagrams" in selected or "concept_map" in selected:
            module_selected.append("concept_map")
        if "revision_notes" in selected or ("summary" in selected and "key_info" in selected):
            module_selected.append("revision_notes")
        if "key_info" in selected:
            module_selected.extend(("formulas", "key_information"))
        if "definitions" in selected:
            module_selected.append("definitions")
        if "recommendations" in selected:
            module_selected.append("recommendations")
        module_selected = list(dict.fromkeys(module_selected))
        results: Dict[str, Any] = {
            "language": language,
            "depth": depth,
            "overview": previous.get("overview", {}),
            "summary": previous.get("summary", ""),
            "sections": list(previous.get("sections", [])),
            "process_flow": previous.get("process_flow") or {"has_process": False, "process_title": "", "start_state": "", "end_state": "", "steps": [], "mermaid_syntax": ""},
            "concept_map": previous.get("concept_map") or {"central_topic": "", "concepts": [], "relationships": [], "mermaid_syntax": ""},
            "key_information": previous.get("key_information") or {},
            "definitions": list(previous.get("definitions", [])),
            "recommendations": list(previous.get("recommendations", [])),
            "formulas": list(previous.get("formulas", [])),
            "revision_notes": list(previous.get("revision_notes", [])),
            "reliability_report": {
                "warnings": list(extraction.warnings),
                "coverage_pages": extraction.page_count,
                "missing_sections": len(extraction.warnings) > 0,
                "facts_grounded": True,
                "total_batches": len(batches),
                "completed_batches": sorted(done),
                "failed_batches": [],
                "module_batches": {name: sorted(module_done.get(name, set())) for name in module_selected},
                "failed_modules": [],
                "selected_modules": module_selected,
                "selected_components": selected,
            }
        }

        async def save_progress():
            results["reliability_report"]["completed_batches"] = sorted(done)
            results["reliability_report"]["module_batches"] = {
                name: sorted(module_done.get(name, set())) for name in module_selected
            }
            results["reliability_report"]["failed_batches"] = sorted(set(results["reliability_report"]["failed_batches"]))
            results["reliability_report"]["failed_modules"] = sorted(set(results["reliability_report"]["failed_modules"]))
            results["reliability_report"]["is_complete"] = not (
                results["reliability_report"]["failed_batches"] or results["reliability_report"]["failed_modules"]
            )
            if progress_callback:
                await progress_callback(results)

        stop_for_provider = False
        for batch_index, batch in enumerate(batches):
            if base_selected and batch_index not in done:
                try:
                    response = await ollama_client.generate_json(build_batched_analysis_prompt(
                        extraction.title, batch_index + 1, len(batches), batch, language, depth
                    ))
                    if not isinstance(response, dict) or response.get("json_parse_warning"):
                        raise ValueError("The model did not return the required overview and section object.")
                    if "summary" in base_selected:
                        summary = response.get("summary") or response.get("overall_summary")
                        fallback_overview = {}
                        if not isinstance(summary, str) or not summary.strip() or is_generic_placeholder_text(summary):
                            fallback = await ollama_client.generate_json(build_summary_prompt(
                                extraction.title,
                                "\n\n".join(str(source.get("text") or "") for source in batch),
                                language,
                                depth,
                            ))
                            if isinstance(fallback, dict):
                                summary = fallback.get("overall_summary")
                                fallback_overview = fallback
                        overview = response.get("overview")
                        if not isinstance(overview, dict):
                            overview = fallback_overview
                        if not isinstance(overview, dict) or not isinstance(summary, str) or not summary.strip() or is_generic_placeholder_text(summary):
                            raise ValueError("The model omitted the essential overview or summary fields.")
                        if not results["overview"]:
                            results["overview"] = overview
                        results["summary"] = "\n\n".join(filter(None, [results["summary"], summary]))
                    if "sections" in base_selected:
                        sections = response.get("sections")
                        if not isinstance(sections, list) or not sections:
                            sections = []
                        accepted_by_source = set()
                        usable_section_output = False
                        for section in sections:
                            if not isinstance(section, dict):
                                continue
                            explanation = section.get("simplified_explanation")
                            if not isinstance(explanation, str) or is_generic_placeholder_text(explanation):
                                continue
                            usable_section_output = True
                            source = _source_section_for_response(section, batch)
                            if not source:
                                continue
                            identity = (str(source["heading"]), int(source["page_number"]))
                            normalized = {
                                "heading": source["heading"],
                                "page_number": source["page_number"],
                                "simplified_explanation": explanation.strip(),
                                "key_points": [item for item in section.get("key_points", []) if isinstance(item, str) and item.strip()] if isinstance(section.get("key_points"), list) else [],
                                "potential_risks": [item for item in section.get("potential_risks", []) if isinstance(item, str) and item.strip()] if isinstance(section.get("potential_risks"), list) else [],
                                "risk_level": section.get("risk_level") if section.get("risk_level") in ("low", "medium", "high") else "low",
                            }
                            accepted_by_source.add(identity)
                            existing = next((item for item in results["sections"]
                                             if (item.get("heading"), item.get("page_number")) == identity), None)
                            if existing:
                                existing["simplified_explanation"] += "\n\n" + normalized["simplified_explanation"]
                                existing["key_points"] = list(dict.fromkeys(existing.get("key_points", []) + normalized["key_points"]))
                                existing["potential_risks"] = list(dict.fromkeys(existing.get("potential_risks", []) + normalized["potential_risks"]))
                            else:
                                results["sections"].append(normalized)
                        if not usable_section_output:
                            for source in batch:
                                identity = (str(source["heading"]), int(source["page_number"]))
                                regenerated = await _generate_source_section(extraction.title, source, language, depth)
                                if regenerated:
                                    results["sections"].append(regenerated)
                                    accepted_by_source.add(identity)
                        if not results["sections"]:
                            raise ValueError("The model did not return a document-grounded section explanation.")
                    done.add(batch_index)
                    await save_progress()
                except Exception as exc:
                    results["reliability_report"]["failed_batches"].append(batch_index)
                    results["reliability_report"]["warnings"].append(f"Core analysis part {batch_index + 1} failed: {str(exc)}")
                    await save_progress()
                    stop_for_provider = _is_provider_failure(exc)

            combined_pending = [
                module for module in COMBINED_MODULES
                if module in module_selected
                and batch_index not in module_done.get(module, set())
            ]
            if combined_pending and not stop_for_provider:
                if len(combined_pending) == 1:
                    module = combined_pending[0]
                    try:
                        retry_value = await ollama_client.generate_json(build_focused_module_prompt(
                            module,
                            extraction.title,
                            batch_index + 1,
                            len(batches),
                            batch,
                            language,
                        ))
                        _merge_combined_module(results, module, retry_value)
                        module_done.setdefault(module, set()).add(batch_index)
                        await save_progress()
                    except Exception as retry_exc:
                        results["reliability_report"]["failed_modules"].append(f"{module}:{batch_index}")
                        results["reliability_report"]["warnings"].append(
                            f"{module} analysis part {batch_index + 1} failed: {str(retry_exc)}"
                        )
                        await save_progress()
                        stop_for_provider = stop_for_provider or _is_provider_failure(retry_exc)
                else:
                    try:
                        combined = await ollama_client.generate_json(build_combined_modules_prompt(
                            combined_pending,
                            extraction.title,
                            batch_index + 1,
                            len(batches),
                            batch,
                            language,
                        ))
                        if not isinstance(combined, dict) or combined.get("json_parse_warning"):
                            raise ValueError("The combined module request returned invalid JSON.")

                        for module in combined_pending:
                            try:
                                _merge_combined_module(results, module, combined.get(module))
                                module_done.setdefault(module, set()).add(batch_index)
                                await save_progress()
                            except Exception as retry_exc:
                                try:
                                    retry_value = await ollama_client.generate_json(build_focused_module_prompt(
                                        module,
                                        extraction.title,
                                        batch_index + 1,
                                        len(batches),
                                        batch,
                                        language,
                                    ))
                                    _merge_combined_module(results, module, retry_value)
                                    module_done.setdefault(module, set()).add(batch_index)
                                    await save_progress()
                                except Exception as retry_exc:
                                    results["reliability_report"]["failed_modules"].append(f"{module}:{batch_index}")
                                    results["reliability_report"]["warnings"].append(
                                        f"{module} analysis part {batch_index + 1} failed: {str(retry_exc)}"
                                    )
                                    await save_progress()
                                    stop_for_provider = stop_for_provider or _is_provider_failure(retry_exc)
                    except Exception as exc:
                        if _is_provider_failure(exc):
                            stop_for_provider = True
                            for module in combined_pending:
                                if batch_index not in module_done.get(module, set()):
                                    results["reliability_report"]["failed_modules"].append(f"{module}:{batch_index}")
                                    results["reliability_report"]["warnings"].append(
                                        f"{module} analysis part {batch_index + 1} failed: {str(exc)}"
                                    )
                        else:
                            for module in combined_pending:
                                try:
                                    retry_value = await ollama_client.generate_json(build_focused_module_prompt(
                                        module,
                                        extraction.title,
                                        batch_index + 1,
                                        len(batches),
                                        batch,
                                        language,
                                    ))
                                    _merge_combined_module(results, module, retry_value)
                                    module_done.setdefault(module, set()).add(batch_index)
                                    await save_progress()
                                except Exception as retry_exc:
                                    results["reliability_report"]["failed_modules"].append(f"{module}:{batch_index}")
                                    results["reliability_report"]["warnings"].append(
                                        f"{module} analysis part {batch_index + 1} failed: {str(retry_exc)}"
                                    )
                                    await save_progress()
                                    stop_for_provider = stop_for_provider or _is_provider_failure(retry_exc)
                        await save_progress()

            for module in ([] if stop_for_provider else module_selected):
                if module in COMBINED_MODULES:
                    continue
                if batch_index in module_done.get(module, set()):
                    continue
                try:
                    value = await ollama_client.generate_json(build_focused_module_prompt(
                        module, extraction.title, batch_index + 1, len(batches), batch, language
                    ))
                    if value is None or (isinstance(value, dict) and value.get("json_parse_warning")):
                        raise ValueError("The model returned invalid JSON for this module.")
                    # Small instruct models sometimes wrap the requested JSON
                    # value in an object named after the module. Accept only
                    # that explicit wrapper; do not guess at arbitrary fields.
                    if isinstance(value, dict) and module in value:
                        value = value[module]
                    # llama3.2:1b occasionally turns an array example into a
                    # named object or returns a single record. Normalize only
                    # unambiguous shapes; all other malformed values remain
                    # retryable failures.
                    if module == "revision_notes" and isinstance(value, dict):
                        if isinstance(value.get("note"), str):
                            value = [value["note"]]
                        elif value and all(isinstance(item, str) for item in value.values()) and all("note" in str(key).casefold() for key in value):
                            value = list(value.values())
                    elif module in ("formulas", "definitions", "recommendations") and isinstance(value, dict):
                        record_key = {"formulas": "formula", "definitions": "term", "recommendations": "recommendation"}[module]
                        if isinstance(value.get(record_key), str):
                            value = [value]
                    if module == "process_flow":
                        if not isinstance(value, dict) or not isinstance(value.get("has_process"), bool) or not isinstance(value.get("steps"), list):
                            raise ValueError("Malformed process_flow response.")
                        has_valid_steps = any(
                            isinstance(step, dict) and isinstance(step.get("title"), str) and step["title"].strip()
                            and _process_step_summary(step)
                            for step in value["steps"]
                        )
                        if not value["has_process"] and not has_valid_steps and _has_explicit_flow_cues(batch):
                            retry_value = await ollama_client.generate_json(build_process_recovery_prompt(
                                extraction.title, batch_index + 1, len(batches), batch, language
                            ))
                            if isinstance(retry_value, dict) and module in retry_value:
                                retry_value = retry_value[module]
                            if not isinstance(retry_value, dict) or not isinstance(retry_value.get("has_process"), bool) or not isinstance(retry_value.get("steps"), list):
                                raise ValueError("Malformed process-flow recheck response.")
                            value = retry_value
                            has_valid_steps = any(
                                isinstance(step, dict) and isinstance(step.get("title"), str) and step["title"].strip()
                                and _process_step_summary(step)
                                for step in value["steps"]
                            )
                            if not value["has_process"] and not has_valid_steps:
                                raise ValueError("The source contains ordered-flow cues, but the model did not return steps after a focused recheck.")
                        for state_key in ("start_state", "end_state"):
                            if isinstance(value.get(state_key), str) and value[state_key].strip() and not results["process_flow"].get(state_key):
                                results["process_flow"][state_key] = value[state_key].strip()
                        steps = [
                            step for step in value["steps"]
                            if isinstance(step, dict)
                            and isinstance(step.get("title"), str)
                            and step["title"].strip()
                            and _process_step_summary(step)
                        ]
                        if value["has_process"] and not steps:
                            raise ValueError("Process was marked present but no valid steps were returned.")
                        if steps:
                            steps = [
                                _normalize_process_step(step, len(results["process_flow"].get("steps", [])) + index)
                                for index, step in enumerate(steps, 1)
                            ]
                            results["process_flow"]["has_process"] = True
                            results["process_flow"]["process_title"] = results["process_flow"].get("process_title") or value.get("process_title", "")
                            known_steps = {(str(item.get("title", "")).casefold(), item.get("page_number")) for item in results["process_flow"].get("steps", [])}
                            for step in steps:
                                identity = (step["title"].casefold(), step.get("page_number"))
                                if identity not in known_steps:
                                    results["process_flow"].setdefault("steps", []).append(step)
                                    known_steps.add(identity)
                    elif module == "concept_map":
                        if not isinstance(value, dict) or not isinstance(value.get("concepts"), list) or not isinstance(value.get("relationships"), list):
                            raise ValueError("Malformed concept_map response.")
                        if isinstance(value.get("central_topic"), str) and value["central_topic"].strip() and not results["concept_map"].get("central_topic"):
                            results["concept_map"]["central_topic"] = value["central_topic"].strip()
                        existing_concepts = results["concept_map"].setdefault("concepts", [])
                        for item in value["concepts"]:
                            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
                                continue
                            normalized = dict(item)
                            normalized["name"] = item["name"].strip()
                            for field in ("description", "detailed_explanation", "data_unit", "data_unit_interaction", "parent"):
                                if not isinstance(normalized.get(field), str):
                                    normalized[field] = ""
                            for field in ("key_responsibilities", "protocols_hardware_standards"):
                                values = normalized.get(field)
                                normalized[field] = [
                                    entry.strip() for entry in values
                                    if isinstance(entry, str) and entry.strip()
                                ] if isinstance(values, list) else []
                            existing = next((
                                concept for concept in existing_concepts
                                if isinstance(concept, dict)
                                and str(concept.get("name", "")).casefold() == normalized["name"].casefold()
                            ), None)
                            if existing is None:
                                existing_concepts.append(normalized)
                            else:
                                for field in ("description", "detailed_explanation", "data_unit", "data_unit_interaction", "parent"):
                                    if not existing.get(field) and normalized.get(field):
                                        existing[field] = normalized[field]
                                for field in ("key_responsibilities", "protocols_hardware_standards"):
                                    if not existing.get(field) and normalized[field]:
                                        existing[field] = normalized[field]
                        direction = value.get("diagram_direction")
                        if direction in {"TB", "TD", "BT", "LR", "RL"}:
                            results["concept_map"]["diagram_direction"] = direction
                        known_rel = {(str(item.get("from", "")).casefold(), str(item.get("to", "")).casefold(), str(item.get("label", "")).casefold()) for item in results["concept_map"].get("relationships", [])}
                        for item in value["relationships"]:
                            if isinstance(item, dict) and isinstance(item.get("from"), str) and item["from"].strip() and isinstance(item.get("to"), str) and item["to"].strip():
                                identity = (item["from"].casefold(), item["to"].casefold(), str(item.get("label", "")).casefold())
                                if identity not in known_rel:
                                    results["concept_map"].setdefault("relationships", []).append(item)
                                    known_rel.add(identity)
                    elif module == "revision_notes":
                        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                            raise ValueError("Malformed revision_notes response.")
                        results["revision_notes"] = list(dict.fromkeys([*results["revision_notes"], *(item.strip() for item in value if item.strip())]))
                    elif module == "formulas":
                        if not isinstance(value, list) or any(not isinstance(item, dict) or not isinstance(item.get("formula"), str) for item in value):
                            raise ValueError("Malformed formulas response.")
                        merged = [*results["formulas"], *(item for item in value if item.get("formula"))]
                        results["formulas"] = list({(item.get("formula"), item.get("page_number")): item for item in merged}.values())
                    elif module == "key_information":
                        if not isinstance(value, dict) or any(not isinstance(items, list) or any(not isinstance(item, str) for item in items) for items in value.values()):
                            raise ValueError("Malformed key_information response.")
                        for key, items in value.items():
                            results["key_information"].setdefault(key, [])
                            results["key_information"][key] = list(dict.fromkeys(results["key_information"][key] + items))
                    elif module == "definitions":
                        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                            raise ValueError("Malformed definitions response.")
                        known = {str(item.get("term", "")).casefold() for item in results["definitions"]}
                        for item in value:
                            if isinstance(item.get("term"), str) and item["term"].strip() and isinstance(item.get("plain_definition"), str) and item["plain_definition"].strip() and item["term"].casefold() not in known:
                                results["definitions"].append(item)
                                known.add(item["term"].casefold())
                    elif module == "recommendations":
                        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                            raise ValueError("Malformed recommendations response.")
                        known = {str(item.get("recommendation", "")).casefold() for item in results["recommendations"]}
                        for item in value:
                            if isinstance(item.get("recommendation"), str) and item["recommendation"].strip() and item["recommendation"].casefold() not in known:
                                results["recommendations"].append(item)
                                known.add(item["recommendation"].casefold())
                    module_done.setdefault(module, set()).add(batch_index)
                    await save_progress()
                except Exception as exc:
                    if module == "process_flow":
                        source_flow = _extract_explicit_flow_steps(batch, extraction.title)
                        if source_flow:
                            current = results["process_flow"]
                            current["has_process"] = True
                            current["process_title"] = current.get("process_title") or source_flow["process_title"]
                            known_steps = {(str(item.get("title", "")).casefold(), item.get("page_number")) for item in current.get("steps", [])}
                            for step in source_flow["steps"]:
                                if (step["title"].casefold(), step["page_number"]) not in known_steps:
                                    current.setdefault("steps", []).append(step)
                            module_done.setdefault(module, set()).add(batch_index)
                            results["reliability_report"]["warnings"].append(
                                "Process steps were reconstructed from an explicit source list or ordered sentences because the model did not return a valid structured flow."
                            )
                            results["process_flow"] = normalize_process_flow(
                                current, extraction.title
                            )
                            await save_progress()
                            continue
                    results["reliability_report"]["failed_modules"].append(f"{module}:{batch_index}")
                    results["reliability_report"]["warnings"].append(f"{module} analysis part {batch_index + 1} failed: {str(exc)}")
                    await save_progress()
                    stop_for_provider = stop_for_provider or _is_provider_failure(exc)
                if stop_for_provider:
                    break
            if stop_for_provider:
                for pending_index in range(batch_index, len(batches)):
                    if base_selected and pending_index not in done:
                        results["reliability_report"]["failed_batches"].append(pending_index)
                    for pending_module in module_selected:
                        if pending_index not in module_done.get(pending_module, set()):
                            results["reliability_report"]["failed_modules"].append(f"{pending_module}:{pending_index}")
                await save_progress()
                break

        source_sections = [
            {"text": section.text, "page_number": section.page_number}
            for section in extraction.sections
        ]
        osi_flow = _extract_osi_flow_steps(source_sections)
        if osi_flow:
            results["process_flow"] = osi_flow
            results["reliability_report"]["warnings"].append(
                "The complete OSI sender-to-receiver flow was reconstructed from explicit layer, medium, sender, and receiver evidence in the source."
            )
        results["process_flow"] = normalize_process_flow(results["process_flow"], extraction.title)
        if results["concept_map"].get("concepts"):
            check = validate_mermaid_syntax(_build_concept_mermaid(results["concept_map"]))
            results["concept_map"]["mermaid_syntax"] = check["cleaned"] if check["valid"] else ""
        results["reliability_report"]["failed_batches"] = sorted(set(results["reliability_report"]["failed_batches"]))
        results["reliability_report"]["failed_modules"] = sorted(set(results["reliability_report"]["failed_modules"]))
        results["reliability_report"]["module_batches"] = {
            name: sorted(module_done.get(name, set())) for name in module_selected
        }
        results["reliability_report"]["is_complete"] = not (
            results["reliability_report"]["failed_batches"] or results["reliability_report"]["failed_modules"]
        )
        return results

    @staticmethod
    async def refine_component(
        component_type: str,
        original_text: str,
        current_content: str,
        custom_instruction: str,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Refines a single analysis component based on user custom instructions.
        Preserves original text and returns revised content with new version.
        """
        prompt = f"""ROLE:
You are an expert document editor.

TASK:
Revise the following simplified component based strictly on the user's custom instruction.

CONTEXT:
Original Source Document Text:
\"\"\"
{original_text[:2500]}
\"\"\"

Current Simplified Version:
\"\"\"
{current_content}
\"\"\"

User Instruction:
\"{custom_instruction}\"

CONSTRAINTS:
- Do NOT introduce ungrounded claims or hallucinated facts.
- Follow the requested formatting (e.g. bullet points, simpler, shorter).
- Language: {language}

OUTPUT FORMAT:
Return only the revised content.
"""
        revised = await ollama_client.generate(prompt)
        return {
            "component_type": component_type,
            "instruction": custom_instruction,
            "revised_content": revised.strip(),
            "status": "success"
        }

analysis_service = AnalysisService()
