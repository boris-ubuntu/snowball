import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    APP_NAME: str = "Snowball - Портфель ценных бумаг"
    APP_VERSION: str = "1.0.0"
    
    # Database - can use DATABASE_URL directly (from Neon) or individual params
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # Individual database params (used if DATABASE_URL is not set)
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "snowball")
    DB_USER: str = os.getenv("DB_USER", "snowball")
    DB_PASS: str = os.getenv("DB_PASS", "snowball")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "snowball-investment-secret-key-2026")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "43200"))
    
    @property
    def DB_URL(self) -> str:
        """Get database URL: DATABASE_URL env takes priority, fall back to individual params"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def DB_URL_ASYNC(self) -> str:
        """Get async database URL"""
        if self.DATABASE_URL:
            # Replace postgresql:// with postgresql+asyncpg://
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()