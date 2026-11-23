"""
Health and AI status endpoints for FormEase.
Checks backend uptime and the configured AI provider/model readiness.
"""
from fastapi import APIRouter
from ...core.config import settings
from ...ai.ollama_client import ollama_client
from ...schemas.common import HealthResponse, AIStatusResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def check_backend_health():
    return HealthResponse(
        status="ok",
        project=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT
    )

@router.get("/ai/status", response_model=AIStatusResponse)
async def check_ai_status():
    status_data = await ollama_client.check_health()
    return AIStatusResponse(
        provider=ollama_client.provider,
        configured=status_data.get("configured", status_data.get("connected", False)),
        live_connection_verified=status_data.get("live_connection_verified", False),
        ollama_connected=status_data.get("connected", False),
        model_name=ollama_client.last_used_model if ollama_client.provider == "openrouter" else ollama_client.model,
        model_installed=status_data.get("model_installed", False),
        status_detail=status_data.get("detail", "")
    )
