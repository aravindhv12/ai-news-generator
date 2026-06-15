from pydantic_settings import BaseSettings
from typing import Optional
import os

env_file_path = ".env"
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_env = os.path.join(backend_dir, ".env")
if not os.path.exists(env_file_path) and os.path.exists(backend_env):
    env_file_path = backend_env

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Tech News Platform"
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_news"
    
    # AI - Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"
    
    # Instagram / Facebook Graph API
    INSTAGRAM_ACCESS_TOKEN: Optional[str] = None
    INSTAGRAM_BUSINESS_ID: Optional[str] = None
    
    # Public Host (for media URLs in local dev, e.g. ngrok)
    PUBLIC_HOST: str = "http://localhost:8000"
    
    # Security
    ADMIN_USER: str = "admin"
    ADMIN_PASSWORD: str = "change_me" # Use get_password_hash during setup
    JWT_SECRET: str = "super-secret-key"
    
    class Config:
        env_file = env_file_path

settings = Settings()

# Safety validation for production deployments (e.g. Vercel)
if os.getenv("VERCEL") and "localhost" in settings.DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is missing or pointing to localhost on Vercel. "
        "Please configure DATABASE_URL in Vercel's Environment Variables (Project Settings -> Environment Variables) "
        "with your Supabase connection string (ensuring ?sslmode=require is appended) and redeploy."
    )

