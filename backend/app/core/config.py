"""
Application configuration for FormEase backend.
Reads from environment variables and provides typed settings.
Supports both pydantic_settings and standard library fallback.
"""
import os
from typing import List

try:
    from pydantic_settings import BaseSettings
    class Settings(BaseSettings):
        PROJECT_NAME: str = "FormEase"
        ENVIRONMENT: str = "development"
        DEBUG: bool = True
        API_V1_STR: str = "/api/v1"
        BACKEND_HOST: str = "0.0.0.0"
        BACKEND_PORT: int = 8000
        FRONTEND_URL: str = "http://localhost:3000"
        CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

        # Supabase Configuration
        SUPABASE_URL: str = "https://placeholder-project.supabase.co"
        SUPABASE_ANON_KEY: str = "placeholder-anon-key"
        SUPABASE_SERVICE_ROLE_KEY: str = "placeholder-service-role-key"
        SUPABASE_JWT_SECRET: str = "placeholder-jwt-secret"
        SUPABASE_STORAGE_BUCKET: str = "documents"

        # Central AI provider. OpenRouter is the default; Ollama remains selectable locally.
        AI_PROVIDER: str = "openrouter"
        OPENROUTER_API_BASE_URL: str = "https://openrouter.ai/api/v1"
        OPENROUTER_API_KEY: str = ""
        OPENROUTER_MODEL: str = ""
        OPENROUTER_FREE_FALLBACK_MODELS: str = "baidu/ernie-5.5-flash-preview:free"
        OPENROUTER_TIMEOUT_SECONDS: int = 90
        AI_REQUEST_INTERVAL_SECONDS: float = 3.5
        AI_MAX_RETRIES: int = 2
        AI_QUEUE_CONCURRENCY: int = 1
        AI_ANALYSIS_BATCH_CHARS: int = 10000
        OCR_ENABLED: bool = True
        OCR_LANGUAGE: str = "eng+hin"
        OCR_MIN_TEXT_CHARS: int = 40
        AI_USER_CHAT_REQUESTS_PER_MINUTE: int = 10

        # Ollama Local AI Inference
        OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
        OLLAMA_MODEL: str = "llama3.2:latest"
        OLLAMA_TIMEOUT_SECONDS: int = 120
        OLLAMA_MAX_RETRIES: int = 3

        # Document Extraction & Retrieval
        MAX_UPLOAD_SIZE_MB: int = 100
        SUPPORTED_FILE_EXTENSIONS: str = "pdf,docx,txt"
        DEFAULT_CHUNK_SIZE: int = 700
        DEFAULT_CHUNK_OVERLAP: int = 90
        TFIDF_MAX_FEATURES: int = 5000
        TFIDF_RELEVANCE_THRESHOLD: float = 0.18

        # Background Job Queue
        MAX_CONCURRENT_JOBS: int = 2
        JOB_POLL_INTERVAL_SECONDS: int = 2
        JOB_MAX_RETRIES: int = 3
        TRASH_RETENTION_DAYS: int = 30

        @property
        def cors_origin_list(self) -> List[str]:
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

        @property
        def supported_extensions_list(self) -> List[str]:
            return [ext.strip().lower() for ext in self.SUPPORTED_FILE_EXTENSIONS.split(",") if ext.strip()]

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"

    settings = Settings()

except ImportError:
    # Standard library fallback when pydantic_settings is not installed in local environment
    class Settings:
        def __init__(self):
            self.PROJECT_NAME: str = os.getenv("PROJECT_NAME", "FormEase")
            self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
            self.DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
            self.API_V1_STR: str = os.getenv("API_V1_STR", "/api/v1")
            self.BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
            self.BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
            self.FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
            self.CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

            self.SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://placeholder-project.supabase.co")
            self.SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "placeholder-anon-key")
            self.SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "placeholder-service-role-key")
            self.SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "placeholder-jwt-secret")
            self.SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "documents")

            self.AI_PROVIDER: str = os.getenv("AI_PROVIDER", "openrouter")
            self.OPENROUTER_API_BASE_URL: str = os.getenv("OPENROUTER_API_BASE_URL", "https://openrouter.ai/api/v1")
            self.OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
            self.OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "")
            self.OPENROUTER_FREE_FALLBACK_MODELS: str = os.getenv("OPENROUTER_FREE_FALLBACK_MODELS", "baidu/ernie-5.5-flash-preview:free")
            self.OPENROUTER_TIMEOUT_SECONDS: int = int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "90"))
            self.AI_REQUEST_INTERVAL_SECONDS: float = float(os.getenv("AI_REQUEST_INTERVAL_SECONDS", "3.5"))
            self.AI_MAX_RETRIES: int = int(os.getenv("AI_MAX_RETRIES", "2"))
            self.AI_QUEUE_CONCURRENCY: int = int(os.getenv("AI_QUEUE_CONCURRENCY", "1"))
            self.AI_ANALYSIS_BATCH_CHARS: int = int(os.getenv("AI_ANALYSIS_BATCH_CHARS", "10000"))
            self.OCR_ENABLED: bool = os.getenv("OCR_ENABLED", "true").lower() == "true"
            self.OCR_LANGUAGE: str = os.getenv("OCR_LANGUAGE", "eng+hin")
            self.OCR_MIN_TEXT_CHARS: int = int(os.getenv("OCR_MIN_TEXT_CHARS", "40"))
            self.AI_USER_CHAT_REQUESTS_PER_MINUTE: int = int(os.getenv("AI_USER_CHAT_REQUESTS_PER_MINUTE", "10"))

            self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
            self.OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
            self.OLLAMA_TIMEOUT_SECONDS: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
            self.OLLAMA_MAX_RETRIES: int = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))

            self.MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
            self.SUPPORTED_FILE_EXTENSIONS: str = os.getenv("SUPPORTED_FILE_EXTENSIONS", "pdf,docx,txt")
            self.DEFAULT_CHUNK_SIZE: int = int(os.getenv("DEFAULT_CHUNK_SIZE", "700"))
            self.DEFAULT_CHUNK_OVERLAP: int = int(os.getenv("DEFAULT_CHUNK_OVERLAP", "90"))
            self.TFIDF_MAX_FEATURES: int = int(os.getenv("TFIDF_MAX_FEATURES", "5000"))
            self.TFIDF_RELEVANCE_THRESHOLD: float = float(os.getenv("TFIDF_RELEVANCE_THRESHOLD", "0.18"))

            self.MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
            self.JOB_POLL_INTERVAL_SECONDS: int = int(os.getenv("JOB_POLL_INTERVAL_SECONDS", "2"))
            self.JOB_MAX_RETRIES: int = int(os.getenv("JOB_MAX_RETRIES", "3"))
            self.TRASH_RETENTION_DAYS: int = int(os.getenv("TRASH_RETENTION_DAYS", "30"))

        @property
        def cors_origin_list(self) -> List[str]:
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

        @property
        def supported_extensions_list(self) -> List[str]:
            return [ext.strip().lower() for ext in self.SUPPORTED_FILE_EXTENSIONS.split(",") if ext.strip()]

    settings = Settings()

