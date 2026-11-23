"""
Annotations router for FormEase.
Connected directly to Supabase PostgreSQL 'annotations' table.
Uses request-scoped authenticated Supabase client carrying the user's verified JWT.
Enforces strict document and user ownership verification.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from ...core.security import get_current_user
from ...core.database import get_user_db
import uuid
import datetime

router = APIRouter()

class AnnotationCreate(BaseModel):
    highlighted_text: Optional[str] = None
    note: str
    color: str = "#fef08a"
    page_number: int = 1

@router.get("/documents/{document_id}/annotations")
async def get_annotations(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]

    try:
        doc_check = db.table("documents").select("id").eq("id", document_id).eq("user_id", user_id).execute()
        if not (doc_check.data if hasattr(doc_check, "data") else []):
            raise HTTPException(status_code=404, detail="Document not found or access denied.")

        res = db.table("annotations")\
            .select("*")\
            .eq("document_id", document_id)\
            .eq("user_id", user_id)\
            .order("created_at")\
            .execute()
        
        return {"annotations": res.data if hasattr(res, "data") else []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

@router.post("/documents/{document_id}/annotations")
async def create_annotation(
    document_id: str,
    payload: AnnotationCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]

    try:
        doc_check = db.table("documents").select("id").eq("id", document_id).eq("user_id", user_id).execute()
        if not (doc_check.data if hasattr(doc_check, "data") else []):
            raise HTTPException(status_code=404, detail="Document not found or access denied.")

        ann_id = str(uuid.uuid4())
        record = {
            "id": ann_id,
            "document_id": document_id,
            "user_id": user_id,
            "highlighted_text": payload.highlighted_text,
            "note": payload.note,
            "color": payload.color,
            "page_number": payload.page_number,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat()
        }

        db.table("annotations").insert(record).execute()
        return record
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create annotation: {str(e)}")

@router.delete("/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]

    try:
        check = db.table("annotations")\
            .select("id")\
            .eq("id", annotation_id)\
            .eq("user_id", user_id)\
            .execute()
        if not (check.data if hasattr(check, "data") else []):
            raise HTTPException(status_code=404, detail="Annotation not found or access denied.")

        db.table("annotations")\
            .delete()\
            .eq("id", annotation_id)\
            .eq("user_id", user_id)\
            .execute()

        return {"status": "deleted", "annotation_id": annotation_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete annotation: {str(e)}")
