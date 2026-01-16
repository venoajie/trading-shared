# tests/trading_shared/risk/test_pme_calculator.py

from unittest.mock import AsyncMock, MagicMock

import pytest

from trading_shared.risk.pme_calculator import PortfolioMarginCalculator


class TestPortfolioMarginCalculator:
    """Tests for PortfolioMarginCalculator class."""

    @pytest.fixture
    def mock_api_client(self):
        mock_client = MagicMock()
        mock_client.simulate_pme = AsyncMock()
        return mock_client

    @pytest.fixture
    def calculator(self, mock_api_client):
        return PortfolioMarginCalculator(mock_api_client)

    @pytest.mark.asyncio
    async def test_calculate_margins_with_empty_positions(self, calculator, mock_api_client):
        account_state = MagicMock()
        account_state.tracked_positions = {}
        result = await calculator.calculate_margins(account_state)
        assert result.initial_margin == 0.0
        assert result.maintenance_margin == 0.0
        assert result.is_valid is True
        mock_api_client.simulate_pme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calculate_margins_with_tracked_positions(self, calculator, mock_api_client):
        account_state = MagicMock()
        account_state.tracked_positions = {
            "pos1": {
                "opening_trades": [{"instrument_name": "BTC-PERPETUAL"}],
                "net_amount": 1.5,
            },
            "pos2": {
                "opening_trades": [{"instrument_name": "ETH-PERPETUAL"}],
                "net_amount": 10.0,
            },
        }
        mock_api_client.simulate_pme.return_value = {
            "success": True,
            "data": {
                "margins": {
                    "cross": {
                        "initial_margin": 5000.0,
                        "maintenance_margin": 2500.0,
                    }
                }
            },
        }
        result = await calculator.calculate_margins(account_state)
        assert result.initial_margin == 5000.0
        assert result.maintenance_margin == 2500.0
        assert result.is_valid is True
        mock_api_client.simulate_pme.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_calculate_margins_with_hypothetical_positions(self, calculator, mock_api_client):
        account_state = MagicMock()
        account_state.tracked_positions = {}
        hypothetical_positions = {
            "BTC-PERPETUAL": 2.0,
            "ETH-PERPETUAL": 15.0,
        }
        mock_api_client.simulate_pme.return_value = {
            "success": True,
            "data": {
                "margins": {
                    "cross": {
                        "initial_margin": 8000.0,
                        "maintenance_margin": 4000.0,
                    }
                }
            },
        }
        result = await calculator.calculate_margins(account_state, hypothetical_positions)
        assert result.initial_margin == 8000.0
        assert result.maintenance_margin == 4000.0
        mock_api_client.simulate_pme.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_calculate_margins_combines_tracked_and_hypothetical(self, calculator, mock_api_client):
        account_state = MagicMock()
        account_state.tracked_positions = {
            "pos1": {
                "opening_trades": [{"instrument_name": "BTC-PERPETUAL"}],
                "net_amount": 1.0,
            },
        }
        hypothetical_positions = {
            "BTC-PERPETUAL": 1.0,
            "ETH-PERPETUAL": 5.0,
        }
        mock_api_client.simulate_pme.return_value = {
            "success": True,
            "data": {
                "margins": {
                    "cross": {
                        "initial_margin": 10000.0,
                        "maintenance_margin": 5000.0,
                    }
                }
            },
        }
        result = await calculator.calculate_margins(account_state, hypothetical_positions)
        call_args = mock_api_client.simulate_pme.call_args[0][0]
        assert call_args["BTC-PERPETUAL"] == 2.0
        assert call_args["ETH-PERPETUAL"] == 5.0

    @pytest.mark.asyncio
    async def test_calculate_margins_handles_api_failure(self, calculator, mock_api_client):
        account_state = MagicMock()
        account_state.tracked_positions = {
            "pos1": {
                "opening_trades": [{"instrument_name": "BTC-PERPETUAL"}],
                "net_amount": 1.0,
            },
        }
        mock_api_client.simulate_pme.return_value = {
            "success": False,
            "error": "API error",
        }
        result = await calculator.calculate_margins(account_state)
        assert result.initial_margin == 0.0
        assert result.maintenance_margin == 0.0
        assert result.is_valid is False
        assert "API error" in result.error_message

    @pytest.mark.asyncio
    async def test_calculate_margins_handles_malformed_response(self, calculator, mock_api_client):
        account_state = MagicMock()
        account_state.tracked_positions = {
            "pos1": {
                "opening_trades": [{"instrument_name": "BTC-PERPETUAL"}],
                "net_amount": 1.0,
            },
        }
        mock_api_client.simulate_pme.return_value = {
            "success": True,
            "data": {},
        }
        result = await calculator.calculate_margins(account_state)
        assert result.initial_margin == 0.0
        assert result.maintenance_margin == 0.0
        assert result.is_valid is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_calculate_margins_handles_missing_opening_trades(self, calculator, mock_api_client):
        account_state = MagicMock()
        account_state.tracked_positions = {
            "pos1": {
                "opening_trades": [],
                "net_amount": 1.0,
            },
        }
        result = await calculator.calculate_margins(account_state)
        assert result.initial_margin == 0.0
        assert result.maintenance_margin == 0.0
        assert result.is_valid is True
        mock_api_client.simulate_pme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_calculate_margins_handles_account_state_without_tracked_positions(self, calculator, mock_api_client):
        account_state = MagicMock(spec=[])
        result = await calculator.calculate_margins(account_state)
        assert result.initial_margin == 0.0
        assert result.maintenance_margin == 0.0
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_calculate_margins_aggregates_same_instrument(self, calculator, mock_api_client):
        account_state = MagicMock()
        account_state.tracked_positions = {
            "pos1": {
                "opening_trades": [{"instrument_name": "BTC-PERPETUAL"}],
                "net_amount": 1.0,
            },
            "pos2": {
                "opening_trades": [{"instrument_name": "BTC-PERPETUAL"}],
                "net_amount": 0.5,
            },
        }
        mock_api_client.simulate_pme.return_value = {
            "success": True,
            "data": {
                "margins": {
                    "cross": {
                        "initial_margin": 3000.0,
                        "maintenance_margin": 1500.0,
                    }
                }
            },
        }
        result = await calculator.calculate_margins(account_state)
        call_args = mock_api_client.simulate_pme.call_args[0][0]
        assert call_args["BTC-PERPETUAL"] == 1.5
