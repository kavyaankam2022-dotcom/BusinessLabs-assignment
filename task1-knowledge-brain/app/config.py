from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_path: str = os.getenv("KB_DATABASE_PATH", "data/knowledge.db")
    sitemap_url: str = os.getenv(
        "KB_SITEMAP_URL", "https://support.brilliantdirectories.com/support/sitemap.xml"
    )
    embedding_model: str = os.getenv("KB_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    claude_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    answer_timeout_seconds: float = float(os.getenv("KB_ANSWER_TIMEOUT_SECONDS", "20"))
    ingestion_job_timeout_seconds: float = float(os.getenv("KB_INGESTION_TIMEOUT_SECONDS", "300"))
    daily_ingestion_hour: int = int(os.getenv("KB_DAILY_INGESTION_HOUR_UTC", "2"))
    daily_ingestion_minute: int = int(os.getenv("KB_DAILY_INGESTION_MINUTE_UTC", "15"))
    max_concurrency: int = int(os.getenv("KB_MAX_CONCURRENCY", "3"))
    request_delay_seconds: float = float(os.getenv("KB_REQUEST_DELAY_SECONDS", "0.3"))
    image_analysis_enabled: bool = os.getenv("KB_IMAGE_ANALYSIS", "false").lower() == "true"


settings = Settings()