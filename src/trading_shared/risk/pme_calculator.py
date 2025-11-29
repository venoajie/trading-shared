# src\trading_shared\risk\pme_calculator.py

from typing import Dict, Optional, Any
from loguru import logger as log

# Use relative imports or shared library imports
from ..exchange.trading.deribit import DeribitTradingClient
from .models import MarginCalculationResult


class PortfolioMarginCalculator:
    def __init__(self, api_client: DeribitTradingClient):
        self.api_client = api_client

    async def calculate_margins(
        self,
        account_state: Any,  # typed as Any to avoid circular dependency on AccountState
        hypothetical_positions: Optional[Dict[str, float]] = None,
    ) -> MarginCalculationResult:
        simulated_positions: Dict[str, float] = {}

        # Logic adapted to assume account_state has tracked_positions
        if hasattr(account_state, "tracked_positions"):
            for position_data in account_state.tracked_positions.values():
                # Robust check for opening trades
                trades = position_data.get("opening_trades", [])
                if trades:
                    instrument_name = trades[0]["instrument_name"]
                    net_amount = float(position_data.get("net_amount", 0))
                    simulated_positions[instrument_name] = (
                        simulated_positions.get(instrument_name, 0) + net_amount
                    )

        if hypothetical_positions:
            for instrument, size in hypothetical_positions.items():
                simulated_positions[instrument] = (
                    simulated_positions.get(instrument, 0) + size
                )

        if not simulated_positions:
            return MarginCalculationResult(
                initial_margin=0.0, maintenance_margin=0.0, is_valid=True
            )

        response = await self.api_client.simulate_pme(simulated_positions)

        if not response.get("success"):
            error_msg = f"PME simulation API call failed: {response.get('error')}"
            log.error(error_msg)
            return MarginCalculationResult(
                initial_margin=0.0,
                maintenance_margin=0.0,
                is_valid=False,
                error_message=error_msg,
            )

        try:
            margin_data = response["data"]["margins"]["cross"]
            return MarginCalculationResult(
                initial_margin=float(margin_data["initial_margin"]),
                maintenance_margin=float(margin_data["maintenance_margin"]),
                is_valid=True,
            )
        except (KeyError, TypeError, ValueError) as e:
            error_msg = f"Failed to parse PME response: {e}"
            log.exception(error_msg)
            return MarginCalculationResult(
                initial_margin=0.0,
                maintenance_margin=0.0,
                is_valid=False,
                error_message=error_msg,
            )
