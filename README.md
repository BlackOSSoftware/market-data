# MT5 Market Data WebSocket API

## Setup (Windows VPS)
1. MetaTrader 5 terminal install karo aur login verified rakho.
2. Is folder me `.env` banao aur `.env.example` se values fill karo.
3. Python deps install karo.

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

4. Server run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## WebSocket Usage
Endpoint:
`ws://<server-ip>:8000/ws/market?symbols=EURUSD,GBPUSD&interval_ms=100&key=YOUR_KEY`

Headers (optional):
`x-api-key: YOUR_KEY`

Response example:
```json
{
  "type": "market_data",
  "symbols": ["EURUSD"],
  "data": [
    {
      "symbol": "EURUSD",
      "time": 1710000000,
      "price_precision": 5,
      "tick_size": 0.00001,
      "point": 0.00001,
      "bid": 1.0842,
      "ask": 1.0844,
      "last": 1.0843,
      "open": 1.0838,
      "high": 1.0846,
      "low": 1.0831,
      "close": 1.0842,
      "volume": 120.0
    }
  ]
}
```

### Live Subscribe / Unsubscribe (same connection)
WebSocket connect hone ke baad control messages bhejo:

```json
{ "action": "subscribe", "symbols": ["USDJPY", "XAUUSD"] }
```

```json
{ "action": "unsubscribe", "symbols": ["GBPUSD"] }
```

```json
{ "action": "set_symbols", "symbols": ["EURUSD", "USDJPY"] }
```

```json
{ "action": "set_interval", "interval_ms": 500 }
```

```json
{ "action": "get_state" }
```

Server updates:
- `subscription_state` (initial/current symbols + interval)
- `subscription_updated` (added/removed symbols)
- `interval_updated`
- `control_error` (invalid action/message)

## Historical Candles (REST)
Endpoint:
`http://<server-ip>:8000/api/history?symbol=EURUSD&resolution=15&count=500&key=YOUR_KEY`

Response example:
```json
[
  { "time": 1710000000, "open": 1.0842, "high": 1.0850, "low": 1.0831, "close": 1.0846, "volume": 120.0 }
]
```

## Notes
- `interval_ms=0` pe loop without delay chalega, lekin OS + MT5 limits ke wajah se "0ms" guarantee nahi hota.
- Price values broker ke `digits/tick_size` ke basis par normalize hote hain; long float artifacts avoid kiye gaye hain.
- `price_precision`, `tick_size`, `point` symbol metadata cache hota hai (har tick par dobara fetch nahi hota), isliye stream fast rehti hai.
- API keys `.env` me `API_KEYS=key1,key2` format me rakho.
- Agar `REDIS_URL` set hai to API keys Redis me store hongi (`REDIS_KEYS_SET` se set name change kar sakte ho). File-based `API_KEYS_FILE` tab ignore hoga.
- MT5 ke liye `MT5_LOGIN/MT5_PASSWORD` optional hain. Agar terminal pe account already logged-in hai, app bina ID/password ke bhi connect karega.

## Built-in UI
Browser me open karo:
`http://<server-ip>:8000/`

## Request Secret Key (Public)
Request:
```bash
curl -X POST http://<server-ip>:8000/api/keys/request
```

Response:
```json
{ "api_key": "generated_key_here" }
```

Generated keys `API_KEYS_FILE` me save ho jati hain.

## API Key Generate (Admin)
Admin header required:
`x-admin-key: <ADMIN_KEY>`

Request:
```bash
curl -X POST http://<server-ip>:8000/api/keys/generate -H "x-admin-key: <ADMIN_KEY>"
```

Response:
```json
{ "api_key": "generated_key_here" }
```

Generated keys `API_KEYS_FILE` me save ho jati hain.
