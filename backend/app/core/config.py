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

    # ---- Citizens: identity, aging and mortality ----

    # Prefix for the human-facing national ID, e.g. "AS-000042". Changing this
    # affects only citizens created afterwards — already-numbered citizens keep
    # the number they were issued, the way a real registry works.
    NATIONAL_ID_PREFIX: str = "AS"

    # The age at which a citizen may hold office or a parliament seat, and below
    # which they are excluded from the candidate picker.
    ADULT_AGE: int = 18

    # Set False to freeze aging and turn off natural death entirely. An admin can
    # still mark individuals dead by hand — this only governs whether the tick
    # engine does it on its own. Provided because a society that quietly loses
    # people is not always what you want while you are testing something else.
    NATURAL_DEATH_ENABLED: bool = True

    # How many ticks pass before a citizen's age increases by one year. A tick is
    # an hour and a day is 24 ticks (see dashboard_service._day_for_tick), so 720
    # means one year of age per 30 simulated days. Aging has to be far slower than
    # the clock or the population would die of old age within minutes.
    TICKS_PER_YEAR_OF_AGE: int = 720

    # Below this age nobody dies of old age. Above it the per-tick risk climbs
    # with each additional year — see simulation/mortality.py for the curve.
    NATURAL_DEATH_START_AGE: int = 70

    # Hard ceiling. A citizen who somehow reaches this age dies at the next tick
    # regardless of the roll, so the risk curve can stay gentle without allowing
    # a 300-year-old.
    MAX_CITIZEN_AGE: int = 105

    # A citizen whose health falls at or below this dies of ill health. Nothing in
    # the tick engine currently lowers health, so in practice this fires only when
    # an admin sets a critical value from the citizen editor — which is
    # deliberate. It is here so health means something the moment anything starts
    # draining it, rather than needing a second change later.
    CRITICAL_HEALTH: float = 5.0

    # ---- Government ----

    # How many parliament seats exist. Appointing to a full house is rejected
    # rather than silently growing it, so this is a real cap and not a hint.
    PARLIAMENT_SEATS: int = 30


settings = Settings()
