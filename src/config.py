"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://dealfinder:dealfinder_dev@localhost:5435/austin_deals"
    database_url_sync: str = "postgresql://dealfinder:dealfinder_dev@localhost:5435/austin_deals"

    # Reddit API
    reddit_user_agent: str = "AustinDealFinder/1.0 (housing search)"

    # OpenAI
    openai_api_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Scraping
    scrape_interval_hours: int = 3
    max_price: int = 2000

    # Target location: 600 Congress Avenue, Austin, TX 78701
    target_lat: float = 30.2672
    target_lon: float = -97.7431
    max_distance_miles: float = 2.0

    # Market reference
    avg_market_rent: float = 1600.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
