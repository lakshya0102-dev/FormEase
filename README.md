# FormEase — AI Document Simplifier Platform

> **Understand Documents. Simplify Complexity. Step by Step.**

[![Backend Tests](https://img.shields.io/badge/tests-mocked%20suite-brightgreen.svg)]()
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-teal.svg)]()
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)]()
[![AI](https://img.shields.io/badge/Inference-OpenRouter%20Free-orange.svg)]()

FormEase is a production-minded full-stack web platform designed to simplify complex, lengthy, and bureaucratic documents into structured, accessible, plain-language explanations.

---

## 1. Problem Statement & Solution

### The Problem
Citizens, employees, and patients are routinely overwhelmed by dense legal agreements, bureaucratic government notices, tenancy contracts, medical waivers, and compliance policies. These documents obscure critical deadlines, legal liabilities, and procedural requirements under confusing jargon.

### The FormEase Solution
FormEase ingests raw PDF, DOCX, TXT documents or pasted text and transforms them into:
1. **Executive Overview & Summary**: High-level purpose and target audience.
2. **Section Explorer**: Clause-by-clause translations with explicit risk ratings (Low, Medium, High).
3. **Procedural Workflows**: Automatic extraction of chronological process steps with switchable Mermaid flowcharts.
4. **Key Information**: Actionable extraction of critical obligations, deadlines, and penalty clauses.
5. **Interactive Definitions**: Context-aware jargon glossary.
6. **Document-Grounded Chatbot**: Ask questions with answers strictly constrained to retrieved evidence passages.
7. **Export Engine**: Export full analyses to professional PDF and formatted Markdown.

---

## 2. Free-Model Architecture

The platform keeps model credentials on the backend and:
- **Free models only**: The backend rejects OpenRouter model IDs that are not free variants. It can fail over to explicitly configured free model IDs only.
- **Provider boundary**: Browsers never call OpenRouter directly; prompts are sent by FastAPI. Document text leaves the backend for model inference, so this is not on-device processing.
- **Optional local OCR**: Tesseract reads scanned pages on the backend; it does not use a paid OCR API.
- **Supabase Authentication & Row Level Security (RLS)**: Enforces multi-tenant data isolation at the PostgreSQL level.
- **Scikit-Learn TF-IDF Retrieval**: Deterministic, verifiable passage matching for the document chatbot.
- **Real Supabase Auth**: Email/password sign-in with session tokens forwarded to FastAPI for server-side verification.

```
USER BROWSER
    │
    ▼ (HTTPS / Responsive Next.js Web)
NEXT.JS FRONTEND (Vercel)
    │
    ▼ (Authenticated REST API / JWT)
FASTAPI BACKEND
    │
    ├── Supabase Authentication & PostgreSQL with RLS
    ├── Supabase Private Storage (Raw files)
    ├── Scikit-Learn TF-IDF Retrieval Engine
    ├── OpenRouter free chat models (server-side only)
    └── Tesseract OCR (local backend process, scanned pages only)
```

---

## 3. Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | Next.js 14, React 18, TypeScript, Tailwind CSS, Lucide Icons, Mermaid |
| **Backend API** | Python 3.11, FastAPI, Pydantic, Uvicorn |
| **AI Inference** | OpenRouter-compatible chat completions with free-only model enforcement |
| **NLP & Retrieval** | Scikit-learn (TF-IDF vectorizer), NumPy |
| **Document Parsing** | PyMuPDF (fitz), python-docx, Tesseract OCR (optional system binary) |
| **Database & Auth** | Supabase PostgreSQL, Supabase Auth, Row Level Security |
| **Export Generation**| ReportLab (PDF), Markdown |

---

## 4. Project Directory Structure

```
FormEase/
├── frontend/                   # Next.js 14 React TypeScript Application
│   ├── src/
│   │   ├── app/                # App router (layout.tsx, page.tsx, globals.css)
│   │   ├── components/         # Modular UI components
│   │   │   ├── layout/         # Collapsible Sidebar & Header
│   │   │   ├── dashboard/      # Main dashboard & metrics
│   │   │   ├── upload/         # Multi-file dropzone & review
│   │   │   ├── viewer/         # Interactive analysis dashboard & original reader
│   │   │   ├── chat/           # Evidence-grounded document chatbot
│   │   │   ├── library/        # Document library & search
│   │   │   ├── trash/          # Recently Deleted trash view
│   │   │   └── settings/       # Language (EN/HI), Depth, and configured provider status
│   │   ├── lib/                # API client & Supabase helpers
│   │   └── types/              # Shared TypeScript interfaces
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
├── backend/                    # FastAPI Python Backend
│   ├── app/
│   │   ├── main.py             # FastAPI entrypoint & router configuration
│   │   ├── core/               # App configuration & Supabase security/JWT
│   │   ├── api/v1/             # Modular REST endpoints (documents, analysis, chat, export)
│   │   ├── processors/         # PyMuPDF/docx extractors & recursive chunker
│   │   ├── retrieval/          # TF-IDF retrieval engine
│   │   ├── ai/                 # OpenRouter/local Ollama provider client & prompts
│   │   └── services/           # Document ingestion, analysis orchestrator & export
│   ├── tests/                  # Comprehensive unit & integration test suite
│   └── requirements.txt
├── Dockerfile                  # FastAPI + English/Hindi Tesseract runtime
├── render.yaml                 # Free Render backend blueprint
├── database/
│   ├── schema.sql              # Supabase PostgreSQL schema with RLS & indexes
│   └── migrations/
├── docs/                       # University Project Documentation
│   ├── prompt-engineering.md   # 5-part prompts, iterations, 3-tool attribution
│   ├── architecture.md         # System architecture & topology
│   ├── database.md             # Schema specification
│   ├── setup.md                # Installation and local development guide
│   └── testing.md              # Test execution records
├── .env.example                # Environment configuration template
├── .gitignore
└── README.md
```

---

## 5. Quickstart Guide

### Step 1: Configure Environment
```bash
cp .env.example .env
```
Fill in Supabase credentials and the free OpenRouter model/key in `.env`. The key stays backend-only. If using local OCR outside Docker, install Tesseract and the `eng`/`hin` language packs.

### Step 2: Run Backend Tests & Server
```bash
# Run automated tests
python3 -m pytest backend/tests -q

# Start FastAPI server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation will be live at `http://localhost:8000/docs`.

### Step 3: Run Frontend
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## 6. Free-tier limitations

OpenRouter free models have shared account and provider rate limits; failed attempts can count toward daily caps. Render's free backend can sleep after inactivity and has an ephemeral filesystem, so all user documents and history must stay in Supabase. See [docs/setup.md](docs/setup.md) before deployment.

## 7. University Documentation & Prompt Engineering
A complete academic documentation dossier is provided in `docs/`:
- **5-Part Prompts**: Role, Task, Context, Constraints, Output Format.
- **Empirical Iterations**: Raw unconstrained outputs vs. bounded grounded outputs.
- **3-Tool Attribution**: See the project report for the tools used during planning, runtime inference, and code review.

---

## 8. License
FormEase is developed as an open educational and commercial document productivity platform.
# FormEase
