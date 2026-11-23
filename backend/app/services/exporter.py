"""
Export Service for FormEase.
Generates professional PDF and Markdown exports of the complete document analysis.
Includes Unicode safety and clean typography.
"""
from typing import Dict, Any, List
import io
import datetime
import re

class ExportService:
    @staticmethod
    def _is_placeholder(value: Any) -> bool:
        text = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
        if not text:
            return True
        return any((
            text.startswith("this section provides an overview"),
            text.startswith("this section provides a concise summary"),
            text.startswith("this section explains each section"),
            text.startswith("a concise summary of this part"),
            text.startswith("plain explanation of"),
        ))

    @staticmethod
    def generate_markdown(document_title: str, analysis: Dict[str, Any]) -> str:
        """
        Formats analysis into clean, structured Markdown.
        """
        lines = []
        lines.append(f"# FormEase Document Analysis: {document_title}")
        lines.append(f"*Generated on: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*\n")
        lines.append("---\n")

        # 1. Overview
        overview = analysis.get("overview", {})
        if overview:
            lines.append("## 1. Document Overview")
            for label, key in (("Subject", "document_subject"), ("Purpose", "main_purpose"), ("Target Audience", "target_audience")):
                if overview.get(key):
                    lines.append(f"- **{label}:** {overview[key]}")
            lines.append("")

        # 2. Executive Summary
        summary = analysis.get("summary", "")
        if summary:
            lines.append("## 2. Executive Summary")
            lines.append(f"{summary}\n")

        # 3. Section Explanations
        sections = analysis.get("sections", [])
        if sections:
            lines.append("## 3. Section-by-Section Explanations")
            for sec in sections:
                heading = str(sec.get("heading") or "").strip()
                explanation = str(sec.get("simplified_explanation") or "").strip()
                if not heading or ExportService._is_placeholder(heading):
                    continue
                if not explanation or ExportService._is_placeholder(explanation):
                    continue
                lines.append(f"### {heading} (Page {sec.get('page_number', 1)})")
                lines.append(f"{explanation}\n")
                if sec.get("key_points"):
                    lines.append("**Key Points:**")
                    for kp in sec["key_points"]:
                        lines.append(f"- {kp}")
                    lines.append("")

        # 4. Key Information
        key_info = analysis.get("key_information", {})
        if key_info:
            lines.append("## 4. Key Information & Obligations")
            if key_info.get("critical_obligations"):
                lines.append("### Critical Obligations:")
                for ob in key_info["critical_obligations"]:
                    lines.append(f"- {ob}")
            if key_info.get("deadlines_and_dates"):
                lines.append("### Deadlines & Dates:")
                for d in key_info["deadlines_and_dates"]:
                    lines.append(f"- {d}")
            if key_info.get("warnings_and_penalties"):
                lines.append("### Warnings & Penalties:")
                for w in key_info["warnings_and_penalties"]:
                    lines.append(f"- {w}")
            if key_info.get("important_conditions"):
                lines.append("### Important Conditions:")
                for condition in key_info["important_conditions"]:
                    lines.append(f"- {condition}")
            if key_info.get("important_facts"):
                lines.append("### Important Facts & Figures:")
                for fact in key_info["important_facts"]:
                    lines.append(f"- {fact}")
            lines.append("")

        # 5. Process & Workflow
        process = analysis.get("process_flow", {})
        if process and process.get("has_process"):
            lines.append(f"## 5. Process: {process.get('process_title', 'Workflow')}")
            for s in process.get("steps", []):
                lines.append(f"{s.get('step_number', 1)}. **{s.get('title', 'Step')}**: {s.get('description', '')}")
                if s.get("condition"):
                    lines.append(f"   - Condition: {s['condition']}")
                if s.get("inputs"):
                    lines.append(f"   - Inputs: {', '.join(s['inputs'])}")
                if s.get("outputs"):
                    lines.append(f"   - Outputs: {', '.join(s['outputs'])}")
            titles = [step.get("title") for step in process.get("steps", []) if step.get("title")]
            if len(titles) >= 2:
                lines.append("")
                lines.append("Static flow: " + " -> ".join(titles))
            if process.get("mermaid_syntax"):
                lines.append("\n```mermaid")
                lines.append(process["mermaid_syntax"])
                lines.append("```\n")

        # 6. Definitions
        definitions = analysis.get("definitions", [])
        if definitions:
            lines.append("## 6. Glossary & Definitions")
            for d in definitions:
                lines.append(f"- **{d.get('term', '')}**: {d.get('plain_definition', '')}")
            lines.append("")

        # 7. Recommendations
        recommendations = analysis.get("recommendations", [])
        if recommendations:
            lines.append("## 7. Contextual Recommendations")
            for r in recommendations:
                lines.append(f"- **[{r.get('category', 'Notice')}]** {r.get('recommendation', '')} *(Ref: {r.get('source_reference', 'Doc')})*")
            lines.append("")

        formulas = analysis.get("formulas", [])
        if formulas:
            lines.append("## Formulas")
            for item in formulas:
                lines.append(f"- **{item.get('formula', '')}**: {item.get('explanation', '')} (Page {item.get('page_number', 'unknown')})")
            lines.append("")

        revision_notes = analysis.get("revision_notes", [])
        if revision_notes:
            lines.append("## Revision Notes")
            lines.extend(f"- {note}" for note in revision_notes)
            lines.append("")

        concept_map = analysis.get("concept_map", {})
        if concept_map.get("concepts"):
            lines.append("## Document Concept Map")
            if concept_map.get("central_topic"):
                lines.append(f"Central topic: **{concept_map['central_topic']}**")
            for concept in concept_map["concepts"]:
                lines.append(f"- **{concept.get('name', '')}**: {concept.get('description', '')} (Page {concept.get('page_number', 'unknown')})")
            for relation in concept_map.get("relationships", []):
                lines.append(f"- {relation.get('from', '')} {relation.get('label') or 'relates to'} {relation.get('to', '')}")
            concept_names = [concept.get("name") for concept in concept_map.get("concepts", []) if concept.get("name")]
            if concept_map.get("central_topic") and concept_names:
                lines.append("")
                lines.append("Static concept map: " + concept_map["central_topic"] + " -> " + "; ".join(concept_names))
            if concept_map.get("mermaid_syntax"):
                lines.extend(["", "```mermaid", concept_map["mermaid_syntax"], "```"])
            lines.append("")

        reliability = analysis.get("reliability_report", {})
        if reliability.get("is_complete") is False or reliability.get("warnings"):
            lines.append("## Processing Status")
            lines.append("Analysis is partial; review these warnings and retry missing parts:") if reliability.get("is_complete") is False else None
            lines.extend(f"- {warning}" for warning in reliability.get("warnings", []))
            lines.append("")

        lines.append("\n---\n*FormEase — Understand Documents. Simplify Complexity. Step by Step.*")
        return "\n".join(lines)

    @staticmethod
    def generate_pdf(document_title: str, analysis: Dict[str, Any]) -> bytes:
        """
        Generates binary PDF export with ReportLab or plain-text fallback.
        """
        md_text = ExportService.generate_markdown(document_title, analysis)
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
            styles = getSampleStyleSheet()
            
            story = []
            title_style = styles['Heading1']
            h2_style = styles['Heading2']
            normal_style = styles['Normal']
            
            story.append(Paragraph(f"FormEase Analysis: {document_title}", title_style))
            story.append(Spacer(1, 12))
            
            in_mermaid = False
            for line in md_text.split("\n"):
                clean = line.strip()
                if clean == "```mermaid":
                    in_mermaid = True
                    story.append(Paragraph("Diagram syntax is included in the Markdown export; the document steps and relationships are listed above.", normal_style))
                    continue
                if in_mermaid:
                    if clean == "```":
                        in_mermaid = False
                    continue
                if not clean:
                    story.append(Spacer(1, 6))
                elif clean.startswith("# "):
                    continue # title already added
                elif clean.startswith("## "):
                    story.append(Paragraph(clean.replace("## ", ""), h2_style))
                    story.append(Spacer(1, 6))
                elif clean.startswith("### "):
                    story.append(Paragraph(f"<b>{clean.replace('### ', '')}</b>", normal_style))
                else:
                    # Sanitize HTML tags for ReportLab Paragraph
                    safe_line = clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    story.append(Paragraph(safe_line, normal_style))

            doc.build(story)
            pdf_bytes = buf.getvalue()
            buf.close()
            return pdf_bytes
        except ImportError:
            # Fallback text representation if reportlab is not yet installed
            return md_text.encode("utf-8")

export_service = ExportService()
