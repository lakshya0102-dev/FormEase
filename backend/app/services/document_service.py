"""
Document Service for FormEase.
Handles document validation, file ingestion, text extraction, chunking, and storage.
"""
from typing import Dict, Any, List, Optional
import os
import uuid
from backend.app.core.config import settings
from backend.app.processors.extractor import (
    extract_pdf,
    extract_docx,
    extract_txt,
    extract_pasted_text,
    DocumentExtractionResult
)
from backend.app.processors.chunker import chunk_document, DocumentChunk

class DocumentService:
    @staticmethod
    def validate_file(file_name: str, file_bytes: bytes) -> Dict[str, Any]:
        """
        Validates file size, extension, non-emptiness, and basic signatures.
        """
        if not file_bytes or len(file_bytes) == 0:
            return {"valid": False, "error": "The uploaded file is empty (0 bytes)."}

        size_mb = len(file_bytes) / (1024 * 1024)
        if size_mb > settings.MAX_UPLOAD_SIZE_MB:
            return {
                "valid": False,
                "error": f"File size ({size_mb:.1f} MB) exceeds maximum allowed limit of {settings.MAX_UPLOAD_SIZE_MB} MB."
            }

        ext = file_name.split(".")[-1].lower() if "." in file_name else ""
        if ext not in settings.supported_extensions_list:
            return {
                "valid": False,
                "error": f"Unsupported file extension '.{ext}'. Supported formats: {settings.SUPPORTED_FILE_EXTENSIONS}."
            }

        # Check binary headers for safety
        if ext == "pdf" and not file_bytes.startswith(b"%PDF-"):
            return {"valid": False, "error": "Invalid or corrupted PDF file header."}

        return {"valid": True, "extension": ext, "size_bytes": len(file_bytes)}

    @staticmethod
    def extract_and_chunk(file_name: str, file_bytes: bytes, file_type: str) -> Dict[str, Any]:
        """
        Runs extraction and chunking pipeline.
        Returns extraction result and chunks list.
        """
        file_type = file_type.lower()
        if file_type == "pdf":
            extraction = extract_pdf(file_bytes, file_name)
        elif file_type == "docx":
            extraction = extract_docx(file_bytes, file_name)
        elif file_type == "txt":
            extraction = extract_txt(file_bytes, file_name)
        elif file_type in ("text", "pasted"):
            text_str = file_bytes.decode("utf-8", errors="replace")
            extraction = extract_pasted_text(text_str, file_name)
        else:
            raise ValueError(f"Unsupported document type: {file_type}")

        if not extraction.full_text.strip():
            detail = " ".join(extraction.warnings) or "The document contains no extractable text."
            raise ValueError(f"No readable text was extracted. {detail}")

        chunks = chunk_document(
            extraction,
            target_tokens=settings.DEFAULT_CHUNK_SIZE,
            overlap_tokens=settings.DEFAULT_CHUNK_OVERLAP
        )

        return {
            "extraction": extraction,
            "chunks": chunks
        }

document_service = DocumentService()
