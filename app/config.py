# app/config.py
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import Field
from typing import List
import os


class Settings(BaseSettings):
    PORT: int = 8000
    SSL_ENABLED: bool = False  # 后端不需要SSL，nginx处理
    HOST: str = "0.0.0.0"
    
    # Application
    APP_NAME: str = "COA Document Processor API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Database
    DB_HOST: str = "bg-beone-db-d-1.cijvcub5gps8.us-west-2.rds.amazonaws.com"
    DB_PORT: int = 5432
    DB_USER: str = "aimta_dev_owner"
    DB_PASSWORD: str = "SdBJ92Mr!TOXFJVOBcx"
    DB_NAME: str = "aimta"
    DB_SCHEMA: str = "coa_processor"
    
    # Construct database URL
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # File Upload
    UPLOAD_DIR: str = "/app/uploads"
    PDF_DIRECTORY: str = "/app/uploads/pdfs"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_FILE_TYPES: list[str] = [".pdf"]

    # Azure OpenAI Configuration
    AZURE_OPENAI_API_KEY: Optional[str] = "83a807cd6f5f4a5fb4a252e2f412a669"
    AZURE_OPENAI_BASE_URL: str = "https://dsdi-openai-dev.openai.azure.com/"
    AZURE_OPENAI_API_VERSION: str = "2025-01-01-preview"
    AZURE_OPENAI_DEPLOYMENT_NAME: str = "dsdi-gpt-4o"

    # 判断使用哪种OpenAI服务
    @property
    def USE_AZURE_OPENAI(self) -> bool:
        return bool(self.AZURE_OPENAI_API_KEY)        
    
    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4-vision-preview"
    OPENAI_MAX_TOKENS: int = 4096
    
    # Veeva Vault Configuration
    VEEVA_VAULT_URL: str = "https://sb-beigene-rim.veevavault.com"
    VEEVA_USERNAME: str = "zhijun.li@sb-beigene.com"
    VEEVA_PASSWORD: str = "Aimta2025123!"  # Will be set from environment variable
    VEEVA_API_VERSION: str = "v25.1"
    VEEVA_API_TIMEOUT: int = 30  # seconds
    VEEVA_MAX_CONCURRENT_DOWNLOADS: int = 3  # Maximum concurrent downloads
    VEEVA_DOWNLOAD_CHUNK_SIZE: int = 8192  # 8KB chunks for streaming
    VEEVA_ENABLED: bool = True  # Enable/disable Veeva integration
    
    # Processing Configuration
    PROCESSING_MODE: str = "hybrid"  # "local", "veeva", or "hybrid"
    MAX_MEMORY_PDF_SIZE: int = 50 * 1024 * 1024  # 50MB - max size for in-memory processing
    ENABLE_CACHE: bool = True  # Enable caching for Veeva documents
    CACHE_TTL: int = 3600  # Cache TTL in seconds (1 hour)
    
    # Security
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Redis (optional, for caching)
    REDIS_URL: Optional[str] = None

    @field_validator("PORT", mode="before")
    @classmethod
    def parse_port(cls, v):
        return int(v)

    @field_validator("SSL_ENABLED", mode="before")
    @classmethod
    def parse_ssl_enabled(cls, v):
        if isinstance(v, bool):
            return v
        return v.lower() in ("true", "1", "yes")
    
    @field_validator("VEEVA_ENABLED", mode="before")
    @classmethod
    def parse_veeva_enabled(cls, v):
        if isinstance(v, bool):
            return v
        return v.lower() in ("true", "1", "yes")
    
    @field_validator("PROCESSING_MODE", mode="before")
    @classmethod
    def validate_processing_mode(cls, v):
        valid_modes = ["local", "veeva", "hybrid"]
        if v not in valid_modes:
            raise ValueError(f"PROCESSING_MODE must be one of {valid_modes}")
        return v
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="allow",
    )


# Create settings instance
settings = Settings()

# Create upload directory if it doesn't exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.PDF_DIRECTORY, exist_ok=True)