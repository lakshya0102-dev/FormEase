"""
Pydantic schemas for FormEase API models, requests and responses.
"""
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

class ExplanationLevel(str, Enum):
    SIMPLE = "simple"
    BALANCED = "balanced"
    DETAILED = "detailed"

class SupportedLanguage(str, Enum):
    EN = "en"
    HI = "hi"

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

# Response schemas
class HealthResponse(BaseModel):
    status: str
    project: str
    environment: str

class AIStatusResponse(BaseModel):
    provider: str = "unknown"
    configured: bool = False
    live_connection_verified: bool = False
    ollama_connected: bool
    model_name: str
    model_installed: bool
    status_detail: str

class DocumentCreate(BaseModel):
    title: str
    file_type: str
    file_size_bytes: int = 0
    storage_path: Optional[str] = None
    pasted_text: Optional[str] = None

class DocumentResponse(BaseModel):
    id: str
    title: str
    file_name: str
    file_type: str
    file_size_bytes: int
    status: DocumentStatus
    page_count: int
    is_deleted: bool
    created_at: str

class AnalyzeRequest(BaseModel):
    language: SupportedLanguage = SupportedLanguage.EN
    depth: ExplanationLevel = ExplanationLevel.BALANCED
    components: Optional[List[str]] = Field(
        default=["summary", "sections", "process", "key_info", "definitions", "recommendations", "diagrams"]
    )

class ChatQueryRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None

class ChatMessageResponse(BaseModel):
    id: str
    sender: str
    content: str
    source_passage: Optional[str] = None
    source_page: Optional[int] = None
    similarity_score: Optional[float] = None
    is_weak_match: bool = False
    created_at: str

class RefinementRequest(BaseModel):
    instruction: str

class FeedbackRequest(BaseModel):
    is_positive: bool
    comment: Optional[str] = None
