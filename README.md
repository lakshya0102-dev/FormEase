# FormEase – AI Document Simplifier

**Turn complex documents into clear explanations, structured notes, visual diagrams, and interactive learning experiences.**

FormEase is an AI-powered document analysis platform designed to make learning and understanding complex information easier. Upload a document, analyze its contents, explore concepts through visual diagrams, and interact with your material using AI.

<p align="center">
  <a href="https://formease-virid.vercel.app">Live Application</a> •
  <a href="https://github.com/lakshya0102-dev/FormEase">GitHub Repository</a> •
  <a href="https://formease-api.onrender.com/api/v1/health">API Health</a>
</p>

---

## Overview

Understanding lengthy technical documents, academic notes, and complex study materials can be time-consuming.

FormEase simplifies this process by combining document processing, AI-powered analysis, information retrieval, and interactive visualizations into one platform.

Whether you are studying computer networks, biology, mathematics, machine learning, or business concepts, FormEase helps transform dense material into more understandable learning resources.

## Features

### 1. AI-Powered Document Analysis
- Upload and analyze learning documents.
- Extract and process document content.
- Generate structured explanations and summaries.
- Break complex information into manageable sections.
- Support learning across multiple subject areas.

### 2. Interactive Concept Maps
- Generate visual concept maps from document content.
- Represent relationships between concepts.
- Render diagrams using Mermaid.
- Zoom and explore diagrams interactively.

### 3. Process Flowcharts
- Convert complex processes into visual flowcharts.
- Generate step-by-step representations.
- Make technical workflows easier to understand.

### 4. AI Document Chat
- Interact with analyzed documents.
- Ask questions about document content.
- Retrieve relevant information using document-based context.

### 5. Reference Diagrams
- Discover relevant external reference images and diagrams.
- Display source information and attribution where available.
- Supplement AI-generated explanations with visual references.

### 6. Document Management
- Manage uploaded documents through the Document Library.
- Access previously processed documents.
- Organize and revisit learning materials.

### 7. Authentication and Security
- Supabase-powered authentication.
- Individual user accounts.
- JWT-based authentication and verification.
- Protected backend API endpoints.

---

## Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | Next.js, React, TypeScript |
| Styling | Tailwind CSS |
| Backend | Python, FastAPI |
| Database | Supabase |
| Authentication | Supabase Auth, JWT |
| AI Integration | OpenRouter |
| Diagram Rendering | Mermaid |
| Document Processing | Python document-processing libraries |
| Deployment | Vercel, Render |
| Version Control | Git, GitHub |

---

## System Architecture

FormEase uses a decoupled full-stack architecture.

```text
                 USER
                   |
                   v
          NEXT.JS FRONTEND
              (Vercel)
                   |
                   v
            FASTAPI BACKEND
               (Render)
                   |
          +--------+--------+
          |        |        |
          v        v        v
       SUPABASE  OPENROUTER  DOCUMENT
       AUTH/DB      AI       PROCESSING
          |        |        |
          +--------+--------+
                   |
                   v
          ANALYSIS & RETRIEVAL
                   |
          +--------+--------+
          |                 |
          v                 v
     CONCEPT MAPS       FLOWCHARTS
          |                 |
          +--------+--------+
                   |
                   v
             USER INTERFACE
```

### Production Deployment

| Component | Platform |
|---|---|
| Frontend | Vercel |
| Backend API | Render |
| Authentication | Supabase Auth |
| Database | Supabase |
| AI Services | OpenRouter |

**Live URLs**

- Application: https://formease-virid.vercel.app
- Backend: https://formease-api.onrender.com
- Health Check: https://formease-api.onrender.com/api/v1/health

---

## Project Structure

```text
FormEase/
│
├── backend/
│   ├── app/
│   │   ├── ai/
│   │   ├── api/
│   │   ├── core/
│   │   ├── processors/
│   │   ├── retrieval/
│   │   └── services/
│   │
│   ├── tests/
│   └── requirements.txt
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   │
│   └── package.json
│
├── database/
│
├── docs/
│
├── Dockerfile
├── render.yaml
├── vercel.json
├── .env.example
└── README.md
```

---

## Getting Started

Follow these instructions to run FormEase locally.

### Prerequisites

- Node.js and npm
- Python 3.11 or a compatible supported version
- Git
- A Supabase project
- An OpenRouter API key

### 1. Clone the Repository

```bash
git clone https://github.com/lakshya0102-dev/FormEase.git

cd FormEase
```

### 2. Backend Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

On Windows:

```bash
.venv\Scripts\activate
```

Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

Configure the backend environment variables using the provided `.env.example` as your reference.

Start the backend:

```bash
uvicorn backend.app.main:app --reload --port 8000
```

If the repository's Python package layout requires running from the backend directory, use:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Backend API:

```text
http://localhost:8000
```

API documentation:

```text
http://localhost:8000/docs
```

### 3. Frontend Setup

Open another terminal:

```bash
cd frontend
npm install
```

Create `frontend/.env.local` and configure the frontend environment variables.

Start the development server:

```bash
npm run dev
```

Frontend:

```text
http://localhost:3000
```

---

## Environment Variables

Never commit actual credentials, API keys, service-role keys, or secret tokens.

### Frontend

Configure these in `frontend/.env.local`:

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase public client key |
| `NEXT_PUBLIC_API_URL` | Backend API base URL |

Example local API URL:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### Backend

Configure the backend variables using the repository's `.env.example`:

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project base URL |
| `SUPABASE_ANON_KEY` | Supabase public API key |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side privileged Supabase access, if required |
| `OPENROUTER_API_KEY` | OpenRouter AI integration |
| `ENVIRONMENT` | Application environment |
| `DEBUG` | Debug mode |
| `CORS_ORIGINS` | Allowed frontend origins |

**Important:** `SUPABASE_URL` must contain only the Supabase project base URL, without `/rest/v1/` or another endpoint path.

Production credentials must be configured through the respective Vercel and Render environment settings.

---

## API

The backend exposes versioned endpoints under:

```text
/api/v1
```

Health check:

```http
GET /api/v1/health
```

Production health endpoint:

https://formease-api.onrender.com/api/v1/health

Interactive API documentation is available at:

```text
/docs
```

when the backend is running with API documentation enabled.

---

## Testing

Run backend tests:

```bash
python -m pytest backend/tests -q
```

Run frontend type checking:

```bash
cd frontend
npm run typecheck
```

Build the frontend:

```bash
npm run build
```

---

## Deployment

FormEase uses separate deployment services for the frontend and backend.

### Frontend – Vercel

The Next.js frontend is deployed on Vercel.

Production environment configuration:

```env
NEXT_PUBLIC_API_URL=https://formease-api.onrender.com/api/v1
```

### Backend – Render

The FastAPI backend is deployed on Render using the repository's `Dockerfile` and `render.yaml` configuration.

The backend deployment uses environment variables configured securely in Render.

### Database and Authentication – Supabase

Supabase provides authentication and database services.

Keep production credentials and privileged keys outside the Git repository.

---

## Security

FormEase follows several security practices:

- JWT signature verification.
- Token expiration validation.
- Issuer and audience validation where applicable.
- Protected authenticated API routes.
- Server-side management of privileged credentials.
- Environment-based configuration.
- CORS restrictions.

Never expose backend secrets or Supabase service-role credentials in frontend code.

---

## Future Improvements

Potential areas for continued development include:

- More advanced AI-generated learning experiences.
- Improved document visualization.
- Additional document formats.
- Enhanced diagram customization.
- More powerful semantic document retrieval.
- Improved processing performance.
- Expanded testing and monitoring.

---

## Contributing

Contributions, suggestions, and bug reports are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Implement your changes.
4. Run relevant tests.
5. Submit a pull request.

---

## License

A license has not yet been specified. All rights remain with the respective copyright holders until a license is added to the repository.

---

## Author

**Lakshya Srivastava**

B.Tech Computer Science Engineering – Artificial Intelligence & Data Science

- GitHub: [lakshya0102-dev](https://github.com/lakshya0102-dev)
- Project: [FormEase](https://github.com/lakshya0102-dev/FormEase)
- Live Application: [formease-virid.vercel.app](https://formease-virid.vercel.app)

---

<p align="center">
  <strong>FormEase – Making complex learning simpler.</strong>
</p>
