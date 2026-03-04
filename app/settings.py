import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mt5_path: str
    mt5_login: Optional[int]
    mt5_password: str
    mt5_server: str
    api_keys: set[str]
    admin_key: str
    keys_file: Path
    redis_url: str
    redis_keys_set: str
    default_timeframe: str
    default_interval_ms: int


def load_settings() -> Settings:
    mt5_login_raw = _get_env("MT5_LOGIN", "")
    mt5_login = None
    if mt5_login_raw:
        try:
            parsed = int(mt5_login_raw)
            if parsed > 0:
                mt5_login = parsed
        except ValueError:
            mt5_login = None

    keys_raw = _get_env("API_KEYS", "")
    api_keys = {k.strip() for k in keys_raw.split(",") if k.strip()}

    timeframe = _get_env("DEFAULT_TIMEFRAME", "M1")
    interval_ms_raw = _get_env("DEFAULT_INTERVAL_MS", "100")
    try:
        interval_ms = int(interval_ms_raw)
    except ValueError:
        interval_ms = 100

    keys_file = Path(_get_env("API_KEYS_FILE", "data/api_keys.json"))
    redis_url = _get_env("REDIS_URL", "")
    redis_keys_set = _get_env("REDIS_KEYS_SET", "api_keys")

    return Settings(
        mt5_path=_get_env("MT5_PATH", ""),
        mt5_login=mt5_login,
        mt5_password=_get_env("MT5_PASSWORD", ""),
        mt5_server=_get_env("MT5_SERVER", ""),
        api_keys=api_keys,
        admin_key=_get_env("ADMIN_KEY", ""),
        keys_file=keys_file,
        redis_url=redis_url,
        redis_keys_set=redis_keys_set,
        default_timeframe=timeframe,
        default_interval_ms=interval_ms,
    )
