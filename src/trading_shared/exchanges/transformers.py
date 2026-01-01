# src/trading_shared/exchanges/transformer.py

# --- Built Ins  ---
from datetime import datetime, timezone
from typing import Any

# --- Installed  ---
from loguru import logger as log

# --- Shared Library Imports  ---
# from trading_shared.exchanges.mappers import get_canonical_market_type
from .mappers import get_canonical_market_type


def transform_binance_instrument_to_canonical(raw_instrument: dict[str, Any], market_type_hint: str) -> dict[str, Any] | None:
    """
    Transforms a single raw Binance instrument into our canonical format.
    """

    def get_tick_size(filters: list) -> float | None:
        for f in filters:
            if f.get("filterType") == "PRICE_FILTER":
                return float(f.get("tickSize", 0.0))
        return None

    contract_type = raw_instrument.get("contractType")

    canonical_market_type = get_canonical_market_type("binance", raw_instrument, source_hint=market_type_hint)
    market_type = canonical_market_type.value

    if market_type == "spot":
        instrument_kind = "spot"
        settlement_asset = raw_instrument.get("quoteAsset")
    elif market_type == "linear_futures":
        instrument_kind = "perpetual" if contract_type == "PERPETUAL" else "future"
        settlement_asset = raw_instrument.get("marginAsset")
    elif market_type == "inverse_futures":
        instrument_kind = "perpetual" if contract_type == "PERPETUAL" else "future"
        settlement_asset = raw_instrument.get("marginAsset")
    else:
        instrument_kind = "unknown"
        settlement_asset = None

    if not settlement_asset:
        log.warning(f"Could not determine settlement_asset for {raw_instrument.get('symbol')} in market {market_type}. Skipping instrument.")
        return None

    exp_ts_ms = raw_instrument.get("deliveryDate")
    expiration_timestamp = datetime.fromtimestamp(exp_ts_ms / 1000, tz=timezone.utc).isoformat() if exp_ts_ms else None

    return {
        "exchange": "binance",
        "instrument_name": raw_instrument.get("symbol"),
        "market_type": market_type,
        "instrument_kind": instrument_kind,
        "base_asset": raw_instrument.get("baseAsset"),
        "quote_asset": raw_instrument.get("quoteAsset"),
        "settlement_asset": settlement_asset,
        "settlement_period": None,
        "tick_size": get_tick_size(raw_instrument.get("filters", [])),
        "contract_size": raw_instrument.get("contractSize"),
        "expiration_timestamp": expiration_timestamp,
        "data": raw_instrument,
    }


def transform_deribit_instrument_to_canonical(
    raw_instrument: dict[str, Any],
) -> dict[str, Any]:
    """Transforms a single raw Deribit instrument into our canonical format."""
    instrument_name = raw_instrument.get("instrument_name")
    kind = raw_instrument.get("kind")

    if kind == "future":
        instrument_kind = "perpetual" if "PERPETUAL" in instrument_name else "future"
    elif kind == "option":
        instrument_kind = "option"
    else:
        instrument_kind = "unknown"

    exp_ts_ms = raw_instrument.get("expiration_timestamp")
    expiration_timestamp = datetime.fromtimestamp(exp_ts_ms / 1000, tz=timezone.utc).isoformat() if exp_ts_ms else None
    canonical_market_type = get_canonical_market_type("deribit", raw_instrument)

    return {
        "exchange": "deribit",
        "instrument_name": instrument_name,
        "market_type": canonical_market_type.value,
        "instrument_kind": instrument_kind,
        "base_asset": raw_instrument.get("base_currency"),
        "quote_asset": raw_instrument.get("quote_currency"),
        "settlement_asset": raw_instrument.get("settlement_currency") or raw_instrument.get("base_currency"),
        "settlement_period": raw_instrument.get("settlement_period"),
        "tick_size": raw_instrument.get("tick_size"),
        "contract_size": raw_instrument.get("contract_size"),
        "expiration_timestamp": expiration_timestamp,
        "data": raw_instrument,
    }
