"""
Configuration settings for NAAC Compliance Intelligence System
Handles environment variables and application settings
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List

class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
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
    
    # Ollama settings
    ollama_host: str = Field("http://localhost:11434", env="OLLAMA_HOST")
    ollama_model: str = Field("llama3.2:1b", env="OLLAMA_MODEL")
    ollama_timeout: int = Field(120, env="OLLAMA_TIMEOUT")
    
    # Embedding settings
    embedding_model: str = Field("all-MiniLM-L6-v2", env="EMBEDDING_MODEL")
    embedding_device: str = Field("cpu", env="EMBEDDING_DEVICE")  # cpu or cuda
    
    # Document processing settings
    data_directory: str = Field("./data", env="DATA_DIRECTORY")
    cache_directory: str = Field("./cache", env="CACHE_DIRECTORY")
    uploads_directory: str = Field("./uploads", env="UPLOADS_DIRECTORY")
    
    # NAAC website monitoring
    naac_base_url: str = Field("https://www.naac.gov.in", env="NAAC_BASE_URL")
    check_interval_hours: int = Field(24, env="CHECK_INTERVAL_HOURS")
    max_download_retries: int = Field(3, env="MAX_DOWNLOAD_RETRIES")
    
    # Chunking parameters
    chunk_size: int = Field(1000, env="CHUNK_SIZE")
    chunk_overlap: int = Field(200, env="CHUNK_OVERLAP")
    
    # Retrieval parameters
    max_retrieval_results: int = Field(10, env="MAX_RETRIEVAL_RESULTS")
    similarity_threshold: float = Field(0.3, env="SIMILARITY_THRESHOLD")
    
    # CORS settings
    cors_origins: List[str] = Field(["*"], env="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(True, env="CORS_ALLOW_CREDENTIALS")
    
    # Logging settings
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(None, env="LOG_FILE")
    
    # Security settings
    api_key: Optional[str] = Field(None, env="API_KEY")
    rate_limit_requests: int = Field(100, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(3600, env="RATE_LIMIT_WINDOW")  # seconds
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra fields in environment
    
    def get_data_path(self) -> Path:
        """Get data directory as Path object"""
        path = Path(self.data_directory)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_cache_path(self) -> Path:
        """Get cache directory as Path object"""
        path = Path(self.cache_directory)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_uploads_path(self) -> Path:
        """Get uploads directory as Path object"""
        path = Path(self.uploads_directory)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
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