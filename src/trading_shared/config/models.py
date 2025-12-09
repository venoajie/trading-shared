# src\trading_shared\config\models.py

# --- Built Ins  ---
from typing import Optional

# --- Installed  ---
from pydantic import BaseModel, Field, computed_field, SecretStr
from urllib.parse import quote_plus

class RedisSettings(BaseModel):
    url: str
    db: int
    password: Optional[SecretStr] = None
    write_concurrency_limit: int = Field(
        default=4,
        description="Concurrency limit for bulk write operations to Redis."
    )


class PostgresSettings(BaseModel):
    user: str
    password: SecretStr
    host: str
    port: int
    db: str

    @computed_field
    @property
    def dsn(self) -> str:
        """Computes the DSN string for asyncpg."""       
        encoded_user = quote_plus(self.user)
        encoded_password = quote_plus(self.password.get_secret_value())
        return f"postgresql://{encoded_user}:{encoded_password}@{self.host}:{self.port}/{self.db}"
        #return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class ExchangeSettings(BaseModel):
    # API keys are now optional, allowing this model to be used
    # for both public and private clients.
    client_id: Optional[str] = None
    client_secret: Optional[SecretStr] = None

    # WebSocket and REST URLs
    ws_url: Optional[str] = None
    rest_url: str = Field(default="https://www.deribit.com")


class TelegramSettings(BaseModel):
    bot_token: SecretStr
    chat_id: str
