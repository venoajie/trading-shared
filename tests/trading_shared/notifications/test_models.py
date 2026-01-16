# tests/trading_shared/notifications/test_models.py

import pytest
from pydantic import ValidationError

from trading_shared.notifications.models import SystemAlert, TradeNotification


class TestTradeNotification:
    """Tests for TradeNotification model."""

    def test_valid_trade_notification(self):
        data = {
            "direction": "buy",
            "amount": 0.5,
            "instrument_name": "BTC-PERPETUAL",
            "price": 50000.0,
        }
        notification = TradeNotification(**data)
        assert notification.direction == "buy"
        assert notification.amount == 0.5
        assert notification.instrument_name == "BTC-PERPETUAL"
        assert notification.price == 50000.0

    def test_missing_required_field_raises_error(self):
        data = {
            "direction": "buy",
            "amount": 0.5,
        }
        with pytest.raises(ValidationError):
            TradeNotification(**data)

    def test_negative_amount(self):
        data = {
            "direction": "sell",
            "amount": -0.5,
            "instrument_name": "ETH-PERPETUAL",
            "price": 3000.0,
        }
        notification = TradeNotification(**data)
        assert notification.amount == -0.5

    def test_zero_price(self):
        data = {
            "direction": "buy",
            "amount": 1.0,
            "instrument_name": "BTC-PERPETUAL",
            "price": 0.0,
        }
        notification = TradeNotification(**data)
        assert notification.price == 0.0


class TestSystemAlert:
    """Tests for SystemAlert model."""

    def test_valid_system_alert_with_defaults(self):
        data = {
            "component": "trading_engine",
            "event": "startup",
            "details": "System started successfully",
        }
        alert = SystemAlert(**data)
        assert alert.component == "trading_engine"
        assert alert.event == "startup"
        assert alert.details == "System started successfully"
        assert alert.severity == "CRITICAL"

    def test_system_alert_with_info_severity(self):
        data = {
            "component": "market_data",
            "event": "connection_established",
            "details": "Connected to exchange",
            "severity": "INFO",
        }
        alert = SystemAlert(**data)
        assert alert.severity == "INFO"

    def test_system_alert_with_warning_severity(self):
        data = {
            "component": "risk_manager",
            "event": "threshold_exceeded",
            "details": "Position size approaching limit",
            "severity": "WARNING",
        }
        alert = SystemAlert(**data)
        assert alert.severity == "WARNING"

    def test_system_alert_with_critical_severity(self):
        data = {
            "component": "order_executor",
            "event": "execution_failed",
            "details": "Failed to execute order",
            "severity": "CRITICAL",
        }
        alert = SystemAlert(**data)
        assert alert.severity == "CRITICAL"

    def test_invalid_severity_raises_error(self):
        data = {
            "component": "test",
            "event": "test_event",
            "details": "test details",
            "severity": "INVALID",
        }
        with pytest.raises(ValidationError):
            SystemAlert(**data)

    def test_missing_required_fields_raises_error(self):
        data = {
            "component": "test",
        }
        with pytest.raises(ValidationError):
            SystemAlert(**data)

    def test_empty_strings_allowed(self):
        data = {
            "component": "",
            "event": "",
            "details": "",
        }
        alert = SystemAlert(**data)
        assert alert.component == ""
        assert alert.event == ""
        assert alert.details == ""
