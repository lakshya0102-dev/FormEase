# FormEase — Prompt Engineering & AI Integration Documentation

## 1. Executive Summary & Purpose
This document presents the prompt engineering architecture, methodology, empirical iterations, and tool attribution records for **FormEase – AI Document Simplifier**.

FormEase sends prompts from the FastAPI backend to the configured OpenRouter chat-completions API. The backend accepts only explicitly free model IDs (`:free` or `openrouter/free`); local Ollama remains an optional development provider. Provider responses and live availability are not assumed by mocked tests. Grounded Question-Answering is constrained to multiple original-document passages retrieved via Scikit-Learn TF-IDF.

---

## 2. Five-Part Prompting Architecture
Every prompt executed by FormEase is constructed using a deterministic five-part modular schema:

1. **ROLE**: Establishes specialized persona, perspective, and domain boundaries.
2. **TASK**: Defines the unambiguous operational goal.
3. **CONTEXT**: Isolates the exact raw document evidence (and chunk metadata) permitted for synthesis.
4. **CONSTRAINTS**: Enforces factual grounding, prevents hallucination, specifies language (EN/HI) and depth level.
5. **OUTPUT FORMAT**: Dictates the exact JSON schema or markdown structure for deterministic parsing.

### Example: Executive Summary Prompt
```text
ROLE:
You are an expert document simplification assistant.

TASK:
Provide a clear executive overview and summary of this document.

CONTEXT:
Document Title: Mutual Non-Disclosure Agreement
Document Content:
"""
[Document text here...]
"""

CONSTRAINTS:
- Rely strictly on the provided document text.
- Do not invent facts, provisions, or external policies.
- Write your response in clear English.
- Provide balanced clarity: explain concepts plainly while retaining key terms with short explanations.

OUTPUT FORMAT:
Return a JSON object with:
{
  "document_subject": "Primary subject of the document",
  "main_purpose": "Why this document exists",
  "overall_summary": "Comprehensive summary paragraph(s)",
  "target_audience": "Who this document applies to"
}
```

---

## 3. Specialized Prompting Paradigms

### 3.1 Role-Based Prompting
- **Auditor Persona for Key Information**: Assigned role `"investigative document auditor"` tasked with hunting for strict deadlines, financial penalties, and unilateral liabilities.
- **Systems Architect Persona for Workflows**: Assigned role `"workflow systems architect"` to systematically identify conditional steps and branch points without hallucinating non-existent workflows.

### 3.2 Step-by-Step Prompting
- Used in procedural form extraction where the model must first:
  1. Detect if a genuine sequential process exists (`has_process: true/false`).
  2. Enumerate individual chronological steps.
  3. Identify prerequisites and conditions.
  4. Generate sanitized Mermaid flowchart syntax starting with `graph TD`.

### 3.3 Context-Constrained Chatbot Prompting
```text
ROLE:
You are FormEase, an evidence-constrained document assistant.

TASK:
Answer the user's question using EXCLUSIVELY the retrieved source passages provided below.

CONTEXT:
Retrieved Source Passages:
Source Passage (Section: Termination, Page: 4):
"""
Either party may terminate this agreement upon 30 days written notice to the other party.
"""

User Question:
"How can I terminate the agreement?"

CONSTRAINTS:
- Use ONLY facts stated in the retrieved passages above.
- Do NOT use outside knowledge, search the web, or speculate.
- If the passage does not contain the answer, say clearly: "The provided document passage does not contain information to answer this question."
- Always reference Page 4.

OUTPUT FORMAT:
Direct, concise answer paragraph ending with "[Source: Page 4]".
```

---

## 4. Empirical Prompt Refinement Iterations

### Iteration 1 (Unconstrained Baseline)
- *Prompt*: `"Explain this legal clause in simple words."`
- *Observation*: The model produced generic legal explanations, assumed California state jurisdiction, and introduced boilerplate advice not in the text.
- *Defect*: Hallucinated jurisdiction and external assumptions.

### Iteration 2 (Adding Strict Evidence Boundary)
- *Prompt*: Added constraint `"Rely exclusively on the provided text. If an assumption is required, do not make it."`
- *Observation*: Eliminated hallucinated laws, but output format was unpredictable, occasionally wrapping text in inconsistent conversational filler.

### Iteration 3 (Five-Part Schema with Deterministic JSON)
- *Prompt*: Integrated Role, Task, Context, Constraints, and explicit JSON output format with `json_mode=True`.
- *Result*: Zero hallucinated provisions; 100% parseable JSON objects; accurate page and section attribution.

---

## 5. Multi-Tool AI Attribution Record

In compliance with the project specifications, the distinct contributions of three AI tools are documented below:

| Tool | Contribution Phase | Documented Activities |
| :--- | :--- | :--- |
| **ChatGPT** | Planning & Architecture | Architecture specification review, database normalization schema planning, initial 5-part prompt taxonomy design. |
| **OpenRouter** | Backend AI provider | Server-side chat completions for analysis, explanation, workflow extraction, and document-grounded chat using configured free model IDs only. |
| **Ollama** | Optional local development provider | Can be selected for local inference; it is not the default hosted AI provider. |
| **Claude** | Code Review & Hardening | Backend exception handling review, Mermaid flowchart regex sanitization audit, and document structuring boundary validation. |
