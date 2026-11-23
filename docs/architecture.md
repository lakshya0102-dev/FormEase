# FormEase — Architecture Specification

## System topology

```text
User browser
  └─ Next.js (Vercel, HTTPS)
       └─ authenticated REST requests (Supabase access JWT)
            └─ FastAPI (Render or another HTTPS Python host)
                 ├─ Supabase Auth JWT/JWKS verification
                 ├─ Supabase PostgreSQL with row-level security
                 ├─ Supabase private Storage for original documents
                 ├─ TF-IDF retrieval over extracted source chunks
                 ├─ One shared, throttled OpenRouter client
                 └─ PyMuPDF + optional local Tesseract OCR
```

## Security and data handling

- The browser receives only the Supabase project URL and public anon/publishable key. OpenRouter and service-role credentials stay in the backend environment.
- FastAPI verifies each user's Supabase JWT and scopes database/storage requests to that user. PostgreSQL RLS is an additional ownership boundary.
- Original uploaded documents live in the private Supabase Storage bucket; backend local disk is temporary only.
- Document text sent for analysis or chat is sent from FastAPI to the configured OpenRouter free model. It is not on-device inference. Keep sensitive documents off the service unless the data owner accepts the provider's current terms and data handling.
- OpenRouter requests share one queue. Free model IDs are enforced; retries may fail over only to configured IDs ending in `:free`. Daily quota responses are cached briefly to avoid repeated calls.
- Scanned-PDF OCR is local to the backend container and requires Tesseract plus the requested language data. It does not call an OCR SaaS.

## Analysis and chat flow

1. FastAPI validates size and file type, extracts text in page order, runs local OCR only on pages with no useful text layer, and chunks the result while retaining page and section metadata.
2. Original bytes go to private Supabase Storage; metadata and source chunks go to PostgreSQL under RLS.
3. Analysis batches bounded source text, persists completed parts into the analysis JSON progress report, and marks the document complete only when every requested batch succeeded.
4. Retry skips completed batch indexes. An incomplete analysis remains viewable with a retry action.
5. Chat retrieves up to three ranked passages from original document chunks, sends only those passages plus conversation context to the model, and stores source passages/pages alongside the answer.

## Deployment topology

- Next.js frontend: Vercel.
- FastAPI backend: Docker-capable host such as Render's free web service for a demonstrator.
- Supabase Auth, PostgreSQL, and Storage: persistent hosted data services.
- OpenRouter: free-only models; usage is still rate limited.

The Render free service sleeps after 15 minutes without requests, can take about a minute to wake, can restart, and has ephemeral local storage. Supabase must remain the source of persistent files and data. OCR on a 512 MB free instance is best-effort and may be memory constrained for unusually large scans. See [setup.md](setup.md) for deployment steps and limits.
