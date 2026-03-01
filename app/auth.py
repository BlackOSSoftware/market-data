import hmac
from typing import Iterable


def is_valid_key(key: str, allowed: Iterable[str]) -> bool:
    if not key:
        return False
    for item in allowed:
        if hmac.compare_digest(key, item):
            return True
    return False


def is_admin_key(key: str, admin_key: str) -> bool:
    if not key or not admin_key:
        return False
    return hmac.compare_digest(key, admin_key)
