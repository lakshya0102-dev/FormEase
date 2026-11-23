"""
Documents router for FormEase.
Connected directly to Supabase PostgreSQL and Supabase Private Storage.
Uses request-scoped, authenticated Supabase client carrying the user's verified JWT.
Enforces strict user ownership and PostgreSQL document_status enum compliance.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response, status
from ...core.security import get_current_user
from ...core.database import get_user_db
from ...core.config import settings
from ...services.document_service import document_service
import uuid
import datetime

router = APIRouter()

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    # Enforce the configured limit while reading, not after buffering an
    # arbitrarily large request into memory.
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    contents_buffer = bytearray()
    while True:
        chunk = await file.read(min(64 * 1024, max_bytes + 1 - len(contents_buffer)))
        if not chunk:
            break
        contents_buffer.extend(chunk)
        if len(contents_buffer) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit."
            )
    contents = bytes(contents_buffer)
    file_name = file.filename or "uploaded-file"
    validation = document_service.validate_file(file_name, contents)
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation["error"])

    file_ext = validation["extension"]
    doc_id = str(uuid.uuid4())
    user_id = current_user["id"]
    storage_path = f"{user_id}/{doc_id}.{file_ext}"

    # Extract text before storing so unreadable files do not leave orphaned objects.
    try:
        processed = document_service.extract_and_chunk(file_name, contents, file_ext)
        extraction = processed["extraction"]
        chunks = processed["chunks"]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {str(e)}"
        )

    # Store the original only after extraction has produced usable text.
    try:
        db.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            path=storage_path,
            file=contents,
            file_options={"content-type": file.content_type or "application/octet-stream"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store document in private storage: {str(e)}"
        )

    # 3. Insert record into Supabase PostgreSQL documents table with initial status 'pending'
    doc_record = {
        "id": doc_id,
        "user_id": user_id,
        "title": file_name,
        "file_name": file_name,
        "file_type": file_ext,
        "file_size_bytes": len(contents),
        "storage_path": storage_path,
        "page_count": extraction.page_count,
        "status": "pending",
        "is_deleted": False,
        "deleted_at": None,
        "metadata": {"warnings": extraction.warnings},
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat()
    }

    try:
        db.table("documents").insert(doc_record).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error creating document record: {str(e)}"
        )

    # 4. Insert chunks into document_chunks table
    if chunks:
        chunk_rows = [
            {
                "id": str(uuid.uuid4()),
                "document_id": doc_id,
                "user_id": user_id,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "section_title": c.section_title,
                "content": c.content,
                "token_count": c.token_count,
                "created_at": datetime.datetime.utcnow().isoformat()
            }
            for c in chunks
        ]
        try:
            db.table("document_chunks").insert(chunk_rows).execute()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error saving document chunks: {str(e)}"
            )

    return {
        "document": doc_record,
        "chunk_count": len(chunks),
        "extraction_warnings": extraction.warnings
    }

@router.post("/paste")
async def paste_text_document(
    title: str = Form("Pasted Document"),
    text: str = Form(...),
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    if not text.strip():
        raise HTTPException(status_code=400, detail="Pasted text cannot be empty.")

    doc_id = str(uuid.uuid4())
    user_id = current_user["id"]
    text_bytes = text.encode("utf-8")
    storage_path = f"{user_id}/{doc_id}.txt"

    try:
        processed = document_service.extract_and_chunk(title, text_bytes, "text")
        extraction = processed["extraction"]
        chunks = processed["chunks"]
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Pasted text processing failed: {str(e)}")

    # Upload text only after validation and extraction succeed.
    try:
        db.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            path=storage_path,
            file=text_bytes,
            file_options={"content-type": "text/plain; charset=utf-8"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store pasted text in private storage: {str(e)}"
        )

    doc_record = {
        "id": doc_id,
        "user_id": user_id,
        "title": title,
        "file_name": f"{title}.txt",
        "file_type": "text",
        "file_size_bytes": len(text_bytes),
        "storage_path": storage_path,
        "page_count": 1,
        "status": "pending",
        "is_deleted": False,
        "deleted_at": None,
        "metadata": {},
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat()
    }

    try:
        db.table("documents").insert(doc_record).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error creating document record: {str(e)}"
        )

    if chunks:
        chunk_rows = [
            {
                "id": str(uuid.uuid4()),
                "document_id": doc_id,
                "user_id": user_id,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "section_title": c.section_title,
                "content": c.content,
                "token_count": c.token_count,
                "created_at": datetime.datetime.utcnow().isoformat()
            }
            for c in chunks
        ]
        try:
            db.table("document_chunks").insert(chunk_rows).execute()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error saving document chunks: {str(e)}"
            )

    return {
        "document": doc_record,
        "chunk_count": len(chunks),
        "extraction_warnings": []
    }

@router.get("")
async def list_documents(
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]
    try:
        res = db.table("documents")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("is_deleted", False)\
            .order("created_at", desc=True)\
            .execute()
        return {"documents": res.data if hasattr(res, "data") else []}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {str(e)}"
        )

@router.get("/trash")
async def list_trash(
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]
    try:
        res = db.table("documents")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("is_deleted", True)\
            .order("deleted_at", desc=True)\
            .execute()
        return {"documents": res.data if hasattr(res, "data") else []}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {str(e)}"
        )

@router.get("/{document_id}")
async def get_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]
    try:
        doc_res = db.table("documents")\
            .select("*")\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()
        
        doc_data = doc_res.data if hasattr(doc_res, "data") else []
        if not doc_data:
            raise HTTPException(status_code=404, detail="Document not found or access denied.")

        chunks_res = db.table("document_chunks")\
            .select("*")\
            .eq("document_id", document_id)\
            .eq("user_id", user_id)\
            .order("chunk_index")\
            .execute()

        chunks_data = chunks_res.data if hasattr(chunks_res, "data") else []
        return {"document": doc_data[0], "chunks": chunks_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document: {str(e)}"
        )

@router.get("/{document_id}/content")
async def get_document_content(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    """Streams a private original document after verifying its owner."""
    user_id = current_user["id"]
    try:
        doc_res = db.table("documents")\
            .select("title, file_type, storage_path")\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()
        documents = doc_res.data if hasattr(doc_res, "data") else []
        if not documents:
            raise HTTPException(status_code=404, detail="Document not found or access denied.")

        stored_document = documents[0]
        storage_path = stored_document.get("storage_path")
        if not storage_path:
            raise HTTPException(status_code=404, detail="Original file is not available in storage.")
        content = db.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(storage_path)
        media_type = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain; charset=utf-8",
            "text": "text/plain; charset=utf-8"
        }.get(stored_document.get("file_type"), "application/octet-stream")
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": "inline"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve original document: {str(e)}")

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]
    try:
        check = db.table("documents")\
            .select("id")\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()
        if not (check.data if hasattr(check, "data") else []):
            raise HTTPException(status_code=404, detail="Document not found or access denied.")

        db.table("documents")\
            .update({
                "is_deleted": True,
                "deleted_at": datetime.datetime.utcnow().isoformat()
            })\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()

        return {"status": "moved_to_trash", "document_id": document_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )

@router.post("/{document_id}/restore")
async def restore_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_user_db)
):
    user_id = current_user["id"]
    try:
        check = db.table("documents")\
            .select("id")\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()
        if not (check.data if hasattr(check, "data") else []):
            raise HTTPException(status_code=404, detail="Document not found or access denied.")

        db.table("documents")\
            .update({
                "is_deleted": False,
                "deleted_at": None
            })\
            .eq("id", document_id)\
            .eq("user_id", user_id)\
            .execute()

        return {"status": "restored", "document_id": document_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore document: {str(e)}"
        )
