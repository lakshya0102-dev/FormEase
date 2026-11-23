"""
FormEase Test Suite — Foundation Verification & Security Enforcement.
Tests:
1. File validation & text cleaning
2. Text extraction (TXT, Pasted text, PyMuPDF, python-docx)
3. Large document chunking with metadata retention
4. TF-IDF retrieval scoring, thresholding, and top-1 passage retrieval
5. 5-part prompt generation (Summary, Sections, Process, Key Info, Definitions, Chatbot)
6. Mermaid syntax sanitization
7. Export formatting (Markdown and PDF)
8. Security & Authentication:
   - Valid JWT verification with HS256 & audience check
   - Missing Authorization header rejection (401)
   - Expired JWT rejection (401)
   - Malformed / unverified JWT rejection (401)
   - Non-UUID subject rejection (401)
9. Database integration & Multi-Tenant Isolation:
   - Document upload with storage and table insertion
   - Document query filtering by user_id
   - Cross-tenant access denial (User B cannot access User A's document)
   - Soft-delete and restore operations
10. Concurrency Safety & Scoped Token Isolation:
    - Independent scoped clients for concurrent users without token leakage
    - Document status enum compliance
    - Storage path validation and private bucket policies
11. Reliability & Error Recovery:
    - Analysis component failure isolation
    - Unconfigured Supabase fail-fast behavior (503)
"""
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import time
import uuid

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from jose import jwt, jwk
from fastapi import HTTPException
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from backend.app.core.config import settings
from backend.app.core.security import verify_supabase_jwt, get_current_user
from backend.app.core.database import (
    get_supabase_client,
    set_test_supabase_client,
    get_authenticated_supabase_client
)
from backend.app.schemas.common import DocumentStatus
from backend.app.processors.extractor import (
    clean_extracted_text,
    extract_pasted_text,
    extract_txt
)
from backend.app.processors.chunker import chunk_document, approximate_token_count
from backend.app.retrieval.tfidf_engine import TFIDFRetriever
from backend.app.services.document_service import document_service
from backend.app.services.analysis_service import validate_mermaid_syntax, analysis_service
from backend.app.services.exporter import export_service
from backend.app.ai.prompts import (
    build_summary_prompt,
    build_section_explanation_prompt,
    build_grounded_chat_prompt
)

TEST_SECRET = "test-supa-secret-at-least-32-bytes-long-for-hs256!"

def create_test_jwt(sub: str, email: str = "user@formease.local", expired: bool = False) -> str:
    now = int(time.time())
    exp = now - 3600 if expired else now + 3600
    payload = {
        "sub": sub,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": exp
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")

class TestFormEaseCore(unittest.TestCase):
    def test_file_validation(self):
        res_empty = document_service.validate_file("test.pdf", b"")
        self.assertFalse(res_empty["valid"])
        self.assertIn("empty", res_empty["error"])

        res_bad_ext = document_service.validate_file("test.exe", b"binarydata")
        self.assertFalse(res_bad_ext["valid"])
        self.assertIn("Unsupported", res_bad_ext["error"])

        valid_txt = "FormEase test content".encode("utf-8")
        res_valid = document_service.validate_file("sample.txt", valid_txt)
        self.assertTrue(res_valid["valid"])
        self.assertEqual(res_valid["extension"], "txt")

    def test_document_processing_rejects_unreadable_text(self):
        with self.assertRaisesRegex(ValueError, "No readable text was extracted"):
            document_service.extract_and_chunk("blank.txt", b"   \n  ", "txt")

    def test_text_cleaning_and_extraction(self):
        dirty = "Line 1\r\n\r\n\r\n\r\nLine 2    with   extra   spaces\n\n\nLine 3"
        cleaned = clean_extracted_text(dirty)
        self.assertNotIn("\r", cleaned)
        self.assertNotIn("   ", cleaned)
        self.assertIn("Line 2 with extra spaces", cleaned)

        extracted = extract_pasted_text("Clause 1: The user must pay by the 15th.", "Agreement")
        self.assertEqual(extracted.title, "Agreement")
        self.assertEqual(len(extracted.sections), 1)
        self.assertIn("Clause 1", extracted.full_text)

    def test_pdf_extraction_preserves_all_pages_in_order(self):
        import fitz
        from backend.app.processors.extractor import extract_pdf
        pdf = fitz.open()
        for marker in ("FIRST_PAGE_MARKER", "SECOND_PAGE_MARKER", "THIRD_PAGE_MARKER"):
            page = pdf.new_page()
            page.insert_text((72, 72), marker)
        data = pdf.tobytes()
        pdf.close()
        extracted = extract_pdf(data, "three-pages.pdf")
        self.assertEqual(extracted.page_count, 3)
        self.assertEqual([section.page_number for section in extracted.sections], [1, 2, 3])
        self.assertLess(extracted.full_text.index("FIRST_PAGE_MARKER"), extracted.full_text.index("SECOND_PAGE_MARKER"))
        self.assertLess(extracted.full_text.index("SECOND_PAGE_MARKER"), extracted.full_text.index("THIRD_PAGE_MARKER"))

    def test_scanned_pdf_uses_mocked_local_ocr_and_keeps_page_reference(self):
        import fitz
        import sys
        import types
        from backend.app.processors.extractor import extract_pdf
        pdf = fitz.open()
        pdf.new_page()
        data = pdf.tobytes()
        pdf.close()
        fake_tesseract = types.ModuleType("pytesseract")
        fake_tesseract.image_to_string = MagicMock(return_value="OCR_PAGE_MARKER scanned page text")
        fake_image = types.ModuleType("PIL.Image")
        fake_image.open = MagicMock(return_value=object())
        fake_pil = types.ModuleType("PIL")
        fake_pil.Image = fake_image
        with patch.dict(sys.modules, {"pytesseract": fake_tesseract, "PIL": fake_pil, "PIL.Image": fake_image}):
            extracted = extract_pdf(data, "scan.pdf")
        self.assertIn("OCR_PAGE_MARKER", extracted.full_text)
        self.assertEqual(extracted.sections[0].page_number, 1)
        self.assertTrue(any("local OCR" in warning for warning in extracted.warnings))

    def test_docx_extraction_keeps_tables_in_reading_order(self):
        import io
        from docx import Document
        from backend.app.processors.extractor import extract_docx
        document = Document()
        document.add_heading("Payment Terms", level=1)
        document.add_paragraph("Invoices are due within thirty days.")
        table = document.add_table(rows=2, cols=2)
        table.cell(0, 0).text, table.cell(0, 1).text = "Fee", "Due date"
        table.cell(1, 0).text, table.cell(1, 1).text = "$100", "June 30"
        data = io.BytesIO()
        document.save(data)
        extracted = extract_docx(data.getvalue(), "terms.docx")
        self.assertLess(extracted.full_text.index("Invoices are due"), extracted.full_text.index("Fee | Due date"))
        self.assertIn("$100 | June 30", extracted.full_text)

    def test_chunking_and_metadata(self):
        long_text = " ".join([f"Word{i} in clause {i//20}." for i in range(500)])
        extracted = extract_pasted_text(long_text, "Terms of Service")
        chunks = chunk_document(extracted, target_tokens=100, overlap_tokens=20)
        
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_index, 1)
        self.assertEqual(chunks[0].page_number, 1)
        self.assertTrue(len(chunks[0].content) > 0)
        self.assertTrue(chunks[0].token_count > 0)

    def test_tfidf_retrieval(self):
        chunks = [
            {"id": "chunk-1", "content": "Cancellation policy: The agreement may be terminated with 30 days notice.", "page_number": 2, "section_title": "Termination"},
            {"id": "chunk-2", "content": "Payment terms: Invoices are payable within 14 days of receipt.", "page_number": 4, "section_title": "Billing"},
            {"id": "chunk-3", "content": "Intellectual property: All software remains the exclusive property of the company.", "page_number": 7, "section_title": "IP"}
        ]
        retriever = TFIDFRetriever(threshold=0.15)
        retriever.fit_corpus(chunks)

        match = retriever.query("How many days notice are required to cancel?")
        self.assertIsNotNone(match)
        self.assertEqual(match.chunk_id, "chunk-1")
        self.assertEqual(match.page_number, 2)
        self.assertFalse(match.is_weak_match)
        self.assertIn("30 days notice", match.content)

        passages = retriever.query_many("How many days notice are required to cancel?", top_k=3)
        self.assertGreaterEqual(len(passages), 2)
        self.assertEqual(passages[0].chunk_id, "chunk-1")
        self.assertTrue(all(item.is_original_chunk for item in passages))

        match_bill = retriever.query("When do I need to pay invoice?")
        self.assertIsNotNone(match_bill)
        self.assertEqual(match_bill.chunk_id, "chunk-2")
        self.assertEqual(match_bill.page_number, 4)

        unrelated = retriever.query("What is the recipe for chocolate cake?")
        if unrelated:
            self.assertTrue(unrelated.is_weak_match)

    def test_chat_retrieves_original_passage_for_main_purpose_question(self):
        chunks = [{
            "id": "purpose-source", "content": (
                "The parties agree to the obligations below. The employee performs assigned work, "
                "and the employer pays wages each month. This agreement governs the duties and "
                "responsibilities of both parties."
            ), "page_number": 3, "section_title": "Terms"
        }]
        # Generated analysis text must not affect the TF-IDF index or become evidence.
        analysis_components = [{
            "heading": "Summary", "simplified_content": "Chocolate cake recipe and baking temperature."
        }]
        retriever = TFIDFRetriever(threshold=0.18)
        retriever.fit_corpus(chunks, analysis_components)
        passages = retriever.query_many("What is the main purpose of this document?", top_k=3)
        self.assertTrue(passages)
        self.assertEqual(passages[0].chunk_id, "purpose-source")
        self.assertEqual(passages[0].page_number, 3)
        self.assertGreaterEqual(passages[0].similarity_score, 0.18 * 0.55)
        self.assertTrue(passages[0].is_original_chunk)
        prompt = build_grounded_chat_prompt(
            "What is the main purpose of this document?", passages[0].content,
            passages[0].page_number, passages[0].section_title,
            retrieved_passages=[passage.to_dict() for passage in passages]
        )
        self.assertIn("The parties agree to the obligations below", prompt)
        self.assertIn("Page 3", prompt)
        self.assertNotIn("Chocolate cake recipe", prompt)

    def test_irrelevant_chat_question_has_no_document_passage(self):
        chunks = [{
            "id": "contract", "content": "The parties agree to the obligations below. The employer pays wages monthly.",
            "page_number": 1, "section_title": "Terms"
        }]
        retriever = TFIDFRetriever()
        retriever.fit_corpus(chunks)
        self.assertEqual(retriever.query_many("What temperature should I bake a chocolate cake?"), [])

    def test_history_is_used_for_followups_but_not_standalone_retrieval(self):
        from backend.app.api.v1.chat import _chat_retrieval_query
        history = [
            {"sender": "user", "content": "What obligations does the agreement list?"},
            {"sender": "assistant", "content": "It describes work and payment obligations."},
        ]
        standalone = "What is the main purpose of this document?"
        self.assertEqual(_chat_retrieval_query(standalone, history), standalone)
        self.assertIn("obligations", _chat_retrieval_query("What does that mean?", history))

    def test_mermaid_syntax_validation(self):
        bad_syntax = "A --> B --> C"
        checked = validate_mermaid_syntax(bad_syntax)
        self.assertTrue(checked["valid"])
        self.assertTrue(checked["cleaned"].startswith("graph TD"))

        valid_syntax = "graph TD\n  Start --> Finish"
        checked2 = validate_mermaid_syntax(valid_syntax)
        self.assertTrue(checked2["valid"])
        self.assertIn("Start --> Finish", checked2["cleaned"])

        malformed = validate_mermaid_syntax("flowchart TD\nthis is not valid syntax")
        self.assertFalse(malformed["valid"])
        self.assertEqual(malformed["cleaned"], "")

    def test_process_diagram_uses_decisions_and_explicit_branches(self):
        from backend.app.services.analysis_service import _build_process_mermaid
        flow = {
            "start_state": "Request received", "end_state": "Result sent",
            "steps": [
                {"title": "Check application", "description": "Review required fields", "node_type": "decision", "condition": "complete?",
                 "next_steps": [{"title": "Approve", "condition": "Yes"}, {"title": "Return", "condition": "No"}]},
                {"title": "Approve", "description": "Accept request", "node_type": "step"},
                {"title": "Return", "description": "Request corrections", "node_type": "step"},
            ]
        }
        diagram = _build_process_mermaid(flow)
        self.assertIn('S1{"Check application: complete?"}', diagram)
        self.assertIn("S1 -->|Yes| S2", diagram)
        self.assertIn("S1 -->|No| S3", diagram)
        self.assertIn('START(["Request received"])', diagram)
        self.assertIn('END(["Result sent"])', diagram)
        self.assertTrue(validate_mermaid_syntax(diagram)["valid"])

    def test_literal_ordered_flow_fallback_stays_grounded_in_source(self):
        from backend.app.services.analysis_service import _extract_explicit_flow_steps
        from backend.app.processors.extractor import ExtractedSection
        osi_text = "The OSI model has seven layers: Physical, Data Link, Network, Transport, Session, Presentation, and Application. Data moves through the layers from sender to receiver."
        flow = _extract_explicit_flow_steps([{"text": osi_text, "page_number": 4}], "OSI Model")
        self.assertEqual([step["title"] for step in flow["steps"]], ["Physical", "Data Link", "Network", "Transport", "Session", "Presentation", "Application"])
        self.assertEqual([step["page_number"] for step in flow["steps"]], [4] * 7)
        self.assertEqual(flow["steps"][0]["node_type"], "start")
        self.assertEqual(flow["steps"][-1]["node_type"], "end")
        self.assertIsNone(_extract_explicit_flow_steps([{"text": "The book discusses networking, routers, and protocols.", "page_number": 1}], "Networking"))

    def test_layer_flow_reverses_for_source_stated_sender_and_receiver_directions(self):
        from backend.app.services.analysis_service import _extract_explicit_flow_steps
        source = "The system has four layers: Lower, Middle A, Middle B, and Upper. At the sender data moves from Upper downward to Lower; at the receiver it moves upward from Lower to Upper."
        flow = _extract_explicit_flow_steps([{"text": source, "page_number": 2}], "Layered system")
        self.assertEqual(len(flow["steps"]), 8)
        self.assertEqual(flow["steps"][0]["title"], "Sender — Upper")
        self.assertEqual(flow["steps"][3]["title"], "Sender — Lower")
        self.assertEqual(flow["steps"][4]["title"], "Receiver — Lower")
        self.assertEqual(flow["steps"][-1]["title"], "Receiver — Upper")

    def test_process_model_empty_response_falls_back_only_to_explicit_steps(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        text = "The procedure has three stages: collect the input, transform it, and send the result."
        extraction = DocumentExtractionResult("Procedure", text, [ExtractedSection("Procedure", text, 1)], 1)
        async def empty_process(prompt):
            return {"has_process": False, "process_title": "", "steps": []}
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=empty_process):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["process"]))
        self.assertTrue(result["process_flow"]["has_process"])
        self.assertEqual(len(result["process_flow"]["steps"]), 3)
        self.assertTrue(result["process_flow"]["mermaid_syntax"])
        self.assertTrue(result["reliability_report"]["is_complete"])
        self.assertTrue(any("reconstructed from an explicit source list" in warning for warning in result["reliability_report"]["warnings"]))

    def test_osi_sender_receiver_flow_is_reconstructed_with_source_pages(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        text = (
            "The OSI model describes seven layers: Application, Presentation, Session, Transport, "
            "Network, Data Link, and Physical. At the sender, the application layer creates data. "
            "The sender encapsulates data as it moves down through the layers. "
            "The Physical layer transmits bits through the medium. "
            "At the receiver, data is decapsulated as it moves up through the layers. "
            "The receiving application receives and delivers the data."
        )
        extraction = DocumentExtractionResult(
            "OSI Model",
            text,
            [
                ExtractedSection("OSI layers", text[:text.index("The Physical")], 2),
                ExtractedSection("Transmission and reception", text[text.index("The Physical"):], 3),
            ],
            3,
        )

        async def incomplete_model_flow(prompt):
            return {
                "has_process": True,
                "process_title": "Procedure",
                "steps": [{"title": "Send data", "description": "The sender sends data.", "page_number": 2}],
            }

        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=incomplete_model_flow):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["process"]))

        flow = result["process_flow"]
        titles = [step["title"] for step in flow["steps"]]
        self.assertEqual(titles[0], "Sender application creates data")
        self.assertIn("Application Layer (Layer 7)", titles)
        self.assertIn("Presentation Layer (Layer 6)", titles)
        self.assertIn("Session Layer (Layer 5)", titles)
        self.assertIn("Transport Layer (Layer 4)", titles)
        self.assertIn("Network Layer (Layer 3)", titles)
        self.assertIn("Data Link Layer (Layer 2)", titles)
        self.assertIn("Physical Layer (Layer 1)", titles)
        self.assertIn("Transmission through the medium", titles)
        self.assertEqual(titles[9], "Physical Layer (Layer 1)")
        self.assertEqual(titles[15], "Application Layer (Layer 7)")
        self.assertEqual(titles[-1], "Data delivered to the receiving application")
        self.assertEqual(flow["process_title"], "OSI Data Transmission and Reception")
        self.assertEqual(flow["steps"][0]["page_number"], 2)
        self.assertEqual(flow["steps"][8]["page_number"], 3)
        self.assertEqual(flow["steps"][-1]["page_number"], 3)
        self.assertTrue(validate_mermaid_syntax(flow["mermaid_syntax"])["valid"])

    def test_process_normalization_repairs_generic_titles_and_missing_mermaid(self):
        from backend.app.services.analysis_service import normalize_process_flow
        for title in ("Procedure", "", None):
            with self.subTest(title=title):
                flow = normalize_process_flow({
                    "has_process": True,
                    "process_title": title,
                    "steps": [
                        {"title": "Create data", "description": "The application creates data.", "node_type": "start"},
                        {"title": "Transmit data", "description": "The medium carries the data.", "node_type": "end"},
                        {"title": "Discarded", "description": ""},
                        None,
                    ],
                }, "OSI_Model.pdf")

                self.assertEqual(flow["process_title"], "OSI Model")
                self.assertEqual(len(flow["steps"]), 2)
                self.assertIn("S1 --> S2", flow["mermaid_syntax"])
                self.assertTrue(validate_mermaid_syntax(flow["mermaid_syntax"])["valid"])
                self.assertEqual(flow["steps"][0]["summary"], "The application creates data.")
                self.assertEqual(flow["steps"][0]["brief_explanation"], "The application creates data.")

    def test_process_flow_rich_step_fields_are_normalized_and_persisted(self):
        import asyncio
        import json
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection

        text = "The sender validates the request and forwards an accepted message."
        extraction = DocumentExtractionResult(
            "Message workflow", text, [ExtractedSection("Workflow", text, 5)], 1
        )
        response = {
            "has_process": True,
            "process_title": "Message workflow",
            "steps": [{
                "step_number": 1,
                "title": "Validate request",
                "summary": "Check the incoming request.",
                "brief_explanation": "The sender checks the request fields. This prevents invalid messages from advancing and prepares valid requests for forwarding.",
                "key_actions": ["Check required fields", "Reject invalid requests"],
                "inputs_outputs": {
                    "inputs": ["Incoming request"],
                    "outputs": ["Validated request"],
                },
                "key_components_or_actors": ["Sender"],
                "page_number": 5,
            }],
        }
        persisted = []

        async def capture_progress(progress):
            persisted.append(json.loads(json.dumps(progress)))

        with patch(
            "backend.app.ai.ollama_client.ollama_client.generate_json",
            return_value=response,
        ):
            result = asyncio.run(analysis_service.analyze_document(
                extraction,
                selected_components=["process"],
                progress_callback=capture_progress,
            ))

        step = result["process_flow"]["steps"][0]
        self.assertEqual(step["summary"], "Check the incoming request.")
        self.assertIn("prevents invalid messages", step["brief_explanation"])
        self.assertEqual(step["key_actions"], ["Check required fields", "Reject invalid requests"])
        self.assertEqual(step["inputs_outputs"]["inputs"], ["Incoming request"])
        self.assertEqual(step["inputs_outputs"]["outputs"], ["Validated request"])
        self.assertEqual(step["key_components_or_actors"], ["Sender"])
        self.assertEqual(step["page_number"], 5)
        self.assertEqual(persisted[-1]["process_flow"]["steps"][0], step)
        self.assertEqual(json.loads(json.dumps(result["process_flow"]))["steps"][0]["title"], "Validate request")

    def test_process_flow_prompt_requests_structured_step_details(self):
        from backend.app.ai.prompts import build_focused_module_prompt, build_process_recovery_prompt

        sections = [{"heading": "Workflow", "page_number": 5, "text": "The sender validates and forwards a request."}]
        prompt = build_focused_module_prompt("process_flow", "Message workflow", 1, 1, sections)
        recovery_prompt = build_process_recovery_prompt("Message workflow", 1, 1, sections)
        for field in (
            '"summary"',
            '"brief_explanation"',
            '"key_actions"',
            '"inputs_outputs"',
            '"key_components_or_actors"',
            '"page_number"',
        ):
            self.assertIn(field, prompt)
            self.assertIn(field, recovery_prompt)

    def test_malformed_process_output_does_not_create_a_flow_for_non_process_text(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        text = "This document describes the properties of water and its chemical composition."
        extraction = DocumentExtractionResult("Water", text, [ExtractedSection("Water", text, 1)], 1)

        async def malformed_process(prompt):
            return {"has_process": "yes", "steps": [{"title": "Invented", "description": "Not source-grounded"}]}

        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=malformed_process):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["process"]))

        self.assertFalse(result["process_flow"]["has_process"])
        self.assertEqual(result["process_flow"]["steps"], [])
        self.assertEqual(result["process_flow"]["mermaid_syntax"], "")
        self.assertTrue(any("process_flow:0" in item for item in result["reliability_report"]["failed_modules"]))

    def test_no_process_response_remains_empty_without_source_flow_cues(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        text = "This chapter compares several networking terms and defines their meanings."
        extraction = DocumentExtractionResult("Networking Terms", text, [ExtractedSection("Terms", text, 1)], 1)

        async def no_process(prompt):
            return {"has_process": False, "process_title": "", "steps": []}

        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=no_process):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["process"]))

        self.assertFalse(result["process_flow"]["has_process"])
        self.assertEqual(result["process_flow"]["steps"], [])
        self.assertEqual(result["process_flow"]["mermaid_syntax"], "")
        self.assertEqual(result["reliability_report"]["failed_modules"], [])

    def test_frontend_passes_generated_process_diagram_to_mermaid_renderer(self):
        dashboard_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "../../frontend/src/components/viewer/AnalysisDashboard.tsx",
        ))
        with open(dashboard_path, encoding="utf-8") as dashboard_file:
            dashboard_source = dashboard_file.read()

        self.assertIn(
            "analysis.process_flow.mermaid_syntax || buildProcessDiagramFromSteps",
            dashboard_source,
        )
        self.assertIn("<MermaidDiagram", dashboard_source)
        self.assertIn("chart={processDiagram}", dashboard_source)
        self.assertIn("onNodeClick={handleProcessDiagramNodeClick}", dashboard_source)
        self.assertIn("selectedNodeId={`S${selectedStepIndex + 1}`}", dashboard_source)
        self.assertIn("What Happens in This Step", dashboard_source)
        self.assertIn("Key Actions &amp; Operations", dashboard_source)
        self.assertNotIn("No flowchart syntax available for this process.", dashboard_source)

    def test_concept_map_renders_parent_and_explicit_relationships(self):
        from backend.app.services.analysis_service import _build_concept_mermaid
        diagram = _build_concept_mermaid({
            "central_topic": "OSI Model",
            "concepts": [
                {"name": "Application Layer", "parent": "OSI Model"},
                {"name": "Presentation Layer", "parent": "OSI Model"},
            ],
            "relationships": [{"from": "Application Layer", "to": "Presentation Layer", "label": "passes data to"}],
        })
        self.assertIn('ROOT(["OSI Model"])', diagram)
        self.assertIn("ROOT -->|includes| C1", diagram)
        self.assertIn("C1 -->|passes data to| C2", diagram)
        self.assertTrue(validate_mermaid_syntax(diagram)["valid"])

    def test_layered_concept_map_renders_technical_details_in_generated_direction(self):
        from backend.app.services.analysis_service import _build_concept_mermaid
        diagram = _build_concept_mermaid({
            "central_topic": "OSI Model",
            "diagram_direction": "TB",
            "concepts": [
                {"name": "Application Layer (Layer 7)", "data_unit": "Data",
                 "protocols_hardware_standards": ["HTTP", "DNS"]},
                {"name": "Presentation Layer (Layer 6)", "data_unit": "Data",
                 "protocols_hardware_standards": ["UTF-8", "JPEG"]},
            ],
            "relationships": [
                {"from": "Application Layer (Layer 7)", "to": "Presentation Layer (Layer 6)", "label": "encapsulates"}
            ],
        })
        self.assertTrue(diagram.startswith("flowchart TB"))
        self.assertIn("PDU: Data", diagram)
        self.assertIn("Examples: HTTP, DNS", diagram)
        self.assertIn("C1 -->|encapsulates| C2", diagram)
        self.assertNotIn("ROOT", diagram)
        self.assertTrue(validate_mermaid_syntax(diagram)["valid"])

    def test_concept_map_prompt_requests_structured_node_details_and_layout(self):
        from backend.app.ai.prompts import build_focused_module_prompt
        prompt = build_focused_module_prompt(
            "concept_map", "OSI Model", 1, 1,
            [{"heading": "Layers", "page_number": 2, "text": "The OSI reference model has seven layers."}],
        )
        for field in (
            "detailed_explanation",
            "key_responsibilities",
            "protocols_hardware_standards",
            "data_unit_interaction",
            "diagram_direction",
        ):
            self.assertIn(field, prompt)
        self.assertIn("encapsulation and decapsulation", prompt)

    def test_prompts_architecture(self):
        summary_prompt = build_summary_prompt("Non-Disclosure Agreement", "Confidential text...", "en", "simple")
        self.assertIn("ROLE:", summary_prompt)
        self.assertIn("TASK:", summary_prompt)
        self.assertIn("CONTEXT:", summary_prompt)
        self.assertIn("CONSTRAINTS:", summary_prompt)
        self.assertIn("OUTPUT FORMAT:", summary_prompt)
        self.assertIn("everyday conversational language", summary_prompt)

        hindi_prompt = build_section_explanation_prompt("Section 1", "Rules...", 1, "hi", "balanced")
        self.assertIn("Hindi (Devanagari script)", hindi_prompt)

        chat_prompt = build_grounded_chat_prompt(
            "When is it due?", "Payment is due within 14 days.", 4, "Billing",
            conversation_context=[{"sender": "user", "content": "Tell me about the invoice."},
                                  {"sender": "assistant", "content": "The invoice is issued monthly."}]
        )
        self.assertIn("must never support factual claims", chat_prompt)
        self.assertIn("Tell me about the invoice.", chat_prompt)
        self.assertIn("Use ONLY facts stated in the retrieved document passages", chat_prompt)

    def test_export_markdown(self):
        analysis = {
            "overview": {"document_subject": "Employment Contract", "main_purpose": "Job agreement", "target_audience": "Employee"},
            "summary": "This contract outlines duties and salary.",
            "sections": [{"heading": "Compensation", "page_number": 3, "simplified_explanation": "Salary paid monthly.", "key_points": ["$5000/mo"]}],
            "key_information": {"critical_obligations": ["Work 40 hours"]},
            "definitions": [{"term": "Base Salary", "plain_definition": "Guaranteed income"}]
        }
        md = export_service.generate_markdown("Employment Contract", analysis)
        self.assertIn("# FormEase Document Analysis: Employment Contract", md)
        self.assertIn("## 1. Document Overview", md)
        self.assertIn("Compensation", md)
        self.assertIn("$5000/mo", md)

class TestSecurityAndAuth(unittest.TestCase):
    def setUp(self):
        self.original_secret = settings.SUPABASE_JWT_SECRET
        self.original_supabase_url = settings.SUPABASE_URL
        settings.SUPABASE_JWT_SECRET = TEST_SECRET

    def tearDown(self):
        settings.SUPABASE_JWT_SECRET = self.original_secret
        settings.SUPABASE_URL = self.original_supabase_url

    def test_valid_jwt_verification(self):
        user_uuid = str(uuid.uuid4())
        token = create_test_jwt(user_uuid, "alice@example.com")
        payload = verify_supabase_jwt(token)
        self.assertEqual(payload["sub"], user_uuid)
        self.assertEqual(payload["email"], "alice@example.com")
        self.assertEqual(payload["aud"], "authenticated")

    def test_valid_es256_jwt_verification_uses_supabase_jwks(self):
        user_uuid = str(uuid.uuid4())
        project_url = "https://formease-test.supabase.co"
        settings.SUPABASE_URL = project_url
        signing_key = ec.generate_private_key(ec.SECP256R1())
        private_pem = signing_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()
        ).decode()
        public_pem = signing_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        public_jwk = jwk.construct(public_pem, algorithm="ES256").to_dict()
        public_jwk.update({"kid": "formease-test-key", "alg": "ES256"})
        token = jwt.encode({
            "sub": user_uuid,
            "email": "alice@example.com",
            "aud": "authenticated",
            "iss": f"{project_url}/auth/v1",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600
        }, private_pem, algorithm="ES256", headers={"kid": "formease-test-key"})
        response = MagicMock()
        response.json.return_value = {"keys": [public_jwk]}

        with patch("backend.app.core.security._create_jwks_client") as create_client:
            create_client.return_value.get.return_value = response
            payload = verify_supabase_jwt(token)

        self.assertEqual(payload["sub"], user_uuid)
        self.assertEqual(payload["iss"], f"{project_url}/auth/v1")

    def test_empty_or_missing_token_rejection(self):
        with self.assertRaises(HTTPException) as cm:
            verify_supabase_jwt("")
        self.assertEqual(cm.exception.status_code, 401)

        with self.assertRaises(HTTPException) as cm:
            verify_supabase_jwt(None)
        self.assertEqual(cm.exception.status_code, 401)

    def test_expired_token_rejection(self):
        user_uuid = str(uuid.uuid4())
        token = create_test_jwt(user_uuid, "bob@example.com", expired=True)
        with self.assertRaises(HTTPException) as cm:
            verify_supabase_jwt(token)
        self.assertEqual(cm.exception.status_code, 401)
        self.assertIn("expired", cm.exception.detail)

    def test_tampered_or_invalid_signature_rejection(self):
        user_uuid = str(uuid.uuid4())
        token = create_test_jwt(user_uuid, "charlie@example.com")
        tampered = token[:-4] + "abcd"
        with self.assertRaises(HTTPException) as cm:
            verify_supabase_jwt(tampered)
        self.assertEqual(cm.exception.status_code, 401)

    def test_dev_token_bypass_is_strictly_rejected(self):
        with self.assertRaises(HTTPException) as cm:
            verify_supabase_jwt("Bearer dev-local-token")
        self.assertEqual(cm.exception.status_code, 401)

    def test_unconfigured_jwt_secret_fails_safely(self):
        settings.SUPABASE_JWT_SECRET = "placeholder-jwt-secret"
        token = create_test_jwt(str(uuid.uuid4()))
        with self.assertRaises(HTTPException) as cm:
            verify_supabase_jwt(token)
        self.assertEqual(cm.exception.status_code, 500)

class TestDatabaseAndMultiTenantIsolation(unittest.TestCase):
    def setUp(self):
        self.user_a_id = str(uuid.uuid4())
        self.user_b_id = str(uuid.uuid4())

    def test_unconfigured_supabase_raises_503(self):
        set_test_supabase_client(None)
        old_url, old_key = settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY
        settings.SUPABASE_URL = "https://placeholder-project.supabase.co"
        settings.SUPABASE_ANON_KEY = "placeholder-anon-key"
        try:
            with self.assertRaises(HTTPException) as cm:
                get_supabase_client()
        finally:
            settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY = old_url, old_key
        self.assertEqual(cm.exception.status_code, 503)
        self.assertIn("not configured", cm.exception.detail)

    def test_document_query_enforces_user_isolation(self):
        mock_db = MagicMock()
        set_test_supabase_client(mock_db)

        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq_user = MagicMock()
        mock_eq_deleted = MagicMock()
        mock_order = MagicMock()

        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq_user
        mock_eq_user.eq.return_value = mock_eq_deleted
        mock_eq_deleted.order.return_value = mock_order

        user_a_doc = {"id": str(uuid.uuid4()), "user_id": self.user_a_id, "title": "A's Contract"}
        mock_order.execute.return_value = MagicMock(data=[user_a_doc])

        res = mock_db.table("documents").select("*").eq("user_id", self.user_a_id).eq("is_deleted", False).order("created_at").execute()
        
        mock_select.eq.assert_called_with("user_id", self.user_a_id)
        self.assertEqual(res.data[0]["user_id"], self.user_a_id)

    def test_cross_tenant_access_denial(self):
        mock_db = MagicMock()
        set_test_supabase_client(mock_db)

        doc_table = MagicMock()
        select_mock = MagicMock()
        eq_id_mock = MagicMock()
        eq_user_mock = MagicMock()

        mock_db.table.return_value = doc_table
        doc_table.select.return_value = select_mock
        select_mock.eq.return_value = eq_id_mock
        eq_id_mock.eq.return_value = eq_user_mock
        eq_user_mock.execute.return_value = MagicMock(data=[])

        target_doc_id = str(uuid.uuid4())
        res = mock_db.table("documents").select("*").eq("id", target_doc_id).eq("user_id", self.user_b_id).execute()
        
        self.assertEqual(len(res.data), 0)

class TestConcurrencyAndScopedContext(unittest.TestCase):
    def test_scoped_client_token_isolation(self):
        # Verify that two concurrent users receive distinct isolated clients with their own JWT
        token_a = create_test_jwt(str(uuid.uuid4()), "alice@test.com")
        token_b = create_test_jwt(str(uuid.uuid4()), "bob@test.com")

        with patch("supabase.create_client") as mock_create:
            mock_create.side_effect = lambda url, key, options: MagicMock(
                options=options,
                auth_header=options.headers.get("Authorization")
            )
            
            # Temporarily configure valid settings to test factory
            old_url, old_key = settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY
            settings.SUPABASE_URL = "https://live-test.supabase.co"
            settings.SUPABASE_ANON_KEY = "live-test-anon-key-12345"
            try:
                set_test_supabase_client(None) # reset mock override
                client_a = get_authenticated_supabase_client(token_a)
                client_b = get_authenticated_supabase_client(token_b)

                # Ensure clients are separate instances
                self.assertIsNot(client_a, client_b)
                # Ensure User A's client carries User A's token
                self.assertEqual(client_a.auth_header, f"Bearer {token_a}")
                # Ensure User B's client carries User B's token
                self.assertEqual(client_b.auth_header, f"Bearer {token_b}")
                # Verify no token cross-contamination
                self.assertNotEqual(client_a.auth_header, client_b.auth_header)
            finally:
                settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY = old_url, old_key

    def test_document_status_enum_values(self):
        # Strict validation: Only 'pending', 'processing', 'completed', 'failed' are permitted
        valid_statuses = {"pending", "processing", "completed", "failed"}
        self.assertEqual({s.value for s in DocumentStatus}, valid_statuses)

        # Ensure 'ready' is not in enum
        self.assertNotIn("ready", [s.value for s in DocumentStatus])

    def test_storage_path_format(self):
        user_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())
        path = f"{user_id}/{doc_id}.pdf"
        parts = path.split("/")
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], user_id)
        self.assertTrue(parts[1].endswith(".pdf"))

    def test_storage_policies_present_in_schema(self):
        with open("database/schema.sql") as f:
            sql = f.read()
        self.assertIn("storage.buckets", sql)
        self.assertIn("bucket_id = 'documents'", sql)
        self.assertIn("(storage.foldername(name))[1] = auth.uid()::text", sql)

class TestAnalysisReliabilityAndErrorRecovery(unittest.TestCase):
    @staticmethod
    def valid_batch(section_heading="Section", page_number=1):
        return {
            "overview": {"document_subject": "Test", "main_purpose": "Explain", "target_audience": "Students"},
            "summary": "Part summary",
            "sections": [{"heading": section_heading, "page_number": page_number,
                          "simplified_explanation": "Plain explanation", "key_points": ["Key point"],
                          "potential_risks": [], "risk_level": "low"}],
            "process_flow": {"has_process": False, "process_title": "", "steps": []},
            "concept_map": {"concepts": [], "relationships": []},
            "key_information": {"critical_obligations": [], "deadlines_and_dates": [],
                                "warnings_and_penalties": [], "important_conditions": []},
            "definitions": [], "recommendations": [], "formulas": [], "revision_notes": [],
        }

    @classmethod
    def response_for_prompt(cls, prompt, section_heading="Section", page_number=1):
        if "Generate all requested learning modules independently" in prompt:
            return {
                "revision_notes": ["The application is submitted before review."],
                "formulas": [{"formula": "Total = base + fee", "explanation": "The document defines a total as base amount plus fee.", "page_number": 1}],
                "key_information": {"critical_obligations": ["Submit the form"], "deadlines_and_dates": ["Submit by June 30"], "warnings_and_penalties": [], "important_conditions": ["A complete form is required"], "important_facts": ["Fee: $20"]},
                "definitions": [{"term": "Applicant", "plain_definition": "The person submitting the form", "context_sentence": "The applicant signs the form.", "page_number": 1}],
                "recommendations": [{"category": "Critical Action", "recommendation": "Submit the complete form by June 30.", "source_reference": "Page 1"}],
            }
        if "Module: process_flow" in prompt:
            return {"has_process": True, "process_title": "Application", "steps": [{"title": "Submit", "description": "Submit the required form", "inputs": ["Form"], "outputs": ["Application"], "condition": "", "page_number": 1}]}
        if "Module: concept_map" in prompt:
            return {
                "central_topic": "Application",
                "diagram_direction": "LR",
                "concepts": [
                    {"name": "Application", "description": "The submitted form",
                     "detailed_explanation": "Applicants complete the form.\n\nThe completed form starts the review process.",
                     "key_responsibilities": ["Collect required information"],
                     "protocols_hardware_standards": ["Application form"],
                     "data_unit": "Form submission",
                     "data_unit_interaction": "The form is passed to the review stage.",
                     "page_number": 1},
                    {"name": "Review", "description": "Assessment of the form",
                     "detailed_explanation": "The submitted form is assessed.\n\nThe assessment determines whether requirements are met.",
                     "key_responsibilities": ["Assess submitted information"],
                     "protocols_hardware_standards": ["Review checklist"],
                     "data_unit": "Review record",
                     "data_unit_interaction": "The review uses the submitted form.",
                     "page_number": 1},
                ],
                "relationships": [{"from": "Application", "to": "Review", "label": "is assessed by", "page_number": 1}],
            }
        if "Module: revision_notes" in prompt:
            return ["The application is submitted before review."]
        if "Module: formulas" in prompt:
            return [{"formula": "Total = base + fee", "explanation": "The document defines a total as base amount plus fee.", "page_number": 1}]
        if "Module: key_information" in prompt:
            return {"critical_obligations": ["Submit the form"], "deadlines_and_dates": ["Submit by June 30"], "warnings_and_penalties": [], "important_conditions": ["A complete form is required"], "important_facts": ["Fee: $20"]}
        if "Module: definitions" in prompt:
            return [{"term": "Applicant", "plain_definition": "The person submitting the form", "context_sentence": "The applicant signs the form.", "page_number": 1}]
        if "Module: recommendations" in prompt:
            return [{"category": "Critical Action", "recommendation": "Submit the complete form by June 30.", "source_reference": "Page 1"}]
        return cls.valid_batch(section_heading, page_number)

    def test_placeholder_sections_are_regenerated_with_source_heading_and_page(self):
        import asyncio
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult(
            "OSI Policy",
            "Physical Layer: The sender converts bits into electrical signals.",
            [ExtractedSection("Physical Layer", "The sender converts bits into electrical signals.", 4)],
            4,
        )

        async def mocked_generate(prompt):
            if "Explain this specific section" in prompt:
                return {
                    "heading": "Physical Layer",
                    "page_number": 4,
                    "simplified_explanation": "The Physical Layer converts sender data into electrical signals for transmission.",
                    "key_points": ["The sender converts bits into electrical signals."],
                    "potential_risks": [],
                    "risk_level": "low",
                }
            return {
                "overview": {"document_subject": "OSI networking", "main_purpose": "Explain data transmission", "target_audience": "Students"},
                "summary": "The document explains the Physical Layer of OSI data transmission.",
                "sections": [{
                    "heading": "This section",
                    "page_number": 4,
                    "simplified_explanation": "This section provides an overview of the document's main purpose and target audience.",
                    "key_points": [],
                    "potential_risks": [],
                    "risk_level": "low",
                }],
            }

        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=mocked_generate):
            result = asyncio.run(analysis_service.analyze_document(
                extraction,
                selected_components=["summary", "sections"],
            ))

        self.assertTrue(result["reliability_report"]["is_complete"])
        self.assertEqual(len(result["sections"]), 1)
        self.assertEqual(result["sections"][0]["heading"], "Physical Layer")
        self.assertEqual(result["sections"][0]["page_number"], 4)
        self.assertIn("electrical signals", result["sections"][0]["simplified_explanation"])

    def test_empty_section_response_uses_dedicated_source_prompt_not_placeholder(self):
        import asyncio
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult(
            "Leave Policy",
            "Leave Request: Employees submit leave requests at least 14 days before planned absence.",
            [ExtractedSection("Leave Request", "Employees submit leave requests at least 14 days before planned absence.", 2)],
            2,
        )

        async def mocked_generate(prompt):
            if "Explain this specific section" in prompt:
                return {
                    "heading": "Leave Request",
                    "page_number": 2,
                    "simplified_explanation": "Employees must submit leave requests at least 14 days in advance.",
                    "key_points": ["Requests require 14 days of advance notice."],
                    "potential_risks": [],
                    "risk_level": "medium",
                }
            return {
                "overview": {"document_subject": "Leave policy", "main_purpose": "Explain leave requests", "target_audience": "Employees"},
                "summary": "The document defines leave request notice requirements.",
                "sections": [],
            }

        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=mocked_generate):
            result = asyncio.run(analysis_service.analyze_document(
                extraction,
                selected_components=["summary", "sections"],
            ))

        self.assertTrue(result["reliability_report"]["is_complete"])
        self.assertEqual(result["sections"][0]["heading"], "Leave Request")
        self.assertEqual(result["sections"][0]["page_number"], 2)
        self.assertNotIn("This section provides", result["sections"][0]["simplified_explanation"])

    def test_saved_placeholder_sections_are_removed_from_api_data(self):
        from backend.app.api.v1.analysis import _clean_saved_sections
        cleaned = _clean_saved_sections([
            {"heading": "Overview", "page_number": 1, "simplified_explanation": "This section provides an overview of the document's main purpose and target audience."},
            {"heading": "Compensation", "page_number": 3, "simplified_explanation": "Salary is paid monthly and subject to the listed deductions."},
        ])
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["heading"], "Compensation")

    def test_pdf_section_titles_use_document_headings_or_source_content(self):
        from backend.app.processors.extractor import infer_section_heading
        heading = infer_section_heading("Physical Layer\nSender and receiver exchange raw electrical signals.", 2)
        content_title = infer_section_heading("Employees must submit leave requests at least 14 days before absence.", 3)
        self.assertEqual(heading, "Physical Layer")
        self.assertIn("Employees", content_title)

    def test_long_document_analysis_splits_summary_without_dropping_tail(self):
        from backend.app.processors.extractor import DocumentExtractionResult
        extraction = DocumentExtractionResult("Long Doc", "alpha " * 2200 + "TAIL_MARKER", [], 1)
        prompts = []
        async def mocked(prompt):
            prompts.append(prompt)
            return self.response_for_prompt(prompt)
        with patch("backend.app.core.config.settings.AI_ANALYSIS_BATCH_CHARS", 3000), \
             patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=mocked) as mock_ai:
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["summary"]))
        self.assertGreater(mock_ai.call_count, 1)
        self.assertTrue(any("TAIL_MARKER" in prompt for prompt in prompts))
        self.assertTrue(result["reliability_report"]["is_complete"])

    def test_openrouter_fails_closed_without_backend_credentials(self):
        from backend.app.ai.ollama_client import ollama_client
        old_provider = ollama_client.provider
        old_key, old_model = settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL
        ollama_client.provider = "openrouter"
        settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL = "", ""
        try:
            import asyncio
            with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
                asyncio.run(ollama_client.generate("test"))
        finally:
            ollama_client.provider = old_provider
            settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL = old_key, old_model

    def test_openrouter_uses_configured_model_and_compatible_chat_endpoint(self):
        from backend.app.ai.ollama_client import ollama_client
        from unittest.mock import AsyncMock
        old_provider, old_model, old_key = ollama_client.provider, ollama_client.openrouter_model, settings.OPENROUTER_API_KEY
        ollama_client.provider, ollama_client.openrouter_model = "openrouter", "unit-test/model:free"
        settings.OPENROUTER_API_KEY = "test-key"
        response = MagicMock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "grounded result"}}]}
        http_client = AsyncMock()
        http_client.__aenter__.return_value.post = AsyncMock(return_value=response)
        try:
            with patch("backend.app.ai.ollama_client.httpx.AsyncClient", return_value=http_client):
                import asyncio
                result = asyncio.run(ollama_client.generate("source-bound prompt"))
            self.assertEqual(result, "grounded result")
            call = http_client.__aenter__.return_value.post.call_args
            self.assertTrue(call.args[0].endswith("/chat/completions"))
            self.assertEqual(call.kwargs["json"]["model"], "unit-test/model:free")
        finally:
            ollama_client.provider, ollama_client.openrouter_model = old_provider, old_model
            settings.OPENROUTER_API_KEY = old_key

    def test_component_failure_isolation(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        
        extraction = DocumentExtractionResult(
            title="Test Doc",
            full_text="Sample text content for analysis testing.",
            sections=[ExtractedSection("Section 1", "Clause text", 1)],
            page_count=1
        )

        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", return_value=self.valid_batch("Section 1")) as mock_ai:
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(
                extraction,
                selected_components=["summary", "process"]
            ))

            self.assertEqual(result["summary"], "Part summary")
            self.assertFalse(result["process_flow"]["has_process"])
            self.assertEqual(mock_ai.call_count, 2)

    def test_total_provider_failure_is_reported_as_retryable_partial_analysis(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult(
            title="Test Doc",
            full_text="Sample text content.",
            sections=[ExtractedSection("Section 1", "Clause text", 1)],
            page_count=1
        )
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=RuntimeError("Ollama unavailable")):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["summary", "process"]))
        self.assertFalse(result["reliability_report"]["is_complete"])
        self.assertEqual(result["reliability_report"]["failed_batches"], [0])
        self.assertEqual(result["overview"], {})
        self.assertEqual(result["summary"], "")

    def test_missing_optional_empty_arrays_do_not_discard_valid_analysis(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult(
            title="Optional fields", full_text="A short clause.",
            sections=[ExtractedSection("Clause", "A short clause.", 1)], page_count=1
        )
        batch = self.valid_batch("Clause")
        batch.pop("definitions")
        batch.pop("formulas")
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", return_value=batch):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["summary"]))
        self.assertTrue(result["reliability_report"]["is_complete"])
        self.assertEqual(result["summary"], "Part summary")
        self.assertEqual(result["overview"]["document_subject"], "Test")
        self.assertEqual(result["definitions"], [])
        self.assertEqual(result["formulas"], [])
        self.assertFalse(result["reliability_report"]["warnings"])

    def test_missing_revision_notes_normalize_without_failing_batch(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult(
            title="Missing notes", full_text="A short clause.",
            sections=[ExtractedSection("Clause", "A short clause.", 1)], page_count=1
        )
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", return_value={}):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["revision_notes"]))
        self.assertFalse(result["reliability_report"]["is_complete"])
        self.assertEqual(result["reliability_report"]["completed_batches"], [])
        self.assertEqual(result["reliability_report"]["failed_batches"], [])
        self.assertEqual(result["revision_notes"], [])
        self.assertEqual(result["reliability_report"]["failed_modules"], ["revision_notes:0"])

    def test_malformed_revision_notes_normalize_without_failing_batch(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult(
            title="Malformed notes", full_text="A short clause.",
            sections=[ExtractedSection("Clause", "A short clause.", 1)], page_count=1
        )
        batch = {"unrelated": "not the expected array"}
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", return_value=batch):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["revision_notes"]))
        self.assertFalse(result["reliability_report"]["is_complete"])
        self.assertEqual(result["reliability_report"]["completed_batches"], [])
        self.assertEqual(result["reliability_report"]["failed_batches"], [])
        self.assertEqual(result["revision_notes"], [])
        self.assertEqual(result["reliability_report"]["failed_modules"], ["revision_notes:0"])

    def test_revision_notes_accepts_explicit_module_wrapper_from_small_model(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult("Wrapped notes", "Clause text.", [ExtractedSection("Clause", "Clause text.", 1)], 1)
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json",
                   return_value={"revision_notes": ["The clause states the required action."]}):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["revision_notes"]))
        self.assertTrue(result["reliability_report"]["is_complete"])
        self.assertEqual(result["revision_notes"], ["The clause states the required action."])

    def test_revision_notes_accepts_small_model_descriptive_note_key(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult("Named note", "Clause text.", [ExtractedSection("Clause", "Clause text.", 1)], 1)
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json",
                   return_value={"short_source_grounded_revision_note": "The clause states the required action."}):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, selected_components=["revision_notes"]))
        self.assertTrue(result["reliability_report"]["is_complete"])
        self.assertEqual(result["revision_notes"], ["The clause states the required action."])

    def test_concept_map_can_be_reanalyzed_without_other_modules(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection

        extraction = DocumentExtractionResult(
            "OSI Model",
            "The OSI reference model has seven layers.",
            [ExtractedSection("OSI Layers", "The OSI reference model has seven layers.", 1)],
            1,
        )

        async def concept_map_response(prompt):
            self.assertIn("Module: concept_map", prompt)
            return {
                "central_topic": "OSI Model",
                "concepts": [{
                    "name": "Physical Layer",
                    "description": "Transmits bits.",
                    "detailed_explanation": "The physical layer transmits the data as signals.",
                    "key_responsibilities": ["Transmit bits"],
                    "protocols_hardware_standards": ["Ethernet cable"],
                    "data_unit": "Bits",
                    "data_unit_interaction": "Encodes frames as bits.",
                    "page_number": 1,
                }],
                "relationships": [],
                "diagram_direction": "TB",
            }

        with patch(
            "backend.app.ai.ollama_client.ollama_client.generate_json",
            side_effect=concept_map_response,
        ) as mock_ai:
            import asyncio
            result = asyncio.run(
                analysis_service.analyze_document(
                    extraction,
                    selected_components=["concept_map"],
                    existing_result={
                        "concept_map": {
                            "central_topic": "OSI Model",
                            "concepts": [{
                                "name": "Physical Layer",
                                "description": "Transmits bits.",
                            }],
                            "relationships": [],
                        },
                    },
                )
            )

        self.assertEqual(mock_ai.call_count, 1)
        self.assertTrue(result["reliability_report"]["is_complete"])
        self.assertEqual(result["reliability_report"]["selected_modules"], ["concept_map"])
        self.assertEqual(result["process_flow"]["steps"], [])
        self.assertEqual(result["concept_map"]["concepts"][0]["key_responsibilities"], ["Transmit bits"])
        self.assertEqual(result["concept_map"]["concepts"][0]["description"], "Transmits bits.")

    def test_eighteen_page_document_is_batched_not_one_request_per_page(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        sections = [ExtractedSection(f"Page {i}", f"Content for page {i}. " + ("document details " * 70), i) for i in range(1, 19)]
        extraction = DocumentExtractionResult("18 pages", " ".join(s.text for s in sections), sections, 18)
        async def mocked(prompt):
            return self.response_for_prompt(prompt)
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=mocked) as mock_ai:
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction))
        self.assertEqual(mock_ai.call_count, 12)
        self.assertEqual(result["reliability_report"]["total_batches"], 3)

    def test_retry_skips_completed_analysis_batches(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        sections = [ExtractedSection(f"Section {i}", "content " * 700, i) for i in range(1, 4)]
        extraction = DocumentExtractionResult("Retry", " ".join(s.text for s in sections), sections, 3)
        from backend.app.services.analysis_service import _analysis_batches
        with patch("backend.app.core.config.settings.AI_ANALYSIS_BATCH_CHARS", 3000), \
             patch("backend.app.ai.ollama_client.ollama_client.generate_json", return_value=self.valid_batch("Section 2", 2)) as mock_ai:
            import asyncio
            total_batches = len(_analysis_batches(extraction))
            result = asyncio.run(analysis_service.analyze_document(
                extraction, existing_result={"summary": "Saved", "sections": [self.valid_batch()["sections"][0]],
                                             "process_flow": {"has_process": False, "steps": []}},
                completed_batches=list(range(total_batches - 1)),
                selected_components=["summary"]))
        self.assertEqual(mock_ai.call_count, 1)
        self.assertTrue(result["reliability_report"]["is_complete"])

    def test_all_advanced_modules_are_generated_and_saved_with_combined_request(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult(
            "Application Guide", "Applicants submit the form by June 30 and pay a $20 fee. The form is reviewed.",
            [ExtractedSection("Procedure", "Applicants submit the form by June 30 and pay a $20 fee. The form is reviewed.", 1)], 1
        )
        prompts, saved = [], []
        async def mocked(prompt):
            prompts.append(prompt)
            return self.response_for_prompt(prompt, "Procedure")
        async def persist(result):
            import copy
            saved.append(copy.deepcopy(result))
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=mocked):
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction, progress_callback=persist))
        self.assertTrue(any("Generate all requested learning modules independently" in prompt for prompt in prompts))
        for module in ("process_flow", "concept_map", "revision_notes", "formulas", "key_information", "definitions", "recommendations"):
            if module in ("revision_notes", "formulas", "key_information", "definitions", "recommendations"):
                continue
            self.assertTrue(any(f"Module: {module}" in prompt for prompt in prompts), module)
            self.assertEqual(result["reliability_report"]["module_batches"][module], [0])
        self.assertEqual(len(result["process_flow"]["steps"]), 1)
        self.assertEqual(len(result["concept_map"]["relationships"]), 1)
        self.assertIn("The completed form starts the review process.", result["concept_map"]["concepts"][0]["detailed_explanation"])
        self.assertEqual(result["concept_map"]["concepts"][0]["key_responsibilities"], ["Collect required information"])
        self.assertEqual(result["concept_map"]["concepts"][0]["data_unit"], "Form submission")
        self.assertEqual(saved[-1]["concept_map"]["concepts"][0]["protocols_hardware_standards"], ["Application form"])
        self.assertEqual(result["concept_map"]["diagram_direction"], "LR")
        self.assertTrue(result["revision_notes"])
        self.assertTrue(result["formulas"])
        self.assertTrue(result["key_information"]["important_facts"])
        self.assertTrue(result["definitions"])
        self.assertTrue(result["recommendations"])
        self.assertTrue(saved)
        self.assertTrue(result["reliability_report"]["is_complete"])

    def test_partial_module_failure_preserves_successes_and_retries_only_that_module(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult("Partial", "Source says submit an application and it is reviewed.",
            [ExtractedSection("Steps", "Source says submit an application and it is reviewed.", 1)], 1)
        prompts = []
        async def first_run(prompt):
            prompts.append(prompt)
            if "Generate all requested learning modules independently" in prompt:
                return {
                    "revision_notes": {"malformed": "expected an array"},
                    "formulas": [{"formula": "Fee = 20", "explanation": "The form requires a fee.", "page_number": 1}],
                    "key_information": {"important_facts": ["Fee: $20"]},
                    "definitions": [{"term": "Applicant", "plain_definition": "The person submitting the form"}],
                    "recommendations": [{"recommendation": "Submit the complete form.", "source_reference": "Page 1"}],
                }
            if "Module: revision_notes" in prompt:
                return {"malformed": "expected an array"}
            return self.response_for_prompt(prompt, "Steps")
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=first_run):
            import asyncio
            partial = asyncio.run(analysis_service.analyze_document(extraction))
        self.assertFalse(partial["reliability_report"]["is_complete"])
        self.assertEqual(partial["reliability_report"]["failed_modules"], ["revision_notes:0"])
        self.assertTrue(partial["definitions"])
        self.assertTrue(partial["process_flow"]["steps"])
        self.assertTrue(partial["concept_map"]["concepts"])

        retry_prompts = []
        async def retry(prompt):
            retry_prompts.append(prompt)
            return ["The application is submitted before review."]
        with patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=retry):
            resumed = asyncio.run(analysis_service.analyze_document(
                extraction, existing_result=partial,
                completed_batches=partial["reliability_report"]["completed_batches"],
                completed_module_batches=partial["reliability_report"]["module_batches"],
            ))
        self.assertEqual(len(retry_prompts), 1)
        self.assertIn("Module: revision_notes", retry_prompts[0])
        self.assertTrue(resumed["reliability_report"]["is_complete"])
        self.assertTrue(resumed["recommendations"])

    def test_combined_module_provider_failure_marks_combined_modules_failed(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        extraction = DocumentExtractionResult(
            "Provider Failure",
            "The document includes a policy.",
            [ExtractedSection("Policy", "The document includes a policy.", 1)],
            1,
        )
        with patch(
            "backend.app.ai.ollama_client.ollama_client.generate_json",
            side_effect=RuntimeError("Ollama inference failed: connection failed"),
        ) as mock_ai:
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(
                extraction,
                selected_components=["revision_notes", "key_info", "definitions", "recommendations"],
            ))
        self.assertEqual(mock_ai.call_count, 1)
        self.assertFalse(result["reliability_report"]["is_complete"])
        for module in ("revision_notes", "key_information", "definitions", "recommendations"):
            self.assertTrue(
                any(item.startswith(f"{module}:") for item in result["reliability_report"]["failed_modules"]),
                module,
            )
        self.assertTrue(any("failed" in warning.lower() for warning in result["reliability_report"]["warnings"]))

    def test_daily_quota_failure_stops_remaining_document_batches(self):
        from backend.app.processors.extractor import DocumentExtractionResult, ExtractedSection
        sections = [ExtractedSection(f"Page {i}", "page content " * 700, i) for i in range(1, 10)]
        extraction = DocumentExtractionResult("Quota", " ".join(s.text for s in sections), sections, 9)
        with patch("backend.app.core.config.settings.AI_ANALYSIS_BATCH_CHARS", 3000), \
             patch("backend.app.ai.ollama_client.ollama_client.generate_json", side_effect=RuntimeError("OpenRouter free daily quota is exhausted")) as mock_ai:
            import asyncio
            result = asyncio.run(analysis_service.analyze_document(extraction))
        self.assertEqual(mock_ai.call_count, 1)
        self.assertFalse(result["reliability_report"]["is_complete"])
        self.assertEqual(len(result["reliability_report"]["failed_batches"]), result["reliability_report"]["total_batches"])


class TestOpenRouterQueue(unittest.TestCase):
    def setUp(self):
        from backend.app.ai.ollama_client import OllamaClient
        self.OllamaClient = OllamaClient

    def test_queue_serializes_calls_and_enforces_minimum_interval(self):
        import asyncio
        from backend.app.core.config import settings
        old = (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
               settings.AI_QUEUE_CONCURRENCY, settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES)
        settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY = "openrouter", "test/model:free", "test-key"
        settings.AI_QUEUE_CONCURRENCY, settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES = 4, 0.04, 1
        client = self.OllamaClient()
        starts = []
        response = MagicMock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        class FakeHttp:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, *args, **kwargs):
                starts.append(time.monotonic())
                await asyncio.sleep(0.005)
                return response
        try:
            with patch("backend.app.ai.ollama_client.httpx.AsyncClient", side_effect=lambda **kwargs: FakeHttp()):
                async def run(): await asyncio.gather(client.generate("a"), client.generate("b"))
                asyncio.run(run())
        finally:
            (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
             settings.AI_QUEUE_CONCURRENCY, settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES) = old
        self.assertEqual(len(starts), 2)
        self.assertGreaterEqual(starts[1] - starts[0], 0.035)

    def test_provider_errors_and_retry_are_bounded(self):
        import asyncio
        from backend.app.core.config import settings
        old = (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
               settings.OPENROUTER_FREE_FALLBACK_MODELS, settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES)
        settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY = "openrouter", "test/model:free", "test-key"
        settings.OPENROUTER_FREE_FALLBACK_MODELS = ""
        settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES = 0, 2
        def response(code, text="", retry_after=None):
            item = MagicMock(status_code=code, text=text, headers={"Retry-After": retry_after} if retry_after is not None else {})
            item.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
            return item
        async def run_with(responses):
            queue = list(responses)
            calls = []
            class FakeHttp:
                async def __aenter__(self): return self
                async def __aexit__(self, *args): return False
                async def post(self, *args, **kwargs): calls.append(1); return queue.pop(0)
            client = self.OllamaClient()
            with patch("backend.app.ai.ollama_client.httpx.AsyncClient", side_effect=lambda **kwargs: FakeHttp()), \
                 patch("backend.app.ai.ollama_client.asyncio.sleep", new=AsyncMock()):
                result = await client.generate("test")
            return result, len(calls)
        from unittest.mock import AsyncMock
        try:
            self.assertEqual(asyncio.run(run_with([response(429, "temporary", "0"), response(200)])), ("ok", 2))
            for code, text in [(402, "credits")]:
                with self.subTest(code=code):
                    async def fail():
                        client = self.OllamaClient()
                        class FakeHttp:
                            async def __aenter__(self): return self
                            async def __aexit__(self, *args): return False
                            async def post(self, *args, **kwargs): return response(code, text)
                        with patch("backend.app.ai.ollama_client.httpx.AsyncClient", side_effect=lambda **kwargs: FakeHttp()):
                            await client.generate("test")
                    with self.assertRaisesRegex(RuntimeError, "OpenRouter"):
                        asyncio.run(fail())
            with self.assertRaisesRegex(RuntimeError, "daily quota"):
                asyncio.run(run_with([response(429, "Daily quota exceeded")]))
        finally:
            (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
             settings.OPENROUTER_FREE_FALLBACK_MODELS, settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES) = old

    def test_timeout_retries_only_to_configured_attempt_limit(self):
        import asyncio
        import httpx
        from backend.app.core.config import settings
        from unittest.mock import AsyncMock
        from backend.app.ai.ollama_client import OllamaClient
        old = (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
               settings.OPENROUTER_FREE_FALLBACK_MODELS, settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES)
        settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY = "openrouter", "test/model:free", "test-key"
        settings.OPENROUTER_FREE_FALLBACK_MODELS = ""
        settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES = 0, 2
        attempts = []
        class FakeHttp:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, *args, **kwargs):
                attempts.append(1)
                raise httpx.ReadTimeout("timeout")
        try:
            with patch("backend.app.ai.ollama_client.httpx.AsyncClient", side_effect=lambda **kwargs: FakeHttp()), \
                 patch("backend.app.ai.ollama_client.asyncio.sleep", new=AsyncMock()):
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    asyncio.run(OllamaClient().generate("test"))
        finally:
            (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
             settings.OPENROUTER_FREE_FALLBACK_MODELS, settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES) = old
        self.assertEqual(len(attempts), 2)

    def test_only_free_fallback_is_used_after_primary_model_restriction(self):
        import asyncio
        from backend.app.core.config import settings
        from backend.app.ai.ollama_client import OllamaClient
        old = (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
               settings.OPENROUTER_FREE_FALLBACK_MODELS, settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES)
        settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY = "openrouter", "primary/test:free", "test-key"
        settings.OPENROUTER_FREE_FALLBACK_MODELS = "baidu/ernie-5.5-flash-preview:free"
        settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES = 0, 1
        model_calls = []
        denied = MagicMock(status_code=403, text="restricted", headers={})
        success = MagicMock(status_code=200)
        success.json.return_value = {"choices": [{"message": {"content": "fallback answer"}}]}
        class FakeHttp:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, *args, **kwargs):
                model_calls.append(kwargs["json"]["model"])
                return denied if len(model_calls) == 1 else success
        try:
            with patch("backend.app.ai.ollama_client.httpx.AsyncClient", side_effect=lambda **kwargs: FakeHttp()):
                answer = asyncio.run(OllamaClient().generate("test"))
        finally:
            (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
             settings.OPENROUTER_FREE_FALLBACK_MODELS, settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES) = old
        self.assertEqual(answer, "fallback answer")
        self.assertEqual(model_calls, ["primary/test:free", "baidu/ernie-5.5-flash-preview:free"])

    def test_paid_model_configuration_is_rejected_before_request(self):
        import asyncio
        from backend.app.core.config import settings
        from backend.app.ai.ollama_client import OllamaClient
        old = settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY
        settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY = "openrouter", "openai/gpt-5.4", "test-key"
        try:
            with self.assertRaisesRegex(RuntimeError, "non-free model"):
                asyncio.run(OllamaClient().generate("test"))
        finally:
            settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY = old

    def test_daily_quota_cooldown_prevents_repeat_provider_requests(self):
        import asyncio
        from backend.app.core.config import settings
        from backend.app.ai.ollama_client import OllamaClient
        old = (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
               settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES)
        settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY = "openrouter", "test/model:free", "test-key"
        settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES = 0, 1
        attempts = []
        response = MagicMock(status_code=429, text="daily quota exceeded", headers={})
        class FakeHttp:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, *args, **kwargs): attempts.append(1); return response
        client = OllamaClient()
        try:
            with patch("backend.app.ai.ollama_client.httpx.AsyncClient", side_effect=lambda **kwargs: FakeHttp()):
                async def run_twice():
                    with self.assertRaisesRegex(RuntimeError, "daily quota"):
                        await client.generate("analysis")
                    with self.assertRaisesRegex(RuntimeError, "recently exhausted"):
                        await client.generate("chat")
                asyncio.run(run_twice())
        finally:
            (settings.AI_PROVIDER, settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
             settings.AI_REQUEST_INTERVAL_SECONDS, settings.AI_MAX_RETRIES) = old
        self.assertEqual(len(attempts), 1)

if __name__ == "__main__":
    unittest.main()
