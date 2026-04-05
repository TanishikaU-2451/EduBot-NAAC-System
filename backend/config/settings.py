"""
Configuration settings for NAAC Compliance Intelligence System
Handles environment variables and application settings
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, List

class Settings(BaseSettings):
    """Application settings with environment variable support"""

    @field_validator("debug", mode="before")
    @classmethod
    def _coerce_debug_flag(cls, value):
        """Accept common environment-style debug values without crashing settings load."""
        if isinstance(value, bool) or value is None:
            return value

        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "production", "prod"}:
            return False
        return value
    
    # Application settings
    app_name: str = Field("NAAC Compliance Intelligence System", env="APP_NAME")
    app_version: str = Field("1.0.0", env="APP_VERSION")
    debug: bool = Field(False, env="DEBUG")
    
    # Server settings
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8000, env="PORT")
    reload: bool = Field(False, env="RELOAD")
    
    # Database settings
    chroma_db_path: str = Field("./chroma_db", env="CHROMA_DB_PATH")
    job_store_url: str = Field("sqlite:///jobs.sqlite", env="JOB_STORE_URL")
    vector_backend: str = Field("supabase", env="VECTOR_BACKEND")
    supabase_db_url: Optional[str] = Field(None, env="SUPABASE_DB_URL")
    supabase_table: str = Field("chunks", env="SUPABASE_TABLE")
    embedding_dim: int = Field(384, env="EMBEDDING_DIM")
    
    # Groq API settings
    groq_model: str = Field("llama-3.3-70b-versatile", env="GROQ_MODEL")
    groq_api_key: Optional[str] = Field(None, env="GROQ_API_KEY")
    groq_timeout: int = Field(120, env="GROQ_TIMEOUT")
    
    # Embedding settings
    embedding_model: str = Field("all-MiniLM-L6-v2", env="EMBEDDING_MODEL")
    embedding_device: str = Field("cpu", env="EMBEDDING_DEVICE")  # cpu or cuda
    embedding_batch_size: int = Field(128, env="EMBEDDING_BATCH_SIZE")
    vector_insert_batch_size: int = Field(1000, env="VECTOR_INSERT_BATCH_SIZE")
    
    # Document processing settings
    pdf_extraction_strategy: str = Field("auto", env="PDF_EXTRACTION_STRATEGY")
    pdf_extract_tables: bool = Field(False, env="PDF_EXTRACT_TABLES")
    large_document_page_threshold: int = Field(120, env="LARGE_DOCUMENT_PAGE_THRESHOLD")
    
    # NAAC website monitoring
    naac_base_url: str = Field("https://www.naac.gov.in", env="NAAC_BASE_URL")
    check_interval_hours: int = Field(24, env="CHECK_INTERVAL_HOURS")
    max_download_retries: int = Field(3, env="MAX_DOWNLOAD_RETRIES")
    
    # Chunking parameters
    chunk_size: int = Field(1000, env="CHUNK_SIZE")
    chunk_overlap: int = Field(200, env="CHUNK_OVERLAP")
    large_document_chunk_size: int = Field(1800, env="LARGE_DOCUMENT_CHUNK_SIZE")
    large_document_chunk_overlap: int = Field(120, env="LARGE_DOCUMENT_CHUNK_OVERLAP")
    min_chunk_length: int = Field(180, env="MIN_CHUNK_LENGTH")
    
    # Retrieval parameters
    max_retrieval_results: int = Field(10, env="MAX_RETRIEVAL_RESULTS")
    similarity_threshold: float = Field(0.3, env="SIMILARITY_THRESHOLD")
    retrieval_mode: str = Field("hybrid", env="RETRIEVAL_MODE")
    retrieval_dense_weight: float = Field(0.65, env="RETRIEVAL_DENSE_WEIGHT")
    retrieval_lexical_weight: float = Field(0.35, env="RETRIEVAL_LEXICAL_WEIGHT")
    retrieval_candidate_multiplier: int = Field(4, env="RETRIEVAL_CANDIDATE_MULTIPLIER")

    # Reranker settings (cross-encoder, applied after hybrid retrieval)
    reranker_enabled: bool = Field(True, env="RERANKER_ENABLED")
    reranker_model: str = Field(
        "cross-encoder/ms-marco-MiniLM-L-6-v2", env="RERANKER_MODEL"
    )
    reranker_device: str = Field("cpu", env="RERANKER_DEVICE")

    # CORS settings
    cors_origins: List[str] = Field(["*"], env="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(True, env="CORS_ALLOW_CREDENTIALS")
    
    # Logging settings
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(None, env="LOG_FILE")
    pipeline_debug_enabled: bool = Field(False, env="PIPELINE_DEBUG_ENABLED")
    pipeline_debug_dir: str = Field("./debug_logs", env="PIPELINE_DEBUG_DIR")
    auto_ingest_enabled: bool = Field(False, env="AUTO_INGEST_ENABLED")
    persist_ingestion_log: bool = Field(False, env="PERSIST_INGESTION_LOG")
    
    # Security settings
    api_key: Optional[str] = Field(None, env="API_KEY")
    rate_limit_requests: int = Field(100, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(3600, env="RATE_LIMIT_WINDOW")  # seconds

    # Memory layer settings
    memory_enabled: bool = Field(True, env="MEMORY_ENABLED")
    memory_short_ttl_days: int = Field(7, env="MEMORY_SHORT_TTL_DAYS")
    memory_long_ttl_days: int = Field(365, env="MEMORY_LONG_TTL_DAYS")
    memory_short_limit: int = Field(20, env="MEMORY_SHORT_LIMIT")
    memory_long_top_k: int = Field(6, env="MEMORY_LONG_TOP_K")
    
    class Config:
        env_file = (".env", "../.env")
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra fields in environment
    
    def get_chroma_path(self) -> Path:
        """Get ChromaDB directory as Path object"""
        path = Path(self.chroma_db_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

# Global settings instance
settings = Settings()

# Environment-specific configurations
class DevelopmentSettings(Settings):
    """Development environment settings"""
    debug: bool = True
    reload: bool = True
    log_level: str = "DEBUG"
    
    class Config:
        extra = "ignore"

class ProductionSettings(Settings):
    """Production environment settings"""
    debug: bool = False
    reload: bool = False
    log_level: str = "WARNING"
    cors_origins: List[str] = []  # Restrict CORS in production
    
    class Config:
        extra = "ignore"

def get_settings() -> Settings:
    """Get settings based on environment"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "production":
        return ProductionSettings()
    elif env == "development":
        return DevelopmentSettings()
    else:
        return Settings()
