import asyncio
import json
import secrets
from datetime import datetime, timezone
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
try:
    import redis
except ImportError:  # pragma: no cover - handled at runtime if redis isn't installed
    redis = None

from .auth import is_admin_key, is_valid_key
from .mt5_client import MT5Client
from .settings import load_settings


load_dotenv(dotenv_path=".env")
settings = load_settings()
mt5_client = MT5Client(settings)
_runtime_keys = set(settings.api_keys)
_redis_client = None
if settings.redis_url and redis is not None:
    _redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def _redis_enabled() -> bool:
    return _redis_client is not None


def _load_keys_from_file() -> None:
    if not settings.keys_file.exists():
        settings.keys_file.parent.mkdir(parents=True, exist_ok=True)
        if not _runtime_keys:
            _runtime_keys.add(secrets.token_urlsafe(24))
        settings.keys_file.write_text(json.dumps({"keys": sorted(_runtime_keys)}, indent=2))
        return
    try:
        data = json.loads(settings.keys_file.read_text())
        file_keys = {k.strip() for k in data.get("keys", []) if k.strip()}
        _runtime_keys.update(file_keys)
        if not _runtime_keys:
            _runtime_keys.add(secrets.token_urlsafe(24))
            _save_keys_to_file()
    except (OSError, json.JSONDecodeError):
        return


def _save_keys_to_file() -> None:
    settings.keys_file.parent.mkdir(parents=True, exist_ok=True)
    settings.keys_file.write_text(json.dumps({"keys": sorted(_runtime_keys)}, indent=2))


def _load_keys_from_redis() -> None:
    if not _redis_client:
        return
    if _runtime_keys:
        _redis_client.sadd(settings.redis_keys_set, *_runtime_keys)
    if _redis_client.scard(settings.redis_keys_set) == 0:
        new_key = secrets.token_urlsafe(24)
        _redis_client.sadd(settings.redis_keys_set, new_key)


def _add_key(key: str) -> None:
    if not key:
        return
    _runtime_keys.add(key)
    if _redis_enabled():
        _redis_client.sadd(settings.redis_keys_set, key)
    else:
        _save_keys_to_file()


def _is_valid_api_key(api_key: str) -> bool:
    if not api_key:
        return False
    if _redis_enabled():
        try:
            return bool(_redis_client.sismember(settings.redis_keys_set, api_key))
        except Exception:
            return False
    return is_valid_key(api_key, _runtime_keys)

app = FastAPI(title="MT5 Market Data API", version="1.0.0")
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_model=None)
def index():
    index_path = static_dir / "index.html"
    if not index_path.exists():
        return JSONResponse({"message": "UI not found"}, status_code=404)
    return FileResponse(str(index_path))


@app.on_event("startup")
def _startup() -> None:
    mt5_client.connect()
    if _redis_enabled():
        _load_keys_from_redis()
    else:
        _load_keys_from_file()


@app.on_event("shutdown")
def _shutdown() -> None:
    mt5_client.shutdown()


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api/symbols")
def symbols() -> JSONResponse:
    import MetaTrader5 as mt5

    mt5_client.connect()
    data = mt5.symbols_get()
    names = [s.name for s in data] if data else []
    return JSONResponse({"symbols": names})


@app.get("/api/history")
def history(
    symbol: str = Query(...),
    timeframe: Optional[str] = None,
    resolution: Optional[str] = None,
    count: Optional[int] = None,
    from_: Optional[str] = Query(default=None, alias="from"),
    to_: Optional[str] = Query(default=None, alias="to"),
    key: Optional[str] = None,
    x_api_key: Optional[str] = Header(default=None),
) -> JSONResponse:
    api_key = key or x_api_key or ""
    if not _is_valid_api_key(api_key):
        return JSONResponse({"error": "invalid_api_key"}, status_code=401)

    tf = (resolution or timeframe or settings.default_timeframe or "M1").strip()
    count_value = _clamp_history_count(count, 500)
    from_ts = _parse_timestamp(from_)
    to_ts = _parse_timestamp(to_)

    mt5_client.connect()
    candles = mt5_client.fetch_history(symbol, tf, count_value, from_ts, to_ts)
    if candles is None:
        return JSONResponse({"error": "symbol_unavailable"}, status_code=404)
    return JSONResponse(candles)


@app.post("/api/keys/generate")
def generate_key(x_admin_key: Optional[str] = Header(default=None)) -> JSONResponse:
    admin_key = settings.admin_key
    if not admin_key:
        return JSONResponse({"error": "admin_key_not_configured"}, status_code=500)
    if not is_admin_key(x_admin_key or "", admin_key):
        return JSONResponse({"error": "invalid_admin_key"}, status_code=401)
    new_key = secrets.token_urlsafe(24)
    _add_key(new_key)
    return JSONResponse({"api_key": new_key})


@app.post("/api/keys/request")
def request_key() -> JSONResponse:
    new_key = secrets.token_urlsafe(24)
    _add_key(new_key)
    return JSONResponse({"api_key": new_key})


def _normalize_symbols(values: List[str]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for value in values:
        symbol = value.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    return normalized


def _parse_symbols(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return _normalize_symbols(raw.split(","))


def _parse_symbols_payload(raw: Any) -> List[str]:
    if isinstance(raw, str):
        return _parse_symbols(raw)
    if isinstance(raw, list):
        return _normalize_symbols([item for item in raw if isinstance(item, str)])
    return []


def _parse_interval(raw: Optional[str], default_ms: int) -> int:
    if not raw:
        return default_ms
    try:
        value = int(raw)
    except ValueError:
        return default_ms
    if value < 0:
        return default_ms
    return value


def _parse_timestamp(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    try:
        value = float(raw)
        if value > 10_000_000_000:
            value = value / 1000.0
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        cleaned = str(raw).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except (TypeError, ValueError):
        return None


def _clamp_history_count(raw: Optional[int], default_count: int = 500) -> int:
    try:
        value = int(raw) if raw is not None else default_count
    except (TypeError, ValueError):
        value = default_count
    if value < 500:
        value = 500
    if value > 2000:
        value = 2000
    return value


def _control_state(symbol_list: List[str], interval_ms: int) -> Dict[str, Any]:
    return {
        "symbols": list(symbol_list),
        "interval_ms": interval_ms,
    }


async def _handle_ws_control_message(
    websocket: WebSocket,
    raw_message: str,
    symbol_list: List[str],
    interval_ms: int,
) -> int:
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "control_error",
                    "error": "invalid_json",
                    "message": "Send JSON control messages.",
                }
            )
        )
        return interval_ms

    if not isinstance(payload, dict):
        await websocket.send_text(
            json.dumps(
                {
                    "type": "control_error",
                    "error": "invalid_message",
                    "message": "Control message must be a JSON object.",
                }
            )
        )
        return interval_ms

    action = str(payload.get("action") or payload.get("type") or "").strip().lower()
    if not action:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "control_error",
                    "error": "action_required",
                    "message": "Use action: subscribe, unsubscribe, set_symbols, set_interval, get_state.",
                }
            )
        )
        return interval_ms

    if action in {"ping", "heartbeat"}:
        await websocket.send_text(json.dumps({"type": "pong"}))
        return interval_ms

    if action in {"get_state", "state"}:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "subscription_state",
                    **_control_state(symbol_list, interval_ms),
                }
            )
        )
        return interval_ms

    if action == "set_interval":
        raw_interval = payload.get("interval_ms")
        if raw_interval is None:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "control_error",
                        "error": "interval_required",
                        "message": "Provide interval_ms for set_interval action.",
                    }
                )
            )
            return interval_ms

        interval_ms = _parse_interval(str(raw_interval), interval_ms)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "interval_updated",
                    **_control_state(symbol_list, interval_ms),
                }
            )
        )
        return interval_ms

    if action in {"subscribe", "unsubscribe", "set_symbols"}:
        requested = _parse_symbols_payload(payload.get("symbols"))
        if action != "set_symbols" and not requested:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "control_error",
                        "error": "symbols_required",
                        "message": "Provide symbols as CSV string or array.",
                    }
                )
            )
            return interval_ms

        previous = list(symbol_list)
        previous_set = set(previous)

        if action == "subscribe":
            existing_set = set(previous)
            for symbol in requested:
                if symbol not in existing_set:
                    symbol_list.append(symbol)
                    existing_set.add(symbol)
        elif action == "unsubscribe":
            remove_set = set(requested)
            symbol_list[:] = [symbol for symbol in symbol_list if symbol not in remove_set]
        else:  # set_symbols
            symbol_list[:] = requested

        current_set = set(symbol_list)
        added = [symbol for symbol in symbol_list if symbol not in previous_set]
        removed = [symbol for symbol in previous if symbol not in current_set]

        await websocket.send_text(
            json.dumps(
                {
                    "type": "subscription_updated",
                    "action": action,
                    "added": added,
                    "removed": removed,
                    **_control_state(symbol_list, interval_ms),
                }
            )
        )
        return interval_ms

    await websocket.send_text(
        json.dumps(
            {
                "type": "control_error",
                "error": "unsupported_action",
                "message": "Supported actions: subscribe, unsubscribe, set_symbols, set_interval, get_state.",
            }
        )
    )
    return interval_ms


def _next_tick_delay(interval_ms: int, has_symbols: bool) -> float:
    if not has_symbols:
        return 3600.0
    if interval_ms > 0:
        return interval_ms / 1000.0
    return 0.0


@app.websocket("/ws/market")
async def ws_market(
    websocket: WebSocket,
    symbols: Optional[str] = None,
    interval_ms: Optional[str] = None,
    key: Optional[str] = None,
) -> None:
    await websocket.accept()

    api_key = key or websocket.headers.get("x-api-key", "")
    if not _is_valid_api_key(api_key):
        await websocket.send_text(json.dumps({"error": "invalid_api_key"}))
        await websocket.close(code=1008)
        return

    symbol_list = _parse_symbols(symbols)
    tf = settings.default_timeframe
    interval = _parse_interval(interval_ms, settings.default_interval_ms)
    receive_task: Optional[asyncio.Task[str]] = None
    tick_task: Optional[asyncio.Task[None]] = None

    try:
        await websocket.send_text(
            json.dumps({"type": "subscription_state", **_control_state(symbol_list, interval)})
        )

        receive_task = asyncio.create_task(websocket.receive_text())
        tick_task = asyncio.create_task(
            asyncio.sleep(_next_tick_delay(interval, bool(symbol_list)))
        )

        while True:
            assert receive_task is not None
            assert tick_task is not None

            done, _ = await asyncio.wait(
                {receive_task, tick_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            receive_done = receive_task in done
            tick_done = tick_task in done

            if receive_done:
                try:
                    raw_message = receive_task.result()
                except (WebSocketDisconnect, RuntimeError):
                    return

                interval = await _handle_ws_control_message(
                    websocket=websocket,
                    raw_message=raw_message,
                    symbol_list=symbol_list,
                    interval_ms=interval,
                )

                receive_task = asyncio.create_task(websocket.receive_text())

                if not tick_done:
                    tick_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await tick_task
                    tick_task = asyncio.create_task(
                        asyncio.sleep(_next_tick_delay(interval, bool(symbol_list)))
                    )

            if tick_done:
                if symbol_list:
                    payload = []
                    for symbol in symbol_list:
                        data = await asyncio.to_thread(
                            mt5_client.fetch_market_data, symbol, tf
                        )
                        if data is not None:
                            payload.append(data)
                        else:
                            payload.append({"symbol": symbol, "error": "symbol_unavailable"})

                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "market_data",
                                "symbols": list(symbol_list),
                                "data": payload,
                            }
                        )
                    )

                tick_task = asyncio.create_task(
                    asyncio.sleep(_next_tick_delay(interval, bool(symbol_list)))
                )
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        if receive_task is not None and not receive_task.done():
            receive_task.cancel()
        if tick_task is not None and not tick_task.done():
            tick_task.cancel()
        if receive_task is not None:
            with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await receive_task
        if tick_task is not None:
            with suppress(asyncio.CancelledError):
                await tick_task
