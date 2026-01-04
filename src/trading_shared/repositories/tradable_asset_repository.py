# src/trading_shared/repositories/tradable_asset_repository.py

# --- Built Ins ---
from collections import defaultdict

# --- Installed ---
from loguru import logger as log

# --- Shared Library Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class TradableAssetRepository:
    """
    Manages access to the canonical `tradable_assets` ledger.
    This is the single source of truth for determining which instruments
    are actively monitored and traded by the system.
    """

    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def fetch_all_instruments_by_exchange(self) -> dict[str, list[str]]:
        """
        Fetches all active, tradable instruments and groups them by exchange.
        This is used by the Backfill service to discover work.

        Returns:
            A dictionary mapping exchange names to a list of instrument names.
            e.g., {'binance': ['BTCUSDT', 'ETHUSDT'], 'deribit': ['BTC-PERPETUAL']}
        """
        # This query joins the ledger with the instruments table to get the
        # specific instrument names and their exchanges for both spot and perpetuals.
        query = """
        SELECT
            spot.exchange AS exchange,
            spot.instrument_name AS instrument
        FROM tradable_assets ta
        JOIN instruments spot ON ta.spot_instrument_id = spot.id
        WHERE ta.is_active = TRUE AND spot.is_active = TRUE
        UNION
        SELECT
            perp.exchange AS exchange,
            perp.instrument_name AS instrument
        FROM tradable_assets ta
        JOIN instruments perp ON ta.linear_perp_instrument_id = perp.id
        WHERE ta.is_active = TRUE AND perp.is_active = TRUE;
        """
        try:
            records = await self._db.fetch(query)

            # Group the flat list of records into the required dictionary structure
            grouped_instruments = defaultdict(list)
            for record in records:
                grouped_instruments[record["exchange"]].append(record["instrument"])

            log.info(f"Fetched tradable instruments for {len(grouped_instruments)} exchanges.")
            return dict(grouped_instruments)

        except Exception:
            log.exception("Failed to fetch tradable instruments by exchange.")
            return {}
