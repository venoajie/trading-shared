# src\trading_shared\config\models.py

# --- Built Ins  ---
from urllib.parse import quote_plus

# --- Installed  ---
from pydantic import BaseModel, Field, SecretStr, computed_field


class RedisSettings(BaseModel):
    url: str
    db: int
    password: SecretStr | None = None
    write_concurrency_limit: int = Field(default=4, description="Concurrency limit for bulk write operations to Redis.")
    socket_connect_timeout: int = Field(
        default=2,
        description="Timeout in seconds for establishing a new Redis connection.",
    )
    max_connections: int = Field(
        default=30,
        description="Maximum number of connections in the standard command pool.",
    )
    pubsub_max_connections: int = Field(
        default=50,
        description="Maximum number of connections in the PubSub pool. Must exceed Total_Instruments / 200.",
    )
    max_retries: int = Field(default=3, description="Maximum number of retries for a resilient command.")
    initial_retry_delay_s: float = Field(default=0.5, description="Initial delay in seconds for exponential backoff.")


class PostgresSettings(BaseModel):
    user: str
    password: SecretStr
    host: str
    port: int
    db: str
    pool_min_size: int = Field(default=1, description="Minimum number of connections in the PostgreSQL pool.")
    pool_max_size: int = Field(default=2, description="Maximum number of connections in the PostgreSQL pool.")
    command_timeout: int = Field(default=30, description="Default timeout in seconds for PostgreSQL commands.")
    max_retries: int = Field(default=3, description="Maximum number of retries for a resilient command.")
    initial_retry_delay_s: float = Field(default=0.5, description="Initial delay in seconds for exponential backoff.")

    @computed_field
    @property
    def dsn(self) -> str:
        """Computes the DSN string for asyncpg."""
        encoded_user = quote_plus(self.user)
        encoded_password = quote_plus(self.password.get_secret_value())
        return f"postgresql://{encoded_user}:{encoded_password}@{self.host}:{self.port}/{self.db}"
        # return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class ExchangeSettings(BaseModel):
    # API keys are now optional, allowing this model to be used
    # for both public and private clients.
    client_id: str | None = None
    client_secret: SecretStr | None = None

    # WebSocket and REST URLs
    ws_url: str | None = None
    rest_url: str = Field(default="https://www.deribit.com")


class TelegramSettings(BaseModel):
    bot_token: SecretStr
    chat_id: str
