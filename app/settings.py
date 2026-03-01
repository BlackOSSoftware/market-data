import os
from dataclasses import dataclass
from pathlib import Path


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mt5_path: str
    mt5_login: int
    mt5_password: str
    mt5_server: str
    api_keys: set[str]
    admin_key: str
    keys_file: Path
    default_timeframe: str
    default_interval_ms: int


def load_settings() -> Settings:
    mt5_login_raw = _get_env("MT5_LOGIN", "0")
    try:
        mt5_login = int(mt5_login_raw)
    except ValueError:
        mt5_login = 0

    keys_raw = _get_env("API_KEYS", "")
    api_keys = {k.strip() for k in keys_raw.split(",") if k.strip()}

    timeframe = _get_env("DEFAULT_TIMEFRAME", "M1")
    interval_ms_raw = _get_env("DEFAULT_INTERVAL_MS", "100")
    try:
        interval_ms = int(interval_ms_raw)
    except ValueError:
        interval_ms = 100

    keys_file = Path(_get_env("API_KEYS_FILE", "data/api_keys.json"))

    return Settings(
        mt5_path=_get_env("MT5_PATH", ""),
        mt5_login=mt5_login,
        mt5_password=_get_env("MT5_PASSWORD", ""),
        mt5_server=_get_env("MT5_SERVER", ""),
        api_keys=api_keys,
        admin_key=_get_env("ADMIN_KEY", ""),
        keys_file=keys_file,
        default_timeframe=timeframe,
        default_interval_ms=interval_ms,
    )
