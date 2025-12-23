# src/shared/trading_shared/utils/asset_utils.py

# Define constants for maintainability
DENOMINATION_PREFIXES = ["1000", "10000", "100000", "1000000"]
LEVERAGED_SUFFIXES = ["UP", "DOWN"]


def normalize_base_asset(base_asset: str) -> str:
    """
    Sanitizes a base asset string to its canonical form by removing known
    denomination prefixes and leveraged token suffixes.

    Examples:
        - '1000SHIB' -> 'SHIB'
        - 'ADAUP'    -> 'ADA'
        - 'BTC'      -> 'BTC'
    """
    asset = base_asset.upper()
    for prefix in DENOMINATION_PREFIXES:
        if asset.startswith(prefix):
            asset = asset[len(prefix) :]
            break  # Assume only one prefix

    for suffix in LEVERAGED_SUFFIXES:
        if asset.endswith(suffix):
            return asset[: -len(suffix)]

    return asset
