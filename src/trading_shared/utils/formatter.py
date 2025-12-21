# src/trading_shared/utils/formatter.py


# --- Helper Functions for Formatting ---
def format_currency(value: float, precision: int = 2) -> str:
    if value > 1_000_000_000:
        return f"${value/1_000_000_000:.{precision}f}B"
    if value > 1_000_000:
        return f"${value/1_000_000:.{precision}f}M"
    if value > 1_000:
        return f"${value/1_000:.{precision}f}K"
    return f"${value:.{precision}f}"

def format_percent(value: float) -> str:
    return f"{'+' if value >= 0 else ''}{value:.2%}"
