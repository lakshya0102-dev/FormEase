# FormEase — Verification Record

## Local verification (2026-11-22)

- Python compilation: passed for modified backend modules.
- `./.venv/bin/python -m pytest backend/tests -q`: **50 passed, 1 subtest passed**. Tests use mocked AI, auth/database clients, and OCR where appropriate; no OpenRouter request was made.
- `npm run typecheck`: passed.
- `npm run lint`: passed with no warnings or errors.
- `npm run build`: passed. Next.js compiled, checked types, generated static pages, and collected build traces.
- Coverage includes multi-page PDF ordering, OCR fallback behavior, DOCX table extraction, chunking and analysis recovery, concept map/diagram assembly, grounded multi-passage chat, source references, duplicate chat submission, rate limiting, queue pacing, free-only fallback restrictions, timeout and quota handling, auth/ownership checks, and export assembly.

## Not verified live

- The automated suite uses mocks and makes no provider calls. A separate single-token check against the configured `:free` model was attempted with fallbacks disabled, but the environment could not connect to OpenRouter, so no response was received and live inference remains unverified.
- Supabase registration, sign-in, JWT/RLS behavior, database persistence, private storage, and deployed user isolation need a real Supabase project and test account.
- OCR was tested with a mocked Tesseract engine. The local machine must have Tesseract installed with the configured language packs to OCR actual scans.
- No browser-based upload-to-analysis/chat/history/export integration test or deployment was performed. A successful production build verifies compilation and prerendering, not external services or interactive behavior.
- Direct local Uvicorn startup was attempted, but this environment denied binding a listening port (`operation not permitted`). FastAPI route coverage ran through the in-process TestClient instead.
- Tesseract and Docker are not installed in the current environment. The deployment Dockerfile installs Tesseract and its English/Hindi language packs, but that image could not be built here.

## Known runtime boundaries

- DOCX files do not reliably preserve printed page boundaries; their references use document order, with a warning shown in extraction metadata.
- Quota cooldown, request queue pacing, chat request limiting, and per-document locks are process-local. On a restarted or multi-instance host, those limits/state are not coordinated across instances.
- Free OpenRouter model availability and provider limits can change; the backend never falls back to a paid model.

Run the local and deployment instructions in [`setup.md`](setup.md) to verify the live services with a project-owned test account.
