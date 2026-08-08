from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central app configuration. All values come from environment variables
    (or a .env file in development). Nothing here should be hardcoded
    elsewhere in the app — always import `settings` instead.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/ai_society_simulator"

    # JWT
    JWT_SECRET_KEY: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "AI Society Simulator"

    # Simulation (referenced by later phases; defined here now so config
    # stays centralized from day 1)
    MAX_CITIZENS_V0: int = 100
    TICK_INTERVAL_SECONDS: int = 10


settings = Settings()
