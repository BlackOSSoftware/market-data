from __future__ import annotations

import time
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
}


class MT5Client:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connected = False
        self._suffix_priority = [".M", ".R", ".P"]

    def connect(self) -> None:
        if self._connected:
            return
        if self._settings.mt5_path:
            mt5.initialize(self._settings.mt5_path)
        else:
            mt5.initialize()

        if self._settings.mt5_login and self._settings.mt5_password:
            mt5.login(
                self._settings.mt5_login,
                password=self._settings.mt5_password,
                server=self._settings.mt5_server or None,
            )
        self._connected = True

    def shutdown(self) -> None:
        if self._connected:
            mt5.shutdown()
        self._connected = False

    def get_timeframe(self, code: str) -> int:
        return _TIMEFRAMES.get(code.upper(), mt5.TIMEFRAME_M1)

    def resolve_symbol(self, symbol: str) -> Optional[str]:
        sym = symbol.strip().upper()
        if not sym:
            return None
        info = mt5.symbol_info(sym)
        if info is not None:
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
                    return n
        return matches[0]

    def ensure_symbol(self, symbol: str) -> bool:
        info = mt5.symbol_info(symbol)
        if info is None:
            return False
        if not info.visible:
            mt5.symbol_select(symbol, True)
        return True

    def fetch_market_data(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        actual = self.resolve_symbol(symbol)
        if not actual or not self.ensure_symbol(actual):
            return None

        tick = mt5.symbol_info_tick(actual)
        tf = self.get_timeframe(timeframe)
        rates = mt5.copy_rates_from_pos(actual, tf, 0, 1)

        if tick is None:
            return None

        bar = rates[0] if rates is not None and len(rates) > 0 else None

        return {
            "symbol": actual,
            "requested": symbol,
            "time": int(tick.time) if tick.time else int(time.time()),
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "last": float(tick.last) if tick.last is not None else None,
            "open": float(bar["open"]) if bar is not None else None,
            "high": float(bar["high"]) if bar is not None else None,
            "low": float(bar["low"]) if bar is not None else None,
            "close": float(bar["close"]) if bar is not None else None,
            "volume": float(bar["real_volume"]) if bar is not None else None,
        }
