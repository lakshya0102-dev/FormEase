# FormEase — Setup and Deployment

## Services and free-tier limits

- Supabase supplies Auth, PostgreSQL, RLS, and private document Storage. Storage and database quotas depend on the current Supabase plan.
- OpenRouter supports free model variants with `:free` IDs. As checked on 2026-11-22, its free models are subject to shared daily/minute limits and failed calls may count toward them. The configured backup below is listed at zero token cost and supports chat completions. Availability can still change; no paid model is used as fallback.
- Render currently offers a free Docker web service suitable for a project demo. It sleeps after 15 minutes without inbound requests and can take about a minute to wake. It can restart and its filesystem is ephemeral. The free plan has limited CPU/RAM and no persistent disk, so all user files must remain in Supabase Storage. Free hosting is a demonstrator tier, not an uptime guarantee.

## Supabase setup

1. Create a Supabase project and enable Email/Password under Authentication → Providers.
2. Set the local Site URL to `http://localhost:3000` and add the development/deployment callback URLs if email confirmation is enabled.
3. Run [`database/schema.sql`](../database/schema.sql) in the Supabase SQL editor. This sets up application tables, RLS policies, the profile trigger, private `documents` bucket, and Storage policies.
4. The backend verifies legacy HS256 tokens with `SUPABASE_JWT_SECRET`; asymmetric project keys are verified through Supabase JWKS discovery.

## OpenRouter free models

Set `AI_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, and `OPENROUTER_MODEL` on the backend only. The backend rejects any configured model that is neither `:free` nor the official `openrouter/free` router. It never falls back to a paid model.

The default fallback ID is `baidu/ernie-5.5-flash-preview:free`; another explicitly verified free ID can be supplied as a comma-separated list through `OPENROUTER_FREE_FALLBACK_MODELS`. The ID is currently listed by OpenRouter as free and compatible with its chat completions API. A 402 or detected daily-quota response will not fail over. Temporary errors may try the configured free backup after bounded retries. The queue defaults to one concurrent request and a 3.5 second minimum gap; quota cooldown is in-memory for one hour.

Do not put `OPENROUTER_API_KEY` in `frontend/.env.local`, Vercel variables, `NEXT_PUBLIC_*`, or browser code. The frontend calls only the authenticated FastAPI backend.

## Local backend

From the repository root:

```bash
cp .env.example .env
# Enter Supabase and OpenRouter values in the root .env using a local editor.
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

The root `.env` must have Supabase settings, `AI_PROVIDER`, `OPENROUTER_API_KEY`, and a free `OPENROUTER_MODEL`. `SUPABASE_JWT_SECRET` is only needed for legacy HS256 projects. Optional settings include:

- `OPENROUTER_FREE_FALLBACK_MODELS` — comma-separated free-only model IDs; default is Baidu ERNIE 5.5 Flash Preview free.
- `AI_REQUEST_INTERVAL_SECONDS=3.5`, `AI_MAX_RETRIES=2`, `AI_QUEUE_CONCURRENCY=1` — shared provider queue behavior.
- `AI_ANALYSIS_BATCH_CHARS=10000` — bounded analysis batch size.
- `OCR_ENABLED=true`, `OCR_LANGUAGE=eng+hin`, `OCR_MIN_TEXT_CHARS=40` — local OCR behavior.
- `MAX_UPLOAD_SIZE_MB=100`, `CORS_ORIGINS` — upload cap and exact browser origins.

### Local OCR dependencies

The Python requirements include `pytesseract` and Pillow. OCR also requires the Tesseract system executable and the language data named by `OCR_LANGUAGE`.

- macOS: install Tesseract and English/Hindi language data with your package manager, then check `tesseract --list-langs` includes `eng` and `hin`.
- Debian/Ubuntu: `sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin`.

OCR is attempted only on pages with fewer than `OCR_MIN_TEXT_CHARS` text-layer characters. OCR recognition can be imperfect; pages are marked with warnings. If Tesseract is missing, text-layer extraction continues and scanned pages receive warnings. OCR code is covered with a mocked engine in tests; real local OCR accuracy must be checked on representative scans.

## Local frontend

Create `frontend/.env.local` from `frontend/.env.example` and set only:

- `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`
- `NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY=<publishable-or-anon-key>`

Then:

```bash
cd frontend
npm install
npm run typecheck
npm run lint
npm run build
npm run dev
```

The Supabase anon/publishable key is browser-visible by design; RLS must remain enabled. Never configure the service-role or OpenRouter key in the frontend.

## Production deployment: Render backend + Vercel frontend

The Python 3.12 Vercel runtime repeatedly failed while resolving the configured Supabase hostname: both `socket.getaddrinfo()` and aiohttp/c-ares returned `OSError` errno 16 before TCP/TLS or an HTTP response. The production topology therefore keeps Next.js on Vercel and runs FastAPI in the Docker service described by [`render.yaml`](../render.yaml). This avoids running JWT key retrieval in the affected Python runtime; it does not change JWT verification.

1. Create a Render Blueprint from this repository. The `formease-api` service uses the root [`Dockerfile`](../Dockerfile), exposes `/api/v1/health` as its health check, and sets the production frontend URL/CORS origin.
2. In Render, supply the prompted backend-only values: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`. Set `SUPABASE_JWT_SECRET` only if the project still issues legacy HS256 tokens. Never put these values in Vercel frontend variables. Wait for the Render health check to pass and note the service’s actual public URL.
3. In Vercel, keep the repository root as the project root and set `NEXT_PUBLIC_API_URL` to `<Render service URL>/api/v1` for Production (for example, `https://formease-api.onrender.com/api/v1` if that is the service URL). Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` as before. Redeploy the frontend so the public API URL is included in its build.
4. Add `https://formease-virid.vercel.app` to Supabase Auth's allowed redirect URLs and Site URL if not already present.
5. Verify the Render `/api/v1/health` endpoint, then verify the Vercel app reaches it; test both an invalid JWT (must return 401 after a successful JWKS retrieval) and an existing authenticated session (document listing must return successfully).

The Render free service can sleep after inactivity and has ephemeral local storage; cold starts may take about a minute. Supabase remains the durable store for all documents and data. For an always-on production service, select a paid Render instance only after approving its cost. Never rely on local backend files for user data.

## Local verification commands

```bash
python3 -m pytest backend/tests -q
python3 -m compileall -q backend/app backend/tests
cd frontend && npm run typecheck && npm run lint && npm run build
```

Automated provider tests use mocks and do not spend OpenRouter requests. Live Supabase Auth/RLS/Storage and live OpenRouter inference must be checked with project-owned test accounts separately; unit tests alone cannot verify those services.
