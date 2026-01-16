# tests/unit/shared/test_notification_models.py

import pytest
from pydantic import ValidationError

from trading_shared.notifications.models import SystemAlert, TradeNotification


class TestTradeNotification:
    """Tests for TradeNotification model."""

    def test_valid_trade_notification(self):
        # Arrange
        data = {
            "direction": "buy",
            "amount": 0.5,
            "instrument_name": "BTC-PERPETUAL",
            "price": 50000.0,
        }

        # Act
        notification = TradeNotification(**data)

        # Assert
        assert notification.direction == "buy"
        assert notification.amount == 0.5
        assert notification.instrument_name == "BTC-PERPETUAL"
        assert notification.price == 50000.0

    def test_missing_required_field_raises_error(self):
        # Arrange
        data = {
            "direction": "buy",
            "amount": 0.5,
            # Missing instrument_name and price
        }

        # Act & Assert
        with pytest.raises(ValidationError):
            TradeNotification(**data)

    def test_negative_amount(self):
        # Arrange
        data = {
            "direction": "sell",
            "amount": -0.5,
            "instrument_name": "ETH-PERPETUAL",
            "price": 3000.0,
        }

        # Act
        notification = TradeNotification(**data)

        # Assert
        assert notification.amount == -0.5

    def test_zero_price(self):
        # Arrange
        data = {
            "direction": "buy",
            "amount": 1.0,
            "instrument_name": "BTC-PERPETUAL",
            "price": 0.0,
        }

        # Act
        notification = TradeNotification(**data)

        # Assert
        assert notification.price == 0.0


class TestSystemAlert:
    """Tests for SystemAlert model."""

    def test_valid_system_alert_with_defaults(self):
        # Arrange
        data = {
            "component": "trading_engine",
            "event": "startup",
            "details": "System started successfully",
        }

        # Act
        alert = SystemAlert(**data)

        # Assert
        assert alert.component == "trading_engine"
        assert alert.event == "startup"
        assert alert.details == "System started successfully"
        assert alert.severity == "CRITICAL"

    def test_system_alert_with_info_severity(self):
        # Arrange
        data = {
            "component": "market_data",
            "event": "connection_established",
            "details": "Connected to exchange",
            "severity": "INFO",
        }

        # Act
        alert = SystemAlert(**data)

        # Assert
        assert alert.severity == "INFO"

    def test_system_alert_with_warning_severity(self):
        # Arrange
        data = {
            "component": "risk_manager",
            "event": "threshold_exceeded",
            "details": "Position size approaching limit",
            "severity": "WARNING",
        }

        # Act
        alert = SystemAlert(**data)

        # Assert
        assert alert.severity == "WARNING"

    def test_system_alert_with_critical_severity(self):
        # Arrange
        data = {
            "component": "order_executor",
            "event": "execution_failed",
            "details": "Failed to execute order",
            "severity": "CRITICAL",
        }

        # Act
        alert = SystemAlert(**data)

        # Assert
        assert alert.severity == "CRITICAL"

    def test_invalid_severity_raises_error(self):
        # Arrange
        data = {
            "component": "test",
            "event": "test_event",
            "details": "test details",
            "severity": "INVALID",
        }

        # Act & Assert
        with pytest.raises(ValidationError):
            SystemAlert(**data)

    def test_missing_required_fields_raises_error(self):
        # Arrange
        data = {
            "component": "test",
            # Missing event and details
        }

        # Act & Assert
        with pytest.raises(ValidationError):
            SystemAlert(**data)

    def test_empty_strings_allowed(self):
        # Arrange
        data = {
            "component": "",
            "event": "",
            "details": "",
        }

        # Act
        alert = SystemAlert(**data)

        # Assert
        assert alert.component == ""
        assert alert.event == ""
        assert alert.details == ""
