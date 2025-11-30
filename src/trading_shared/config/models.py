# src\trading_shared\config\models.py

from typing import Optional
from pydantic import BaseModel, Field, computed_field


class RedisSettings(BaseModel):
    url: str
    db: int
    password: Optional[str] = None


class PostgresSettings(BaseModel):
    user: str
    password: str
    host: str
    port: int
    db: str

    @computed_field
    @property
    def dsn(self) -> str:
        """Computes the DSN string for asyncpg."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

class ExchangeSettings(BaseModel):
    # API keys are now optional, allowing this model to be used
    # for both public and private clients.
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    # A default can be provided for public clients.
    rest_url: str = Field(default="https://www.deribit.com")


class TelegramSettings(BaseModel):
    bot_token: str
    chat_id: str
