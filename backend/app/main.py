"""
FastAPI application entrypoint for FormEase.
Configures CORS, middleware, API v1 routes, and exception handling.
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.core.config import settings

# Router imports
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.documents import router as documents_router
from backend.app.api.v1.analysis import router as analysis_router
from backend.app.api.v1.chat import router as chat_router
from backend.app.api.v1.annotations import router as annotations_router
from backend.app.api.v1.export import router as export_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FormEase — AI Document Simplifier Platform Backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            # Never reflect exception text to an API caller: third-party errors
            # can contain request details, identifiers, or credential material.
            "message": "An unexpected error occurred."
        }
    )

# Include API v1 Routers
api_v1_prefix = settings.API_V1_STR
app.include_router(health_router, prefix=api_v1_prefix, tags=["Health & AI Status"])
app.include_router(documents_router, prefix=f"{api_v1_prefix}/documents", tags=["Documents"])
app.include_router(analysis_router, prefix=api_v1_prefix, tags=["Analysis & Refinement"])
app.include_router(chat_router, prefix=api_v1_prefix, tags=["Document Chatbot"])
app.include_router(annotations_router, prefix=api_v1_prefix, tags=["Annotations"])
app.include_router(export_router, prefix=api_v1_prefix, tags=["Export"])

@app.get("/")
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "tagline": "Understand Documents. Simplify Complexity. Step by Step.",
        "status": "online",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=settings.DEBUG)
