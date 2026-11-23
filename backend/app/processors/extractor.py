"""
Document extraction service for FormEase.
Extracts structured text from PDF (PyMuPDF), DOCX (python-docx), TXT, and Pasted Text.
Retains page numbers, reading order, and handles extraction warnings safely.
"""
from typing import List, Dict, Any, Optional
import io
import re
from ..core.config import settings

class ExtractedSection:
    def __init__(self, heading: str, text: str, page_number: int = 1):
        self.heading = heading
        self.text = text
        self.page_number = page_number

    def to_dict(self) -> Dict[str, Any]:
        return {
            "heading": self.heading,
            "text": self.text,
            "page_number": self.page_number
        }

class DocumentExtractionResult:
    def __init__(
        self,
        title: str,
        full_text: str,
        sections: List[ExtractedSection],
        page_count: int,
        warnings: Optional[List[str]] = None
    ):
        self.title = title
        self.full_text = full_text
        self.sections = sections
        self.page_count = page_count
        self.warnings = warnings or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "page_count": self.page_count,
            "sections": [s.to_dict() for s in self.sections],
            "warnings": self.warnings,
            "total_character_count": len(self.full_text)
        }

def clean_extracted_text(text: str) -> str:
    """
    Cleans extraction artifacts without altering original meaning.
    Removes excessive empty lines, normalizes whitespace and removes page breaks.
    """
    if not text:
        return ""
    # Normalize newline sequences
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse 3 or more consecutive newlines into 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Collapse multiple spaces and tabs into single space
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.split('\n')]
    return '\n'.join(lines).strip()


def infer_section_heading(text: str, page_number: int = 1) -> str:
    """Infer a usable source heading without replacing real headings with placeholders."""
    lines = [line.strip() for line in clean_extracted_text(text).splitlines() if line.strip()]
    if not lines:
        return f"Page {page_number}"

    first = lines[0]
    numbered = re.match(r"^(?:\d+(?:\.\d)*[\s.):-]+|(?:Chapter|Section|Part)\s+\d+[\s:.-]*)", first, re.IGNORECASE)
    short = len(first) <= 120 and len(first.split()) <= 16
    heading_like = (
        bool(numbered)
        or (short and len(lines) > 1 and (
            first.isupper()
            or re.match(r"^[A-Z][A-Za-z0-9 &'(),/-]*$", first) is not None
        ))
    )
    if heading_like:
        return re.sub(r"\s+", " ", first).strip(" :-")

    if len(first) <= 100:
        words = re.findall(r"\b[\w'-]+\b", first)
        if words:
            title = " ".join(words[:8]).strip()
            return title if title else f"Page {page_number}"
    return f"Page {page_number}"

def extract_pdf(file_bytes: bytes, file_name: str = "document.pdf") -> DocumentExtractionResult:
    """
    Extracts text page-by-page from PDF using PyMuPDF (fitz), with graceful fallback.
    """
    warnings = []
    sections = []
    full_text_parts = []
    page_count = 0

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if doc.is_encrypted and doc.needs_pass:
            doc.close()
            return DocumentExtractionResult(file_name, "", [], 0, ["This PDF is password-protected and cannot be read without its password."])
        page_count = len(doc)
        
        if page_count == 0:
            return DocumentExtractionResult(file_name, "", [], 0, ["PDF has zero pages."])

        ocr_unavailable_reported = False
        ocr_engine_failed = False
        for page_idx in range(page_count):
            page_num = page_idx + 1
            page = doc[page_idx]
            page_text = page.get_text("text", sort=True) or ""
            cleaned_page = clean_extracted_text(page_text)

            # Only rasterize pages without a usable text layer. PyMuPDF renders
            # one page at a time so scans do not create a document-sized image set.
            if settings.OCR_ENABLED and not ocr_engine_failed and len(cleaned_page) < settings.OCR_MIN_TEXT_CHARS:
                try:
                    import pytesseract
                    from PIL import Image
                    page_rect = page.rect
                    max_side_points = max(page_rect.width, page_rect.height, 1)
                    scale = min(200 / 72, 2400 / max_side_points)
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
                    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                    ocr_text = pytesseract.image_to_string(image, lang=settings.OCR_LANGUAGE)
                    cleaned_page = clean_extracted_text(ocr_text)
                    if cleaned_page:
                        warnings.append(f"Page {page_num} was read using local OCR; verify recognition quality.")
                except ImportError:
                    if not ocr_unavailable_reported:
                        warnings.append("Scanned PDF pages need local OCR. Install pytesseract, Pillow, and the Tesseract OCR engine to read them.")
                        ocr_unavailable_reported = True
                except Exception as e:
                    # Do not surface local paths or OCR command details.
                    if type(e).__name__ == "TesseractNotFoundError" or isinstance(e, FileNotFoundError):
                        ocr_engine_failed = True
                        if not ocr_unavailable_reported:
                            warnings.append("Tesseract is not installed or not available to the backend; scanned pages may be incomplete.")
                            ocr_unavailable_reported = True
                    else:
                        warnings.append(f"Local OCR failed on page {page_num}; that page may be incomplete.")
            
            if cleaned_page:
                full_text_parts.append(cleaned_page)
                sections.append(ExtractedSection(
                    heading=infer_section_heading(cleaned_page, page_num),
                    text=cleaned_page,
                    page_number=page_num
                ))
            else:
                warnings.append(f"Page {page_num} contains no extractable text layer (may be scanned).")
        
        doc.close()
    except ImportError:
        # Fallback if fitz is not installed in current environment
        warnings.append("PyMuPDF not installed in environment; using pure-python fallback.")
        text_content = file_bytes.decode('utf-8', errors='ignore')
        cleaned = clean_extracted_text(text_content)
        sections.append(ExtractedSection(heading="Full Document", text=cleaned, page_number=1))
        full_text_parts.append(cleaned)
        page_count = 1
    except Exception as e:
            warnings.append("PDF extraction failed; the file may be corrupted or unsupported.")

    full_text = "\n\n".join(full_text_parts)
    if not full_text.strip():
        warnings.append("No text could be extracted from this PDF document.")

    return DocumentExtractionResult(
        title=file_name,
        full_text=full_text,
        sections=sections,
        page_count=max(1, page_count),
        warnings=warnings
    )

def extract_docx(file_bytes: bytes, file_name: str = "document.docx") -> DocumentExtractionResult:
    """
    Extracts paragraphs and headings from DOCX using python-docx.
    """
    warnings = ["DOCX page numbers are not available from the document structure; source references use document order rather than printed pages."]
    sections = []
    full_text_parts = []

    try:
        import docx
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        doc = docx.Document(io.BytesIO(file_bytes))
        current_heading = "Introduction"
        current_paras = []

        for child in doc.element.body.iterchildren():
            if child.tag.endswith("}p"):
                paragraph = Paragraph(child, doc)
                text = paragraph.text.strip()
                if not text:
                    continue
                if paragraph.style and paragraph.style.name.startswith("Heading"):
                    if current_paras:
                        section_text = "\n".join(current_paras)
                        sections.append(ExtractedSection(current_heading, clean_extracted_text(section_text), 1))
                        full_text_parts.append(section_text)
                        current_paras = []
                    current_heading = text
                else:
                    style_name = paragraph.style.name if paragraph.style else ""
                    if style_name.startswith("List Bullet"):
                        text = f"• {text}"
                    elif style_name.startswith("List Number"):
                        text = f"1. {text}"
                    current_paras.append(text)
            elif child.tag.endswith("}tbl"):
                table = Table(child, doc)
                rows = [[clean_extracted_text(cell.text) for cell in row.cells] for row in table.rows]
                if rows:
                    current_paras.append("\n".join(" | ".join(row) for row in rows))

        if current_paras:
            section_text = "\n".join(current_paras)
            sections.append(ExtractedSection(
                heading=current_heading,
                text=clean_extracted_text(section_text),
                page_number=1
            ))
            full_text_parts.append(section_text)

    except ImportError:
        warnings.append("python-docx not installed; fallback applied.")
        text_content = file_bytes.decode('utf-8', errors='ignore')
        cleaned = clean_extracted_text(text_content)
        sections.append(ExtractedSection(heading="Full Document", text=cleaned, page_number=1))
        full_text_parts.append(cleaned)
    except Exception as e:
        warnings.append(f"DOCX extraction error: {str(e)}")

    full_text = clean_extracted_text("\n\n".join(full_text_parts))
    return DocumentExtractionResult(
        title=file_name,
        full_text=full_text,
        sections=sections,
        page_count=1,
        warnings=warnings
    )

def extract_txt(file_bytes: bytes, file_name: str = "document.txt") -> DocumentExtractionResult:
    """
    Extracts text from TXT file with encoding detection.
    """
    encodings = ['utf-8', 'latin-1', 'cp1252', 'utf-16']
    raw_text = ""
    warnings = []

    for enc in encodings:
        try:
            raw_text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if not raw_text:
        raw_text = file_bytes.decode('utf-8', errors='replace')
        warnings.append("Used lossy encoding replacement for TXT decoding.")

    cleaned = clean_extracted_text(raw_text)
    sections = [ExtractedSection(heading=infer_section_heading(cleaned, 1), text=cleaned, page_number=1)]

    return DocumentExtractionResult(
        title=file_name,
        full_text=cleaned,
        sections=sections,
        page_count=1,
        warnings=warnings
    )

def extract_pasted_text(text: str, title: str = "Pasted Text") -> DocumentExtractionResult:
    """
    Handles user-pasted text directly without physical files.
    """
    cleaned = clean_extracted_text(text)
    sections = [ExtractedSection(heading=infer_section_heading(cleaned, 1), text=cleaned, page_number=1)]
    return DocumentExtractionResult(
        title=title,
        full_text=cleaned,
        sections=sections,
        page_count=1,
        warnings=[]
    )
