# src\trading_shared\utils\identity.py

# --- Built Ins  ---
import asyncio
import uuid

# --- Installed  ---
from loguru import logger as log
import oracledb

# Namespace for Trading App Accounts - DO NOT CHANGE
TRADING_IDENTITY_NAMESPACE = uuid.UUID("951e7376-a07e-52ad-9477-030913972236")


def get_account_uuid(account_id: str) -> uuid.UUID:
    """
    Deterministically converts a string account ID (e.g., 'deribit-148510')
    into a valid UUIDv5 for database persistence.
    """
    return uuid.uuid5(TRADING_IDENTITY_NAMESPACE, account_id)


async def provision_identity(pool: oracledb.SessionPool, account_id: str):
    """
    Ensures that a user record exists in the OCI 'users' table for the given legacy account ID.
    If it does not exist, it is created automatically (JIT Provisioning).
    """
    user_uuid = get_account_uuid(account_id)

    # Create a deterministic analytics ID so it remains constant across restarts
    analytics_uuid = uuid.uuid5(TRADING_IDENTITY_NAMESPACE, f"{account_id}_analytics")

    dummy_email = f"{account_id}@legacy.system"
    dummy_hash = "SYSTEM_ACCOUNT_LOCKED"

    # Explicitly insert ALL required columns, including analytics_id
    sql = """
    MERGE INTO users u
    USING (SELECT :id_raw AS id FROM dual) src
    ON (u.id = src.id)
    WHEN NOT MATCHED THEN
        INSERT (id, email, hashed_password, user_data, analytics_id)
        VALUES (:id_raw, :email, :pw, '{"type": "jit_provisioned_system_account"}', :analytics_raw)
    """

    log.info(f"Provisioning identity for '{account_id}' (User UUID: {user_uuid})...")

    try:
        # Run in a separate thread because oracledb is blocking
        await asyncio.to_thread(
            _execute_provision_sql,
            pool,
            sql,
            user_uuid,
            dummy_email,
            dummy_hash,
            analytics_uuid,
        )
        log.success(f"Identity for '{account_id}' is provisioned and ready.")
    except Exception as e:
        log.critical(f"Failed to provision identity for '{account_id}': {e}")
        # We re-raise to stop the application start-up, as it cannot function without a DB user
        raise


def _execute_provision_sql(pool, sql, user_uuid, email, pw, analytics_uuid):
    with pool.acquire() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                {
                    "id_raw": user_uuid.bytes,
                    "email": email,
                    "pw": pw,
                    "analytics_raw": analytics_uuid.bytes,
                },
            )
            connection.commit()
