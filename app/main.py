import asyncio
import json
import secrets
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import is_admin_key, is_valid_key
from .mt5_client import MT5Client
from .settings import load_settings


load_dotenv(dotenv_path=".env")
settings = load_settings()
mt5_client = MT5Client(settings)
_runtime_keys = set(settings.api_keys)


def _load_keys_from_file() -> None:
    if not settings.keys_file.exists():
        settings.keys_file.parent.mkdir(parents=True, exist_ok=True)
        settings.keys_file.write_text(json.dumps({"keys": sorted(_runtime_keys)}, indent=2))
        return
    try:
        data = json.loads(settings.keys_file.read_text())
        file_keys = {k.strip() for k in data.get("keys", []) if k.strip()}
        _runtime_keys.update(file_keys)
    except (OSError, json.JSONDecodeError):
        return


def _save_keys_to_file() -> None:
    settings.keys_file.parent.mkdir(parents=True, exist_ok=True)
    settings.keys_file.write_text(json.dumps({"keys": sorted(_runtime_keys)}, indent=2))

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


@app.post("/api/keys/generate")
def generate_key(x_admin_key: Optional[str] = Header(default=None)) -> JSONResponse:
    admin_key = settings.admin_key
    if not admin_key:
        return JSONResponse({"error": "admin_key_not_configured"}, status_code=500)
    if not is_admin_key(x_admin_key or "", admin_key):
        return JSONResponse({"error": "invalid_admin_key"}, status_code=401)
    new_key = secrets.token_urlsafe(24)
    _runtime_keys.add(new_key)
    _save_keys_to_file()
    return JSONResponse({"api_key": new_key})


def _parse_symbols(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


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


@app.websocket("/ws/market")
async def ws_market(
    websocket: WebSocket,
    symbols: Optional[str] = None,
    timeframe: Optional[str] = None,
    interval_ms: Optional[str] = None,
    key: Optional[str] = None,
) -> None:
    await websocket.accept()

    api_key = key or websocket.headers.get("x-api-key", "")
    if not is_valid_key(api_key, _runtime_keys):
        await websocket.send_text(json.dumps({"error": "invalid_api_key"}))
        await websocket.close(code=1008)
        return

    symbol_list = _parse_symbols(symbols)
    if not symbol_list:
        await websocket.send_text(json.dumps({"error": "symbols_required"}))
        await websocket.close(code=1003)
        return

    tf = timeframe or settings.default_timeframe
    interval = _parse_interval(interval_ms, settings.default_interval_ms)

    try:
        while True:
            payload = []
            for symbol in symbol_list:
                data = await asyncio.to_thread(mt5_client.fetch_market_data, symbol, tf)
                if data is not None:
                    payload.append(data)
                else:
                    payload.append({"symbol": symbol, "error": "symbol_unavailable"})

            await websocket.send_text(json.dumps({"data": payload, "timeframe": tf}))

            if interval > 0:
                await asyncio.sleep(interval / 1000.0)
            else:
                await asyncio.sleep(0)
    except WebSocketDisconnect:
        return
