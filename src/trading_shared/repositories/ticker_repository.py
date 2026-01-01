# src/trading_shared/repositories/ticker_repository.py

# --- Built Ins ---
from datetime import UTC, datetime
from typing import Any

# --- Installed ---
from loguru import logger as log

# --- Local Application Imports ---
from trading_shared.clients.postgres_client import PostgresClient


class TickerRepository:
    def __init__(self, db_client: PostgresClient):
        self._db = db_client

    async def bulk_upsert(self, tickers_data: list[dict[str, Any]]):
        if not tickers_data:
            return

        records_to_upsert = []
        for ticker in tickers_data:
            ts_ms = ticker.get("exchange_timestamp")
            if not ts_ms:
                log.warning(
                    f"Ticker for {ticker.get('instrument_name')} is missing 'exchange_timestamp'. Skipping."
                )
                continue
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            records_to_upsert.append(
                (
                    ticker.get("instrument_name"),
                    ticker.get("last_price"),
                    ticker.get("mark_price"),
                    ticker.get("index_price"),
                    ticker.get("open_interest"),
                    ticker.get("best_bid_price"),
                    ticker.get("best_ask_price"),
                    ticker,
                    ts,
                )
            )

        query = """
            INSERT INTO tickers (
                exchange, instrument_name, last_price, mark_price, index_price, open_interest,
                best_bid_price, best_ask_price, data, exchange_timestamp, recorded_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            ON CONFLICT (exchange, instrument_name) DO UPDATE SET
                last_price = EXCLUDED.last_price, mark_price = EXCLUDED.mark_price, index_price = EXCLUDED.index_price,
                open_interest = EXCLUDED.open_interest, best_bid_price = EXCLUDED.best_bid_price,
                best_ask_price = EXCLUDED.best_ask_price, data = EXCLUDED.data,
                exchange_timestamp = EXCLUDED.exchange_timestamp, recorded_at = NOW();
        """
        try:
            await self._db.execute(query, *records_to_upsert)
            log.debug(f"Successfully bulk-upserted {len(records_to_upsert)} tickers.")
        except Exception as e:
            log.error(f"Error during bulk upsert of tickers: {e}")
            raise
