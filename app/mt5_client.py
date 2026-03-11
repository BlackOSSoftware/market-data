from __future__ import annotations

import time
from threading import Lock
from typing import Any, Dict, Optional

import MetaTrader5 as mt5

from .settings import Settings


_TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,
    "M3": mt5.TIMEFRAME_M3,
    "M4": mt5.TIMEFRAME_M4,
    "M5": mt5.TIMEFRAME_M5,
    "M6": mt5.TIMEFRAME_M6,
    "M10": mt5.TIMEFRAME_M10,
    "M12": mt5.TIMEFRAME_M12,
    "M15": mt5.TIMEFRAME_M15,
    "M20": mt5.TIMEFRAME_M20,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H2": mt5.TIMEFRAME_H2,
    "H3": mt5.TIMEFRAME_H3,
    "H4": mt5.TIMEFRAME_H4,
    "H6": mt5.TIMEFRAME_H6,
    "H8": mt5.TIMEFRAME_H8,
    "H12": mt5.TIMEFRAME_H12,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
    "1": mt5.TIMEFRAME_M1,
    "2": mt5.TIMEFRAME_M2,
    "3": mt5.TIMEFRAME_M3,
    "4": mt5.TIMEFRAME_M4,
    "5": mt5.TIMEFRAME_M5,
    "6": mt5.TIMEFRAME_M6,
    "10": mt5.TIMEFRAME_M10,
    "12": mt5.TIMEFRAME_M12,
    "15": mt5.TIMEFRAME_M15,
    "20": mt5.TIMEFRAME_M20,
    "30": mt5.TIMEFRAME_M30,
    "45": mt5.TIMEFRAME_H1,
    "60": mt5.TIMEFRAME_H1,
    "120": mt5.TIMEFRAME_H2,
    "180": mt5.TIMEFRAME_H3,
    "240": mt5.TIMEFRAME_H4,
    "360": mt5.TIMEFRAME_H6,
    "480": mt5.TIMEFRAME_H8,
    "720": mt5.TIMEFRAME_H12,
    "D": mt5.TIMEFRAME_D1,
    "1D": mt5.TIMEFRAME_D1,
    "DAY": mt5.TIMEFRAME_D1,
    "W": mt5.TIMEFRAME_W1,
    "1W": mt5.TIMEFRAME_W1,
    "WEEK": mt5.TIMEFRAME_W1,
    "M": mt5.TIMEFRAME_MN1,
    "1M": mt5.TIMEFRAME_MN1,
    "MN": mt5.TIMEFRAME_MN1,
}


class MT5Client:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connected = False
        self._suffix_priority = [".M", ".R", ".P"]
        self._cache_lock = Lock()
        self._resolved_symbols: Dict[str, str] = {}
        self._symbol_specs: Dict[str, Dict[str, Any]] = {}
        self._history_cache: Dict[str, Dict[str, Any]] = {}
        self._history_cache_ttl = 2.0
        self._history_cache_max = 256

    def connect(self) -> None:
        if self._connected:
            return
        initialize_ok = (
            mt5.initialize(self._settings.mt5_path)
            if self._settings.mt5_path
            else mt5.initialize()
        )
        if not initialize_ok:
            code, msg = mt5.last_error()
            raise RuntimeError(f"MT5 initialize failed ({code}): {msg}")

        # If credentials are absent, reuse the account already logged in MT5 terminal.
        if self._settings.mt5_login:
            login_kwargs = {}
            if self._settings.mt5_password:
                login_kwargs["password"] = self._settings.mt5_password
            if self._settings.mt5_server:
                login_kwargs["server"] = self._settings.mt5_server

            if not mt5.login(self._settings.mt5_login, **login_kwargs):
                code, msg = mt5.last_error()
                mt5.shutdown()
                raise RuntimeError(f"MT5 login failed ({code}): {msg}")
        elif mt5.account_info() is None:
            mt5.shutdown()
            raise RuntimeError(
                "MT5 account not logged in. Open MT5 terminal and login once,"
                " or set MT5_LOGIN (and optionally MT5_PASSWORD/MT5_SERVER)."
            )
        self._connected = True

    def shutdown(self) -> None:
        if self._connected:
            mt5.shutdown()
        self._connected = False
        with self._cache_lock:
            self._resolved_symbols.clear()
            self._symbol_specs.clear()

    def get_timeframe(self, code: str) -> int:
        return _TIMEFRAMES.get(code.upper(), mt5.TIMEFRAME_M1)

    def resolve_symbol(self, symbol: str) -> Optional[str]:
        sym = symbol.strip().upper()
        if not sym:
            return None
        with self._cache_lock:
            cached = self._resolved_symbols.get(sym)
        if cached and mt5.symbol_info(cached) is not None:
            return cached

        info = mt5.symbol_info(sym)
        if info is not None:
            with self._cache_lock:
                self._resolved_symbols[sym] = sym
            return sym
        symbols = mt5.symbols_get()
        if not symbols:
            return None
        names = [s.name for s in symbols]
        # Prefer exact or suffix match
        matches = [n for n in names if n.upper() == sym]
        if not matches:
            matches = [
                n
                for n in names
                if n.upper().startswith(sym + ".") or n.upper().startswith(sym)
            ]
        if not matches:
            return None
        for suffix in self._suffix_priority:
            for n in matches:
                if n.upper().endswith(suffix):
                    with self._cache_lock:
                        self._resolved_symbols[sym] = n
                    return n
        chosen = matches[0]
        with self._cache_lock:
            self._resolved_symbols[sym] = chosen
        return chosen

    def ensure_symbol(self, symbol: str) -> bool:
        info = mt5.symbol_info(symbol)
        if info is None:
            return False
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                return False
        return True

    def _get_symbol_spec(self, symbol: str) -> Optional[Dict[str, Any]]:
        with self._cache_lock:
            cached = self._symbol_specs.get(symbol)
        if cached is not None:
            return cached

        info = mt5.symbol_info(symbol)
        if info is None:
            return None

        digits = max(int(getattr(info, "digits", 0) or 0), 0)
        point = float(getattr(info, "point", 0.0) or 0.0)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or 0.0)
        if tick_size <= 0.0:
            if point > 0.0:
                tick_size = point
            elif digits > 0:
                tick_size = 1.0 / (10 ** digits)

        scale = 10 ** digits if digits > 0 else 1
        tick_steps = int(round(tick_size * scale)) if tick_size > 0.0 else 1
        if tick_steps <= 0:
            tick_steps = 1

        spec = {
            "digits": digits,
            "point": point,
            "tick_size": tick_size,
            "scale": scale,
            "tick_steps": tick_steps,
        }
        with self._cache_lock:
            self._symbol_specs[symbol] = spec
        return spec

    def _normalize_price(
        self, value: Optional[float], spec: Dict[str, Any]
    ) -> Optional[float]:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        scale = int(spec["scale"])
        tick_steps = int(spec["tick_steps"])
        scaled = int(round(numeric * scale))
        normalized = int(round(scaled / tick_steps)) * tick_steps
        return normalized / scale

    def _get_history_cache(self, key: str) -> Optional[list[dict[str, Any]]]:
        now = time.monotonic()
        with self._cache_lock:
            entry = self._history_cache.get(key)
        if not entry:
            return None
        age = now - entry["ts"]
        if age <= self._history_cache_ttl:
            return entry["data"]
        with self._cache_lock:
            current = self._history_cache.get(key)
            if current and current.get("ts") == entry["ts"]:
                self._history_cache.pop(key, None)
        return None

    def _set_history_cache(self, key: str, data: list[dict[str, Any]]) -> None:
        now = time.monotonic()
        with self._cache_lock:
            self._history_cache[key] = {"ts": now, "data": data}
            if len(self._history_cache) <= self._history_cache_max:
                return
            oldest_key = min(self._history_cache.items(), key=lambda item: item[1]["ts"])[0]
            self._history_cache.pop(oldest_key, None)

    def fetch_history(
        self,
        symbol: str,
        timeframe: str,
        count: int,
        from_ts: Optional[int] = None,
        to_ts: Optional[int] = None,
    ) -> Optional[list[dict[str, Any]]]:
        actual = self.resolve_symbol(symbol)
        if not actual or not self.ensure_symbol(actual):
            return None
        spec = self._get_symbol_spec(actual)
        if spec is None:
            return None

        tf = self.get_timeframe(timeframe)
        safe_count = max(int(count or 0), 1)
        cache_key = f"{actual}:{tf}:{safe_count}"
        cached = self._get_history_cache(cache_key)
        if cached is not None:
            return cached

        rates = mt5.copy_rates_from_pos(actual, tf, 0, safe_count)

        if rates is None or len(rates) == 0:
            return []

        candles = []
        for row in rates:
            try:
                ts = int(row["time"])
            except (TypeError, ValueError, KeyError):
                continue
            try:
                open_raw = row["open"]
                high_raw = row["high"]
                low_raw = row["low"]
                close_raw = row["close"]
            except (TypeError, KeyError, IndexError):
                continue
            open_value = self._normalize_price(open_raw, spec)
            high_value = self._normalize_price(high_raw, spec)
            low_value = self._normalize_price(low_raw, spec)
            close_value = self._normalize_price(close_raw, spec)
            if open_value is None or high_value is None or low_value is None or close_value is None:
                continue
            try:
                volume = row["real_volume"]
            except (TypeError, KeyError, IndexError):
                volume = None
            if volume is None:
                try:
                    volume = row["tick_volume"]
                except (TypeError, KeyError, IndexError):
                    volume = 0
            candles.append(
                {
                    "time": ts,
                    "open": open_value,
                    "high": high_value,
                    "low": low_value,
                    "close": close_value,
                    "volume": float(volume) if volume is not None else 0.0,
                }
            )

        candles.sort(key=lambda item: item["time"])
        self._set_history_cache(cache_key, candles)
        return candles

    def fetch_market_data(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        actual = self.resolve_symbol(symbol)
        if not actual or not self.ensure_symbol(actual):
            return None
        spec = self._get_symbol_spec(actual)
        if spec is None:
            return None

        tick = mt5.symbol_info_tick(actual)
        tf = self.get_timeframe(timeframe)
        rates = mt5.copy_rates_from_pos(actual, tf, 0, 1)
        day_rates = mt5.copy_rates_from_pos(actual, mt5.TIMEFRAME_D1, 0, 1)

        if tick is None:
            return None

        bar = rates[0] if rates is not None and len(rates) > 0 else None
        day_bar = day_rates[0] if day_rates is not None and len(day_rates) > 0 else None
        session_bar = day_bar if day_bar is not None else bar

        session_time = None
        if day_bar is not None:
            try:
                session_time = int(day_bar["time"])
            except (TypeError, ValueError, KeyError):
                session_time = None

        return {
            "symbol": actual,
            "requested": symbol,
            "time": int(tick.time) if tick.time else int(time.time()),
            "price_precision": int(spec["digits"]),
            "tick_size": float(spec["tick_size"]),
            "point": float(spec["point"]),
            "bid": self._normalize_price(tick.bid, spec),
            "ask": self._normalize_price(tick.ask, spec),
            "last": self._normalize_price(tick.last, spec),
            "open": self._normalize_price(session_bar["open"], spec) if session_bar is not None else None,
            "high": self._normalize_price(session_bar["high"], spec) if session_bar is not None else None,
            "low": self._normalize_price(session_bar["low"], spec) if session_bar is not None else None,
            "close": self._normalize_price(session_bar["close"], spec) if session_bar is not None else None,
            "day_open": self._normalize_price(day_bar["open"], spec) if day_bar is not None else None,
            "day_high": self._normalize_price(day_bar["high"], spec) if day_bar is not None else None,
            "day_low": self._normalize_price(day_bar["low"], spec) if day_bar is not None else None,
            "day_close": self._normalize_price(day_bar["close"], spec) if day_bar is not None else None,
            "day_time": session_time,
            "volume": float(bar["real_volume"]) if bar is not None else None,
        }
