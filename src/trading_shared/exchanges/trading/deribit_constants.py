# src\shared_exchange_clients\trading\deribit\constants.py

"""
Static application constants
"""


class ApiMethods:
    """Centralizes the string names for API endpoints."""

    # Public
    GET_INSTRUMENTS = "public/get_instruments"
    GET_TRADINGVIEW_CHART_DATA = "public/get_tradingview_chart_data"

    # --- Private (Trading) ---
    BUY = "private/buy"
    SELL = "private/sell"
    EDIT = "private/edit"
    CANCEL = "private/cancel"
    CANCEL_ALL = "private/cancel_all"
    CANCEL_ALL_BY_KIND_OR_TYPE = "private/cancel_all_by_kind_or_type"

    # --- Private (Account) ---
    GET_ACCOUNT_SUMMARY = "private/get_account_summary"
    GET_ACCOUNT_SUMMARIES = "private/get_account_summaries"
    GET_MARGINS = "private/get_margins"
    GET_OPEN_ORDERS_BY_CURRENCY = "private/get_open_orders_by_currency"
    GET_ORDER_STATE = "private/get_order_state"
    GET_POSITION = "private/get_position"
    GET_POSITIONS = "private/get_positions"
    GET_SUBACCOUNTS = "private/get_subaccounts"
    GET_SUBACCOUNTS_DETAILS = "private/get_subaccounts_details"
    GET_TRANSACTION_LOG = "private/get_transaction_log"
    GET_USER_TRADES_BY_ORDER = "private/get_user_trades_by_order"
    GET_USER_TRADES_BY_CURRENCY = "private/get_user_trades_by_currency"

    # --- Private (Risk/PME) ---
    SIMULATE_PME = "private/pme/simulate"
    SIMULATE_PORTFOLIO = "private/simulate_portfolio"


class AccountId:
    DERIBIT_MAIN = "deribit-148510"


class WebsocketParameters:
    RECONNECT_BASE_DELAY = 5
    MAX_RECONNECT_DELAY = 3600
    MAINTENANCE_THRESHOLD = 300
    HEARTBEAT_INTERVAL = 30
    WEBSOCKET_TIMEOUT = 300
