# MT5 WebSocket API Guide (A to Z)

This guide explains complete usage of the WebSocket market data API.
It covers connection, subscribe/unsubscribe, control messages, data format, and troubleshooting.

## 1) Endpoint

WebSocket endpoint:

```text
ws://<server-ip>:8000/ws/market
```

Example:

```text
ws://127.0.0.1:8000/ws/market
```

## 2) Query Parameters

You can pass these query params while connecting:

- `symbols` (optional): comma-separated symbols (example: `EURUSD,GBPUSD`)
- `interval_ms` (optional): update interval in milliseconds (example: `100`)
- `key` (required if not using header): API key

Auth can be sent in either one:

- Query param: `key=...`
- Header: `x-api-key: ...`

If key is invalid/missing, server sends:

```json
{"error":"invalid_api_key"}
```

and closes the socket.

## 3) Quick Start (No Initial Symbols)

Connect without symbols:

```text
ws://127.0.0.1:8000/ws/market?interval_ms=100&key=YOUR_API_KEY
```

After connect, send:

```json
{ "action": "subscribe", "symbols": ["EURUSD", "GBPUSD"] }
```

## 4) Message Types Sent By Client

### 4.1 Subscribe

Add symbols to current subscription list:

```json
{ "action": "subscribe", "symbols": ["EURUSD", "XAUUSD"] }
```

### 4.2 Unsubscribe

Remove symbols from current subscription list:

```json
{ "action": "unsubscribe", "symbols": ["EURUSD"] }
```

### 4.3 Replace Full Symbol List

Replace current list fully:

```json
{ "action": "set_symbols", "symbols": ["GBPUSD", "USDJPY"] }
```

Clear all symbols:

```json
{ "action": "set_symbols", "symbols": [] }
```

### 4.4 Change Interval

Change push frequency without reconnecting:

```json
{ "action": "set_interval", "interval_ms": 250 }
```

### 4.5 Get Current State

Get current symbols and interval:

```json
{ "action": "get_state" }
```

### 4.6 Ping / Heartbeat

```json
{ "action": "ping" }
```

or

```json
{ "action": "heartbeat" }
```

## 5) Message Types Sent By Server

### 5.1 Initial / Current State

```json
{
  "type": "subscription_state",
  "symbols": ["EURUSD", "GBPUSD"],
  "interval_ms": 100
}
```

### 5.2 Subscription Updated

```json
{
  "type": "subscription_updated",
  "action": "unsubscribe",
  "added": [],
  "removed": ["EURUSD"],
  "symbols": ["GBPUSD"],
  "interval_ms": 100
}
```

### 5.3 Interval Updated

```json
{
  "type": "interval_updated",
  "symbols": ["GBPUSD"],
  "interval_ms": 250
}
```

### 5.4 Market Data

```json
{
  "type": "market_data",
  "symbols": ["GBPUSD"],
  "data": [
    {
      "symbol": "GBPUSD.pr",
      "requested": "GBPUSD",
      "time": 1772583036,
      "price_precision": 5,
      "tick_size": 0.00001,
      "point": 0.00001,
      "bid": 1.33498,
      "ask": 1.33667,
      "last": 0.0,
      "open": 1.33516,
      "high": 1.33516,
      "low": 1.33498,
      "close": 1.33498,
      "volume": 0.0
    }
  ]
}
```

### 5.5 Control Error

```json
{
  "type": "control_error",
  "error": "invalid_json",
  "message": "Send JSON control messages."
}
```

### 5.6 Pong

```json
{ "type": "pong" }
```

## 6) Data Field Meaning

Per item in `market_data.data`:

- `symbol`: broker-side resolved symbol name
- `requested`: symbol you requested
- `time`: tick time (Unix epoch seconds)
- `price_precision`: broker digits/precision
- `tick_size`: minimum price step
- `point`: MT5 point value
- `bid`, `ask`, `last`, `open`, `high`, `low`, `close`: normalized prices
- `volume`: candle volume (if available)

If symbol cannot be fetched:

```json
{ "symbol": "ABC", "error": "symbol_unavailable" }
```

## 7) Full Example Flow

1. Connect:

```text
ws://127.0.0.1:8000/ws/market?interval_ms=100&key=YOUR_API_KEY
```

2. Receive:

```json
{"type":"subscription_state","symbols":[],"interval_ms":100}
```

3. Send subscribe:

```json
{"action":"subscribe","symbols":["EURUSD","GBPUSD"]}
```

4. Receive update:

```json
{"type":"subscription_updated","action":"subscribe","added":["EURUSD","GBPUSD"],"removed":[],"symbols":["EURUSD","GBPUSD"],"interval_ms":100}
```

5. Receive streaming `market_data` repeatedly.

6. Send unsubscribe:

```json
{"action":"unsubscribe","symbols":["EURUSD"]}
```

7. Stream continues with only remaining symbols.

## 8) JavaScript Client Example

```javascript
const url = "ws://127.0.0.1:8000/ws/market?interval_ms=100&key=YOUR_API_KEY";
const ws = new WebSocket(url);

ws.onopen = () => {
  ws.send(JSON.stringify({ action: "subscribe", symbols: ["EURUSD", "GBPUSD"] }));
};

ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  console.log(msg);
};

// Example: later unsubscribe one symbol
setTimeout(() => {
  ws.send(JSON.stringify({ action: "unsubscribe", symbols: ["EURUSD"] }));
}, 5000);
```

## 9) Python Client Example

```python
import asyncio
import json
import websockets

URL = "ws://127.0.0.1:8000/ws/market?interval_ms=100&key=YOUR_API_KEY"

async def main():
    async with websockets.connect(URL) as ws:
        print(await ws.recv())  # subscription_state
        await ws.send(json.dumps({"action": "subscribe", "symbols": ["EURUSD", "GBPUSD"]}))
        for _ in range(5):
            print(await ws.recv())
        await ws.send(json.dumps({"action": "unsubscribe", "symbols": ["EURUSD"]}))
        print(await ws.recv())  # subscription_updated
        print(await ws.recv())  # market_data with remaining symbols

asyncio.run(main())
```

## 10) Common Mistakes

- Invalid JSON:
  - Wrong: `{ "action": "unsubscribe", "symbols": ["EURUSD] }`
  - Correct: `{ "action": "unsubscribe", "symbols": ["EURUSD"] }`
- Sending plain text instead of JSON object.
- Forgetting API key (`key` query or `x-api-key` header).
- Not using symbol array for `subscribe`/`unsubscribe`.

## 11) Notes

- You can connect with no symbols and subscribe later.
- `interval_ms=0` means fastest loop possible (depends on platform limits).
- You do not need reconnect for symbol changes.
- Price precision/tick-size metadata is cached server-side for speed.

