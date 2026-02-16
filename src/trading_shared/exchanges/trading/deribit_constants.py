# src\shared_exchange_clients\trading\deribit\constants.py

"""
Static application constants
"""


class ApiMethods:
    """Centralizes the string names for API endpoints."""

    # Public
    GET_INSTRUMENTS = "public/get_instruments"
    GET_TRADINGVIEW_CHART_DATA = "public/get_tradingview_chart_data"


    # --- Private (Account) ---
    GET_ACCOUNT_SUMMARY = "private/get_account_summary"
    GET_POSITIONS = "private/get_positions"
    GET_SUBACCOUNTS = "private/get_subaccounts"


    # --- Private (Trading) ---
    BUY = "private/buy"
    SELL = "private/sell"
    EDIT = "private/edit"
    CANCEL = "private/cancel"
    CANCEL_ALL = "private/cancel_all"
    GET_OPEN_ORDERS_BY_CURRENCY = "private/get_open_orders_by_currency"
    GET_ORDER_STATE = "private/get_order_state"



    # Private
    GET_TRANSACTION_LOG = "private/get_transaction_log"
    GET_SUBACCOUNTS_DETAILS = "private/get_subaccounts_details"
    GET_OPEN_ORDERS_BY_CURRENCY = "private/get_open_orders_by_currency"
    GET_USER_TRADES_BY_ORDER = "private/get_user_trades_by_order"
    SIMULATE_PME = "private/pme/simulate"
    # --- Private (Risk/PME) ---
    SIMULATE_PME = "private/get_portfolio_margins"
    
class AccountId:
    DERIBIT_MAIN = "deribit-148510"


class WebsocketParameters:
    RECONNECT_BASE_DELAY = 5
    MAX_RECONNECT_DELAY = 3600
    MAINTENANCE_THRESHOLD = 300
    HEARTBEAT_INTERVAL = 30
    WEBSOCKET_TIMEOUT = 300
