"""
Export router for FormEase.
Connected directly to Supabase to retrieve document analysis for export.
Uses request-scoped authenticated Supabase client carrying the user's verified JWT.
Generates PDF and Markdown exports.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from backend.app.core.security import get_current_user
from backend.app.core.database import get_user_db
from backend.app.services.exporter import export_service

router = APIRouter()

@router.get("/documents/{document_id}/export/pdf")
async def export_analysis_pdf(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]

    try:
        doc_res = db.table("documents").select("title").eq("id", document_id).eq("user_id", user_id).execute()
        doc_data = doc_res.data if hasattr(doc_res, "data") else []
        if not doc_data:
            raise HTTPException(status_code=404, detail="Document not found or access denied.")
        doc_title = doc_data[0]["title"]

        analysis_res = db.table("analyses")\
            .select("*")\
            .eq("document_id", document_id)\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        analyses = analysis_res.data if hasattr(analysis_res, "data") else []
        if not analyses:
            raise HTTPException(status_code=400, detail="Document analysis must be generated before exporting.")

        analysis = analyses[0]

        comps_res = db.table("analysis_components")\
            .select("*")\
            .eq("analysis_id", analysis["id"])\
            .execute()
        comps = comps_res.data if hasattr(comps_res, "data") else []
        reliability = analysis.get("reliability_report", {})
        analysis["sections"] = reliability.get("sections_progress") or [
            {
                "heading": c.get("heading"),
                "simplified_explanation": c.get("simplified_content"),
                "page_number": c.get("source_page_start", 1)
            }
            for c in comps if c.get("component_type") == "section"
        ]
        analysis["concept_map"] = reliability.get("concept_map_progress", {})
        analysis["formulas"] = reliability.get("formulas_progress", [])
        analysis["revision_notes"] = reliability.get("revision_notes_progress", [])

        pdf_bytes = export_service.generate_pdf(doc_title, analysis)
        safe_title = doc_title.replace(" ", "_").replace("/", "_")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=FormEase_Analysis_{safe_title}.pdf"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.get("/documents/{document_id}/export/markdown")
async def export_analysis_markdown(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]

    try:
        doc_res = db.table("documents").select("title").eq("id", document_id).eq("user_id", user_id).execute()
        doc_data = doc_res.data if hasattr(doc_res, "data") else []
        if not doc_data:
            raise HTTPException(status_code=404, detail="Document not found or access denied.")
        doc_title = doc_data[0]["title"]

        analysis_res = db.table("analyses")\
            .select("*")\
            .eq("document_id", document_id)\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        analyses = analysis_res.data if hasattr(analysis_res, "data") else []
        if not analyses:
            raise HTTPException(status_code=400, detail="Document analysis must be generated before exporting.")

        analysis = analyses[0]

        comps_res = db.table("analysis_components")\
            .select("*")\
            .eq("analysis_id", analysis["id"])\
            .execute()
        comps = comps_res.data if hasattr(comps_res, "data") else []
        reliability = analysis.get("reliability_report", {})
        analysis["sections"] = reliability.get("sections_progress") or [
            {
                "heading": c.get("heading"),
                "simplified_explanation": c.get("simplified_content"),
                "page_number": c.get("source_page_start", 1)
            }
            for c in comps if c.get("component_type") == "section"
        ]
        analysis["concept_map"] = reliability.get("concept_map_progress", {})
        analysis["formulas"] = reliability.get("formulas_progress", [])
        analysis["revision_notes"] = reliability.get("revision_notes_progress", [])

        md_text = export_service.generate_markdown(doc_title, analysis)
        return {"document_id": document_id, "markdown": md_text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
