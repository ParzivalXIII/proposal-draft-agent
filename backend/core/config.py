from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openai_api_key: str
    openai_base_url: str | None = None
    llm_model_name: str | None = None
    llm_temperature: float = 0.2

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # DB (SQLite for walking skeleton, swap to postgresql+asyncpg://... for prod)
    database_url: str = "sqlite+aiosqlite:///./proposal_agent.db"

settings = Settings()