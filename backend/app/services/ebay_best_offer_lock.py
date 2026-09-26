"""Session advisory locks survive the legacy token/importer's commits."""
from contextlib import contextmanager
import hashlib
from sqlalchemy import text
from fastapi import HTTPException


def lock_key(value):
    return int.from_bytes(hashlib.sha256(('aces:best-offer:' + str(value)).encode()).digest()[:8], 'big', signed=True)


@contextmanager
def account_operation_lock(bind, account_id):
    engine = getattr(bind, 'engine', bind)
    with engine.connect() as connection:
        key = lock_key(account_id)
        acquired = connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': key})
        connection.commit()
        if not acquired:
            raise HTTPException(409, 'Best Offer provider operation already running for this account')
        try:
            yield
        finally:
            connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': key})
            connection.commit()
