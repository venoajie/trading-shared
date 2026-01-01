# tests/trading_shared/config/test_models.py

import pytest
from pydantic import SecretStr, ValidationError

from trading_shared.config.models import PostgresSettings, RedisSettings


class TestPostgresSettings:
    """Tests the PostgresSettings Pydantic model."""

    def test_successful_initialization(self):
        # Arrange
        valid_data = {
            "user": "test_user",
            "password": "test_password",
            "host": "localhost",
            "port": 5432,
            "db": "test_db",
        }

        # Act
        settings = PostgresSettings(**valid_data)

        # Assert
        assert settings.user == "test_user"
        assert settings.password.get_secret_value() == "test_password"
        assert settings.host == "localhost"
        assert settings.port == 5432
        assert settings.db == "test_db"
        assert settings.pool_min_size == 1  # Check default
        assert settings.pool_max_size == 2  # Check default

    def test_dsn_computed_field_is_correct(self):
        # Arrange
        settings = PostgresSettings(
            user="test_user",
            password=SecretStr("test_password"),
            host="localhost",
            port=5432,
            db="test_db",
        )
        expected_dsn = "postgresql://test_user:test_password@localhost:5432/test_db"

        # Act
        dsn = settings.dsn

        # Assert
        assert dsn == expected_dsn

    def test_dsn_handles_special_characters_in_password(self):
        # Arrange
        password_with_special_chars = "p@ssw#rd$123"
        settings = PostgresSettings(
            user="test_user",
            password=SecretStr(password_with_special_chars),
            host="localhost",
            port=5432,
            db="test_db",
        )
        # urllib.parse.quote_plus should encode '@' to '%40', '#' to '%23', etc.
        expected_encoded_password = "p%40ssw%23rd%24123"
        expected_dsn = (
            f"postgresql://test_user:{expected_encoded_password}@localhost:5432/test_db"
        )

        # Act
        dsn = settings.dsn

        # Assert
        assert dsn == expected_dsn

    def test_missing_required_field_raises_validation_error(self):
        # Arrange
        invalid_data = {
            # "user" is missing
            "password": "test_password",
            "host": "localhost",
            "port": 5432,
            "db": "test_db",
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            PostgresSettings(**invalid_data)

        assert "user" in str(exc_info.value)


class TestRedisSettings:
    """Tests the RedisSettings Pydantic model."""

    def test_successful_initialization(self):
        # Arrange
        valid_data = {
            "url": "redis://localhost:6379",
            "db": 0,
            "password": "redis_password",
        }

        # Act
        settings = RedisSettings(**valid_data)

        # Assert
        assert settings.url == "redis://localhost:6379"
        assert settings.db == 0
        assert settings.password.get_secret_value() == "redis_password"
        assert settings.max_retries == 3  # Check default

    def test_password_is_optional(self):
        # Arrange
        data_without_password = {"url": "redis://localhost:6379", "db": 1}

        # Act
        settings = RedisSettings(**data_without_password)

        # Assert
        assert settings.password is None

    def test_invalid_data_type_raises_validation_error(self):
        # Arrange
        invalid_data = {
            "url": "redis://localhost:6379",
            "db": "not-an-integer",  # Invalid type
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            RedisSettings(**invalid_data)

        assert "db" in str(exc_info.value)
        assert "Input should be a valid integer" in str(exc_info.value)
