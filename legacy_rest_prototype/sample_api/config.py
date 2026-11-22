"""Configuration settings for the Sample Shopping API."""

import os
from pydantic import BaseModel


class Settings(BaseModel):
    """Application settings with environment variable fallbacks."""

    APP_NAME: str = "Sample Shopping API (Controlled Vulnerable Target)"
    APP_VERSION: str = "1.0.0"
    HOST: str = os.getenv("API_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("API_PORT", "8000"))
    # The reset endpoint is strictly for local testing workflows
    ENABLE_TEST_RESET: bool = os.getenv("API_ENABLE_TEST_RESET", "true").lower() in (
        "true",
        "1",
        "yes",
    )


settings = Settings()
