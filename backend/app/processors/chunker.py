"""
Document chunking engine for FormEase.
Splits extracted sections into manageable chunks while preserving:
- Document ID and Chunk Index
- Page number and section heading
- Token count approximation and configurable overlap
"""
from typing import List, Dict, Any
from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection

class DocumentChunk:
    def __init__(
        self,
        chunk_index: int,
        content: str,
        page_number: int,
        section_title: str,
        token_count: int
    ):
        self.chunk_index = chunk_index
        self.content = content
        self.page_number = page_number
        self.section_title = section_title
        self.token_count = token_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_index": self.chunk_index,
            "content": self.content,
            "page_number": self.page_number,
            "section_title": self.section_title,
            "token_count": self.token_count
        }

def approximate_token_count(text: str) -> int:
    """
    Approximates tokens (roughly 1 token per 4 characters or 0.75 words).
    """
    if not text:
        return 0
    words = text.split()
    return int(len(words) * 1.3)

def chunk_document(
    extraction: DocumentExtractionResult,
    target_tokens: int = 650,
    overlap_tokens: int = 80
) -> List[DocumentChunk]:
    """
    Recursively chunks sections into chunks respecting boundaries and overlap.
    Retains page and section metadata on each chunk.
    """
    chunks: List[DocumentChunk] = []
    chunk_counter = 0

    target_words = int(target_tokens / 1.3)
    overlap_words = int(overlap_tokens / 1.3)

    for section in extraction.sections:
        words = section.text.split()
        if not words:
            continue

        if len(words) <= target_words:
            chunk_counter += 1
            chunks.append(DocumentChunk(
                chunk_index=chunk_counter,
                content=section.text,
                page_number=section.page_number,
                section_title=section.heading,
                token_count=approximate_token_count(section.text)
            ))
            continue

        # Split with overlap
        start_idx = 0
        while start_idx < len(words):
            end_idx = min(start_idx + target_words, len(words))
            chunk_words = words[start_idx:end_idx]
            chunk_text = " ".join(chunk_words)

            chunk_counter += 1
            chunks.append(DocumentChunk(
                chunk_index=chunk_counter,
                content=chunk_text,
                page_number=section.page_number,
                section_title=section.heading,
                token_count=approximate_token_count(chunk_text)
            ))

            if end_idx >= len(words):
                break
            start_idx += (target_words - overlap_words)

    return chunks
