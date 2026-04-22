from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Config
    app_name: str = "Telegram Signal Bot"
    app_version: str = "1.0.0"
    app_env: str = "dev"
    app_port: int = 8080  # Railway overrides via PORT env var in start.sh
    log_level: str = "INFO"

    # Security
    tradingview_shared_secret: str

    # Database
    database_url: str

    # Telegram API
    telegram_bot_token: str
    telegram_main_chat_id: str
    telegram_warn_chat_id: str
    telegram_admin_chat_id: str

    # Dashboard
    dashboard_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

settings = Settings()
