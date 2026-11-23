# FormEase — Database & Storage Specification

## 1. Relational Schema Summary
The persistence layer is managed by Supabase PostgreSQL with strict Row Level Security (RLS).

### Tables:
1. `profiles`: User preferences (language: en/hi, depth: simple/balanced/detailed, theme).
2. `documents`: Document metadata, status, page count, storage path, soft-deletion tracking.
3. `document_sections`: Extracted headings and raw text chunks mapped to page numbers.
4. `document_chunks`: Structured text chunks with token estimates and overlap for retrieval.
5. `analyses`: Master analysis record containing overview, summary, process flow, and key info.
6. `analysis_components`: Individual clauses and sections with risk rating and source page references.
7. `analysis_versions`: Preserves previous versions during user interactive refinements.
8. `conversations` & `messages`: Stores chatbot queries, answers, source passage references, and similarity scores.
9. `annotations`: Personal notes and text highlights per document.
10. `feedback`: Thumbs up/down evaluations of chatbot answers.
11. `processing_jobs`: Database-backed asynchronous job queue tracking progress stages.

## 2. Row Level Security Policies
Every table enforces `auth.uid() = user_id` for all operations. Sub-resources (e.g. `messages` and `analysis_components`) join against parent records to ensure cross-tenant data leakage is prevented at the database engine level.
