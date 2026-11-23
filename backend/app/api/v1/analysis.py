"""
Analysis router for FormEase.
Connected directly to Supabase PostgreSQL:
- 'analyses' table
- 'analysis_components' table
- 'analysis_versions' table
Uses request-scoped authenticated Supabase client carrying the user's verified JWT.
Maintains valid document_status enum transitions ('pending' -> 'processing' -> 'completed' / 'failed').
"""
from typing import Optional
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.core.security import get_current_user
from backend.app.core.database import get_user_db
from backend.app.schemas.common import AnalyzeRequest, RefinementRequest
from backend.app.services.analysis_service import (
    analysis_service,
    is_generic_placeholder_text,
    normalize_process_flow,
)
from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
import uuid
import datetime

router = APIRouter()
_document_analysis_locks = {}


def _clean_saved_sections(sections):
    """Do not expose generic model placeholders from old or failed saved runs."""
    if not isinstance(sections, list):
        return []
    cleaned = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "").strip()
        explanation = str(section.get("simplified_explanation") or "").strip()
        if not heading or is_generic_placeholder_text(heading):
            continue
        if not explanation or is_generic_placeholder_text(explanation):
            continue
        cleaned.append(section)
    return cleaned


def _join_chunk_overlap(previous: str, following: str, max_overlap_words: int = 70) -> str:
    """Remove chunker-added overlap while reconstructing document text for analysis."""
    left, right = previous.split(), following.split()
    for size in range(min(max_overlap_words, len(left), len(right)), 0, -1):
        if [word.casefold() for word in left[-size:]] == [word.casefold() for word in right[:size]]:
            return " ".join(left + right[size:])
    return f"{previous}\n\n{following}" if previous else following

@router.post("/documents/{document_id}/analyze")
async def analyze_document_endpoint(
    document_id: str,
    payload: AnalyzeRequest,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    # Avoid duplicate billable inference jobs for the same document in this worker.
    lock = _document_analysis_locks.setdefault(document_id, asyncio.Lock())
    async with lock:
        return await _analyze_document_locked(document_id, payload, current_user, db)

async def _analyze_document_locked(
    document_id: str,
    payload: AnalyzeRequest,
    current_user: dict,
    db,
):
    user_id = current_user["id"]

    # 1. Verify document ownership
    try:
        doc_res = db.table("documents")\
            .select("*")\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()
        doc_data = doc_res.data if hasattr(doc_res, "data") else []
        if not doc_data:
            raise HTTPException(status_code=404, detail="Document not found or access denied.")
        doc = doc_data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")

    # 2. Update status to 'processing'
    try:
        db.table("documents")\
            .update({"status": "processing", "updated_at": datetime.datetime.utcnow().isoformat()})\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()
    except Exception:
        pass

    # 3. Retrieve chunks from Supabase
    try:
        chunks_res = db.table("document_chunks")\
            .select("*")\
            .eq("document_id", document_id)\
            .eq("user_id", user_id)\
            .order("chunk_index")\
            .execute()
        chunks = chunks_res.data if hasattr(chunks_res, "data") else []
        if not chunks:
            raise HTTPException(status_code=400, detail="Document has no text chunks to analyze.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error retrieving chunks: {str(e)}")

    # 4. Assemble Extraction Result
    sections = []
    for chunk in chunks:
        heading, page = chunk.get("section_title", "Section"), chunk.get("page_number", 1)
        if sections and sections[-1].heading == heading and sections[-1].page_number == page:
            sections[-1].text = _join_chunk_overlap(sections[-1].text, chunk["content"])
        else:
            sections.append(ExtractedSection(heading=heading, text=chunk["content"], page_number=page))
    full_text = "\n\n".join(section.text for section in sections)
    extraction = DocumentExtractionResult(
        title=doc["title"],
        full_text=full_text,
        sections=sections,
        page_count=doc.get("page_count", 1),
        warnings=doc.get("metadata", {}).get("warnings", []) if doc.get("metadata") else []
    )

    # Reuse the newest analysis so completed parts survive provider errors and retries.
    latest = []
    try:
        previous_res = db.table("analyses").select("*").eq("document_id", document_id).eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
        latest = previous_res.data if hasattr(previous_res, "data") else []
    except Exception:
        latest = []
    previous = latest[0] if latest else None
    prior_components = []
    if previous:
        try:
            prior_res = db.table("analysis_components").select("*").eq("analysis_id", previous["id"]).execute()
            prior_components = prior_res.data if hasattr(prior_res, "data") else []
        except Exception:
            prior_components = []
    prior_reliability = dict((previous or {}).get("reliability_report") or {})
    prior_reliability.pop("external_diagrams_progress", None)
    prior_reliability.pop("external_diagrams_status", None)
    requested_language, requested_depth = payload.language.value, payload.depth.value
    completed_batches = prior_reliability.get("completed_batches", []) if previous and previous.get("language") == requested_language and previous.get("depth") == requested_depth else []
    compatible_previous = bool(previous and previous.get("language") == requested_language and previous.get("depth") == requested_depth)
    prior_result = {
        "overview": (previous or {}).get("overview", {}),
        "summary": (previous or {}).get("summary", ""),
        "sections": prior_reliability.get("sections_progress", []),
        "process_flow": (previous or {}).get("process_flow", {}),
        "concept_map": prior_reliability.get("concept_map_progress", {"concepts": [], "relationships": [], "mermaid_syntax": ""}),
        "formulas": prior_reliability.get("formulas_progress", []),
        "revision_notes": prior_reliability.get("revision_notes_progress", []),
        "key_information": (previous or {}).get("key_information", {}),
        "definitions": (previous or {}).get("definitions", []),
        "recommendations": (previous or {}).get("recommendations", []),
    }
    completed_module_batches = prior_reliability.get("module_batches", {}) if previous and previous.get("language") == requested_language and previous.get("depth") == requested_depth else {}
    if not prior_result["sections"]:
        prior_result["sections"] = [
            {"heading": c.get("heading", ""), "page_number": c.get("source_page_start", 1),
             "simplified_explanation": c.get("simplified_content", ""), "key_points": [],
             "potential_risks": [], "risk_level": c.get("risk_level", "low")}
            for c in prior_components if c.get("component_type") == "section"
        ]
    requested_components = payload.components or ["summary", "sections", "process", "key_info", "definitions", "recommendations", "diagrams"]
    concept_map_requested = "concept_map" in requested_components
    if concept_map_requested:
        completed_module_batches = {**completed_module_batches, "concept_map": []}
    requested_modules = []
    if "process" in requested_components or "diagrams" in requested_components:
        requested_modules.append("process_flow")
    if "diagrams" in requested_components or concept_map_requested:
        requested_modules.append("concept_map")
    if "revision_notes" in requested_components or ("summary" in requested_components and "key_info" in requested_components):
        requested_modules.append("revision_notes")
    if "key_info" in requested_components:
        requested_modules.extend(("formulas", "key_information"))
    if "definitions" in requested_components:
        requested_modules.append("definitions")
    if "recommendations" in requested_components:
        requested_modules.append("recommendations")
    requested_modules = list(dict.fromkeys(requested_modules))
    base_complete = not (set(requested_components) & {"summary", "sections"}) or len(completed_batches) >= prior_reliability.get("total_batches", 0)
    modules_complete = all(len(completed_module_batches.get(name, [])) >= prior_reliability.get("total_batches", 0) for name in requested_modules)
    if (previous and not concept_map_requested and base_complete and modules_complete
            and prior_reliability.get("is_complete")
            and set(prior_reliability.get("selected_components", [])) == set(requested_components)):
        for section in prior_result["sections"]:
            match = next((c for c in prior_components if c.get("component_type") == "section"
                          and c.get("heading") == section.get("heading")
                          and c.get("source_page_start", 1) == section.get("page_number", 1)), None)
            if match:
                section["component_id"] = match["id"]
        prior_result["component_ids"] = {c.get("component_type"): c.get("id") for c in prior_components if c.get("component_type") != "section"}
        return {"status": "completed", "analysis_id": previous["id"], "analysis": {**prior_result, "language": requested_language, "depth": requested_depth, "reliability_report": prior_reliability}}

    analysis_id = previous["id"] if previous else str(uuid.uuid4())
    # 5. Execute analysis; persist every finished part to make retries resumable.
    async def persist_progress(progress):
        nonlocal previous
        report = dict(progress.get("reliability_report", {}))
        report["sections_progress"] = progress.get("sections", [])
        report["concept_map_progress"] = progress.get("concept_map", {})
        report["formulas_progress"] = progress.get("formulas", [])
        report["revision_notes_progress"] = progress.get("revision_notes", [])
        report["module_batches"] = progress.get("reliability_report", {}).get("module_batches", {})
        record = {
            "id": analysis_id, "document_id": document_id, "user_id": user_id,
            "language": requested_language, "depth": requested_depth,
            "overview": progress.get("overview", {}), "summary": progress.get("summary", ""),
            "process_flow": normalize_process_flow(progress.get("process_flow", {}), doc.get("title", "")),
            "key_information": progress.get("key_information", {}),
            "definitions": progress.get("definitions", []), "recommendations": progress.get("recommendations", []),
            "reliability_report": report, "updated_at": datetime.datetime.utcnow().isoformat()
        }
        if previous:
            db.table("analyses").update(record).eq("id", analysis_id).eq("user_id", user_id).execute()
        else:
            record["created_at"] = datetime.datetime.utcnow().isoformat()
            db.table("analyses").insert(record).execute()
            # The row now exists for subsequent progress updates in this request.
            previous = {"id": analysis_id}

    try:
        result = await analysis_service.analyze_document(
            extraction=extraction,
            language=requested_language,
            depth=requested_depth,
            selected_components=payload.components,
            existing_result=prior_result if compatible_previous else None,
            completed_batches=completed_batches,
            completed_module_batches=completed_module_batches,
            progress_callback=persist_progress,
        )
    except Exception as e:
        # Mark as failed if entire pipeline crashes
        db.table("documents")\
            .update({"status": "failed", "updated_at": datetime.datetime.utcnow().isoformat()})\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()
        raise HTTPException(status_code=500, detail=f"Document analysis failed: {str(e)}")

    # 6. Persist to Supabase 'analyses' table
    analysis_record = {
        "id": analysis_id,
        "document_id": document_id,
        "user_id": user_id,
        "language": payload.language.value,
        "depth": payload.depth.value,
        "overview": result.get("overview", {}),
        "summary": result.get("summary", ""),
        "process_flow": normalize_process_flow(result.get("process_flow", {}), doc.get("title", "")),
        "key_information": result.get("key_information", {}),
        "definitions": result.get("definitions", []),
        "recommendations": result.get("recommendations", []),
        "reliability_report": {**result.get("reliability_report", {}), "sections_progress": result.get("sections", []),
                               "concept_map_progress": result.get("concept_map", {}), "formulas_progress": result.get("formulas", []),
                               "revision_notes_progress": result.get("revision_notes", [])},
        "created_at": (previous or {}).get("created_at", datetime.datetime.utcnow().isoformat()),
        "updated_at": datetime.datetime.utcnow().isoformat()
    }

    try:
        if previous and previous.get("created_at"):
            db.table("analyses").update(analysis_record).eq("id", analysis_id).eq("user_id", user_id).execute()
        else:
            db.table("analyses").upsert(analysis_record).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error saving analysis: {str(e)}")

    # Persist a refinable summary as well as the per-section components.
    component_ids = {}
    if result.get("summary"):
        try:
            existing_summary = next((c for c in prior_components if c.get("component_type") == "summary"), None)
            summary_component_id = existing_summary.get("id") if existing_summary else str(uuid.uuid4())
            summary_record = {
                "id": summary_component_id,
                "analysis_id": analysis_id,
                "component_type": "summary",
                "heading": "Executive Summary",
                "original_text": full_text[:10000],
                "simplified_content": result["summary"],
                "source_page_start": 1,
                "created_at": (existing_summary or {}).get("created_at", datetime.datetime.utcnow().isoformat())
            }
            if existing_summary:
                db.table("analysis_components").update(summary_record).eq("id", summary_component_id).execute()
            else:
                db.table("analysis_components").insert(summary_record).execute()
            component_ids["summary"] = summary_component_id
        except Exception:
            pass

    # Persist individual section components into 'analysis_components'.
    for sec in result.get("sections", []):
        try:
            existing_section = next((c for c in prior_components if c.get("component_type") == "section"
                                     and c.get("heading") == sec.get("heading")
                                     and c.get("source_page_start", 1) == sec.get("page_number", 1)), None)
            section_component_id = existing_section.get("id") if existing_section else str(uuid.uuid4())
            section_record = {
                "id": section_component_id,
                "analysis_id": analysis_id,
                "component_type": "section",
                "heading": sec.get("heading", ""),
                "original_text": next(
                    (source.text for source in extraction.sections if source.heading == sec.get("heading")),
                    ""
                )[:10000],
                "simplified_content": sec.get("simplified_explanation", ""),
                "source_page_start": sec.get("page_number", 1),
                "risk_level": sec.get("risk_level", "low"),
                "created_at": (existing_section or {}).get("created_at", datetime.datetime.utcnow().isoformat())
            }
            if existing_section:
                db.table("analysis_components").update(section_record).eq("id", section_component_id).execute()
            else:
                db.table("analysis_components").insert(section_record).execute()
            sec["component_id"] = section_component_id
        except Exception:
            pass

    result["component_ids"] = component_ids

    # 8. Partial analyses remain retryable and are never marked complete.
    is_complete = bool(result.get("reliability_report", {}).get("is_complete"))
    try:
        db.table("documents")\
            .update({"status": "completed" if is_complete else "failed", "updated_at": datetime.datetime.utcnow().isoformat()})\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()
    except Exception:
        pass

    return {"status": "completed" if is_complete else "partial", "analysis_id": analysis_id, "analysis": result}

@router.get("/documents/{document_id}/analysis")
async def get_document_analysis(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]
    try:
        doc_res = db.table("documents").select("id, title").eq("id", document_id).eq("user_id", user_id).execute()
        document_rows = doc_res.data if hasattr(doc_res, "data") else []
        if not document_rows:
            raise HTTPException(status_code=404, detail="Document not found or access denied.")
        document_title = document_rows[0].get("title", "")

        res = db.table("analyses")\
            .select("*")\
            .eq("document_id", document_id)\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()

        analyses = res.data if hasattr(res, "data") else []
        if not analyses:
            raise HTTPException(status_code=404, detail="Analysis not found or still processing.")

        analysis = analyses[0]
        analysis["process_flow"] = normalize_process_flow(
            analysis.get("process_flow"),
            document_title,
        )

        comps_res = db.table("analysis_components")\
            .select("*")\
            .eq("analysis_id", analysis["id"])\
            .order("created_at")\
            .execute()
        comps = comps_res.data if hasattr(comps_res, "data") else []

        sections = analysis.get("reliability_report", {}).get("sections_progress") or [
            {
                "id": c.get("id"),
                "component_id": c.get("id"),
                "heading": c.get("heading"),
                "simplified_explanation": c.get("simplified_content"),
                "page_number": c.get("source_page_start", 1),
                "risk_level": c.get("risk_level", "low")
            }
            for c in comps if c.get("component_type") == "section"
        ]
        sections = _clean_saved_sections(sections)
        analysis["sections"] = sections
        analysis["concept_map"] = analysis.get("reliability_report", {}).get("concept_map_progress", {"concepts": [], "relationships": [], "mermaid_syntax": ""})
        analysis["formulas"] = analysis.get("reliability_report", {}).get("formulas_progress", [])
        analysis["revision_notes"] = analysis.get("reliability_report", {}).get("revision_notes_progress", [])
        report = analysis.setdefault("reliability_report", {})
        report.pop("external_diagrams_progress", None)
        report.pop("external_diagrams_status", None)
        # Older saved runs recorded one completion bit per oversized batch and
        # did not track advanced modules individually. Expose them as retryable
        # so students can regenerate the new focused module outputs.
        if report.get("is_complete") and report.get("total_batches") and not report.get("module_batches"):
            selected = set(report.get("selected_components") or ["summary", "sections", "process", "key_info", "definitions", "recommendations", "diagrams"])
            modules = []
            if "process" in selected or "diagrams" in selected:
                modules.append("process_flow")
            if "diagrams" in selected:
                modules.append("concept_map")
            if "revision_notes" in selected or ("summary" in selected and "key_info" in selected):
                modules.append("revision_notes")
            if "key_info" in selected:
                modules.extend(("formulas", "key_information"))
            if "definitions" in selected:
                modules.append("definitions")
            if "recommendations" in selected:
                modules.append("recommendations")
            report["module_batches"] = {}
            report["selected_modules"] = list(dict.fromkeys(modules))
            report["failed_modules"] = [f"{module}:{index}" for module in report["selected_modules"] for index in range(report["total_batches"])]
            report["is_complete"] = False
            report.setdefault("warnings", []).append("Advanced learning modules need regeneration using focused local analysis requests.")
        analysis["component_ids"] = {
            component.get("component_type"): component.get("id")
            for component in comps
            if component.get("component_type") != "section"
        }

        return {"document_id": document_id, "analysis": analysis}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

@router.post("/analysis/{component_id}/regenerate")
async def refine_analysis_component(
    component_id: str,
    payload: RefinementRequest,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]

    try:
        comp_res = db.table("analysis_components")\
            .select("*, analyses!inner(user_id, document_id)")\
            .eq("id", component_id)\
            .eq("analyses.user_id", user_id)\
            .execute()
        comp_data = comp_res.data if hasattr(comp_res, "data") else []
        if not comp_data:
            raise HTTPException(status_code=404, detail="Component not found or access denied.")
        comp = comp_data[0]

        revised = await analysis_service.refine_component(
            component_type=comp.get("component_type", "section"),
            original_text=comp.get("original_text") or comp.get("simplified_content", ""),
            current_content=comp.get("simplified_content", ""),
            custom_instruction=payload.instruction
        )

        version_row = {
            "id": str(uuid.uuid4()),
            "component_id": component_id,
            "instruction": payload.instruction,
            "revised_content": revised.get("revised_content", ""),
            "version_number": 1,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        previous_versions = db.table("analysis_versions")\
            .select("version_number")\
            .eq("component_id", component_id)\
            .order("version_number", desc=True)\
            .limit(1)\
            .execute()
        existing_versions = previous_versions.data if hasattr(previous_versions, "data") else []
        if existing_versions:
            version_row["version_number"] = existing_versions[0]["version_number"] + 1
        db.table("analysis_versions").insert(version_row).execute()

        db.table("analysis_components")\
            .update({"simplified_content": revised.get("revised_content", "")})\
            .eq("id", component_id)\
            .execute()

        if comp.get("component_type") == "summary":
            db.table("analyses")\
                .update({"summary": revised.get("revised_content", ""), "updated_at": datetime.datetime.utcnow().isoformat()})\
                .eq("id", comp.get("analysis_id"))\
                .eq("user_id", user_id)\
                .execute()

        return {
            "component_id": component_id,
            "revised_content": revised.get("revised_content", ""),
            "instruction": payload.instruction
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Refinement failed: {str(e)}")
