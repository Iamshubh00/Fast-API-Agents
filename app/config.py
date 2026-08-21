from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "cyber-multi-agent"

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4.1"          # swap for whatever tier you have access to
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 3

    # Infra
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cyberagents"
    redis_url: str = "redis://localhost:6379/0"

    # Safety
    require_human_approval_for_response: bool = True

    # Dev-only: bypasses real Keycloak token verification and injects a fake identity with all
    # roles, so you can hit the API locally before a real realm/client is set up.
    # NEVER set this true outside local development.
    dev_disable_auth: bool = False
    dev_fake_user_sub: str = "dev-local-user"

    class Config:
        env_file = ".env"


settings = Settings()