# src\trading_shared\utils\labelling.py

# --- Built Ins  ---
import time
import uuid


def generate_strategy_label(strategy: str, state: str, cycle_id: uuid.UUID | None = None) -> str:
    """
    Generates a standardized label for a new strategy-driven order.
    New Format: {strategy}-{state}-{unix_ms_timestamp}-{cycle_id}
    Legacy Format: {strategy}-{state}-{unix_ms_timestamp}
    """
    unix_ms = int(time.time() * 1000)
    base_label = f"{strategy}-{state}-{unix_ms}"
    if cycle_id:
        return f"{base_label}-{str(cycle_id)}"
    return base_label


def generate_closing_label(opening_label: str) -> str | None:
    """
    Generates a closing label from a corresponding opening label, preserving the cycle_id.
    Example: 'hedgingSpot-open-123-uuid' -> 'hedgingSpot-closed-123-uuid'
    """
    parts = opening_label.split("-")
    if len(parts) < 3 or parts[1] != "open":
        return None
    parts[1] = "closed"
    return "-".join(parts)


def parse_label(label: str) -> tuple[str, str, str, str | None] | None:
    """
    Parses a standardized label into its components.
    Handles both legacy (3-part) and new (4-part) formats.
    Returns (strategy, state, timestamp, cycle_id) or None if invalid.
    """
    if not label:
        return None
    parts = label.split("-")
    if len(parts) == 4:
        # New format: strategy-state-timestamp-cycle_id
        return parts[0], parts[1], parts[2], parts[3]
    if len(parts) == 3:
        # Legacy format: strategy-state-timestamp
        return parts[0], parts[1], parts[2], None
    return None
