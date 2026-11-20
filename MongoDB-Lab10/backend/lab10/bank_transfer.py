
import time
import uuid
from datetime import datetime, timezone

from pymongo.errors import PyMongoError

from backend.db import client, db


accounts = db["accounts"]
transaction_history = db["transaction_history"]


class InsufficientFundsError(Exception):
    pass


class AccountNotFoundError(Exception):
    pass


def initialize_accounts():
    """Create two demo accounts without overwriting existing balances."""

    accounts.update_one(
        {"account_id": "ACC001"},
        {
            "$setOnInsert": {
                "account_id": "ACC001",
                "balance": 1000,
                "version": 1
            }
        },
        upsert=True
    )

    accounts.update_one(
        {"account_id": "ACC002"},
        {
            "$setOnInsert": {
                "account_id": "ACC002",
                "balance": 500,
                "version": 1
            }
        },
        upsert=True
    )

    print("Bank accounts initialized.")


def get_account(account_id):
    """Retrieve an account."""

    return accounts.find_one(
        {"account_id": account_id},
        {"_id": 0}
    )


def get_all_accounts():
    """Retrieve all bank accounts."""

    return list(accounts.find({}, {"_id": 0}))


def transfer_money(
    source_account,
    destination_account,
    amount,
    max_retries=5
):
    """
    Transfer money using a MongoDB multi-document transaction.

    Retries the complete transaction when MongoDB returns
    the TransientTransactionError label.
    """

    if amount <= 0:
        raise ValueError("Transfer amount must be positive.")

    if source_account == destination_account:
        raise ValueError("Source and destination must differ.")

    transfer_id = str(uuid.uuid4())

    for attempt in range(max_retries):

        try:
            with client.start_session() as session:

                with session.start_transaction():

                    source = accounts.find_one(
                        {"account_id": source_account},
                        session=session
                    )

                    if source is None:
                        raise AccountNotFoundError(
                            f"Account {source_account} not found."
                        )

                    if source["balance"] < amount:
                        raise InsufficientFundsError(
                            "Insufficient funds in source account."
                        )

                    destination = accounts.find_one(
                        {"account_id": destination_account},
                        session=session
                    )

                    if destination is None:
                        raise AccountNotFoundError(
                            f"Account {destination_account} not found."
                        )

                    # Debit source account.
                    debit = accounts.update_one(
                        {
                            "account_id": source_account,
                            "balance": {"$gte": amount},
                            "version": source["version"]
                        },
                        {
                            "$inc": {
                                "balance": -amount,
                                "version": 1
                            }
                        },
                        session=session
                    )

                    if debit.modified_count != 1:
                        raise RuntimeError(
                            "Source account update failed."
                        )

                    # Credit destination account.
                    credit = accounts.update_one(
                        {
                            "account_id": destination_account,
                            "version": destination["version"]
                        },
                        {
                            "$inc": {
                                "balance": amount,
                                "version": 1
                            }
                        },
                        session=session
                    )

                    if credit.modified_count != 1:
                        raise RuntimeError(
                            "Destination account update failed."
                        )

                    # Record transaction history.
                    transaction_history.insert_one(
                        {
                            "transfer_id": transfer_id,
                            "source_account": source_account,
                            "destination_account": destination_account,
                            "amount": amount,
                            "status": "SUCCESS",
                            "timestamp": datetime.now(timezone.utc)
                        },
                        session=session
                    )

            return {
                "success": True,
                "transfer_id": transfer_id,
                "message": "Transfer completed successfully.",
                "amount": amount,
                "attempts": attempt + 1
            }

        except PyMongoError as error:

            if error.has_error_label("TransientTransactionError"):

                if attempt == max_retries - 1:
                    raise

                delay = 0.1 * (2 ** attempt)

                print(
                    f"Transient transaction error. "
                    f"Retry {attempt + 1}/{max_retries} "
                    f"after {delay:.2f} seconds."
                )

                time.sleep(delay)
                continue

            raise

    raise RuntimeError("Transaction failed after maximum retries.")


def get_transaction_history():
    """Retrieve successful transfer records."""

    return list(
        transaction_history.find(
            {},
            {"_id": 0}
        ).sort("timestamp", -1)
    )
