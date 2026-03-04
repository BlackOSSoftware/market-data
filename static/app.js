let socket = null;
const lastPrices = {};
let activeSymbols = [];

const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const connectBtn = document.getElementById("connectBtn");
const disconnectBtn = document.getElementById("disconnectBtn");
const generateKeyBtn = document.getElementById("generateKeyBtn");
const subscribeBtn = document.getElementById("subscribeBtn");
const unsubscribeBtn = document.getElementById("unsubscribeBtn");
const replaceBtn = document.getElementById("replaceBtn");
const clearSymbolsBtn = document.getElementById("clearSymbolsBtn");
const dataBody = document.getElementById("dataBody");
const lastUpdate = document.getElementById("lastUpdate");
const symbolsInput = document.getElementById("symbols");
const intervalInput = document.getElementById("interval");
const manageSymbolsInput = document.getElementById("manageSymbols");
const activeSymbolsWrap = document.getElementById("activeSymbols");

function parseSymbols(raw) {
  const seen = new Set();
  const parsed = [];
  raw
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean)
    .forEach((symbol) => {
      if (!seen.has(symbol)) {
        seen.add(symbol);
        parsed.push(symbol);
      }
    });
  return parsed;
}

function setControlButtonsEnabled(connected) {
  subscribeBtn.disabled = !connected;
  unsubscribeBtn.disabled = !connected;
  replaceBtn.disabled = !connected;
  clearSymbolsBtn.disabled = !connected;
}

function setStatus(connected) {
  if (connected) {
    statusDot.classList.add("ok");
    statusText.textContent = "Connected";
    connectBtn.disabled = true;
    disconnectBtn.disabled = false;
  } else {
    statusDot.classList.remove("ok");
    statusText.textContent = "Disconnected";
    connectBtn.disabled = false;
    disconnectBtn.disabled = true;
  }
  setControlButtonsEnabled(connected);
}

function renderActiveSymbols() {
  activeSymbolsWrap.innerHTML = "";
  if (!activeSymbols.length) {
    const empty = document.createElement("span");
    empty.className = "chip chip-empty";
    empty.textContent = "No symbols subscribed";
    activeSymbolsWrap.appendChild(empty);
    return;
  }

  activeSymbols.forEach((symbol) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = symbol;
    activeSymbolsWrap.appendChild(chip);
  });
}

function formatTime(epoch) {
  if (!epoch) return "-";
  return new Date(epoch * 1000).toLocaleTimeString();
}

function formatPrice(value, precision) {
  if (value == null) return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  if (Number.isInteger(precision) && precision >= 0 && precision <= 12) {
    return num.toFixed(precision);
  }
  return String(num);
}

function renderRows(items) {
  dataBody.innerHTML = "";
  items.forEach((item) => {
    const row = document.createElement("tr");
    const status = item.error ? "Unavailable" : "OK";
    const statusClass = item.error ? "status-pill error" : "status-pill";
    const key = item.symbol || item.requested || "";
    const prev = lastPrices[key] || {};
    const bidClass =
      item.bid != null && prev.bid != null
        ? item.bid > prev.bid
          ? "price-up"
          : item.bid < prev.bid
          ? "price-down"
          : ""
        : "";
    const askClass =
      item.ask != null && prev.ask != null
        ? item.ask > prev.ask
          ? "price-up"
          : item.ask < prev.ask
          ? "price-down"
          : ""
        : "";

    if (key) {
      lastPrices[key] = { bid: item.bid, ask: item.ask };
    }

    row.innerHTML = `
      <td>${item.symbol || "-"}</td>
      <td class="${bidClass}">${formatPrice(item.bid, item.price_precision)}</td>
      <td class="${askClass}">${formatPrice(item.ask, item.price_precision)}</td>
      <td>${formatPrice(item.open, item.price_precision)}</td>
      <td>${formatPrice(item.high, item.price_precision)}</td>
      <td>${formatPrice(item.low, item.price_precision)}</td>
      <td>${formatPrice(item.close, item.price_precision)}</td>
      <td>${formatTime(item.time)}</td>
      <td><span class="${statusClass}">${status}</span></td>
    `;
    dataBody.appendChild(row);
  });
}

function applySubscriptionState(message) {
  if (Array.isArray(message.symbols)) {
    activeSymbols = message.symbols.map((s) => String(s).toUpperCase());
    symbolsInput.value = activeSymbols.join(",");
    renderActiveSymbols();
  }
  if (message.interval_ms != null) {
    intervalInput.value = String(message.interval_ms);
  }
}

function sendControl(action, extra = {}) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    alert("WebSocket is not connected.");
    return;
  }
  socket.send(JSON.stringify({ action, ...extra }));
}

function connect() {
  const serverUrl = document.getElementById("serverUrl").value.trim();
  const interval = intervalInput.value.trim();
  const apiKey = document.getElementById("apiKey").value.trim();
  const initialSymbols = parseSymbols(symbolsInput.value.trim());

  if (!serverUrl || !apiKey) {
    alert("Server URL and API key are required.");
    return;
  }

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.close();
  }

  const url = new URL(serverUrl);
  if (initialSymbols.length) {
    url.searchParams.set("symbols", initialSymbols.join(","));
  }
  if (interval) {
    url.searchParams.set("interval_ms", interval);
  }
  url.searchParams.set("key", apiKey);

  socket = new WebSocket(url.toString());

  socket.onopen = () => {
    setStatus(true);
  };

  socket.onclose = () => {
    setStatus(false);
  };

  socket.onerror = () => {
    setStatus(false);
  };

  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);

      if (
        message.type === "subscription_state" ||
        message.type === "subscription_updated" ||
        message.type === "interval_updated"
      ) {
        applySubscriptionState(message);
      }

      if (message.type === "control_error") {
        alert(message.message || message.error || "Invalid control message.");
      }

      if (Array.isArray(message.data)) {
        renderRows(message.data);
        lastUpdate.textContent = `Last update: ${new Date().toLocaleTimeString()}`;
      }
    } catch (err) {
      console.error("Invalid WebSocket message", err);
    }
  };
}

function disconnect() {
  if (socket) {
    socket.close();
    socket = null;
  }
}

connectBtn.addEventListener("click", connect);
disconnectBtn.addEventListener("click", disconnect);

subscribeBtn.addEventListener("click", () => {
  const symbols = parseSymbols(manageSymbolsInput.value.trim());
  if (!symbols.length) {
    alert("Enter symbols to subscribe.");
    return;
  }
  sendControl("subscribe", { symbols });
});

unsubscribeBtn.addEventListener("click", () => {
  const symbols = parseSymbols(manageSymbolsInput.value.trim());
  if (!symbols.length) {
    alert("Enter symbols to unsubscribe.");
    return;
  }
  sendControl("unsubscribe", { symbols });
});

replaceBtn.addEventListener("click", () => {
  const symbols = parseSymbols(manageSymbolsInput.value.trim());
  sendControl("set_symbols", { symbols });
});

clearSymbolsBtn.addEventListener("click", () => {
  sendControl("set_symbols", { symbols: [] });
});

generateKeyBtn.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/keys/request", { method: "POST" });
    const body = await res.json();
    if (!res.ok) {
      alert(body.error || "Failed to generate key.");
      return;
    }
    document.getElementById("apiKey").value = body.api_key;
    alert("New API key generated and filled.");
  } catch (err) {
    alert("Request failed. Check server.");
  }
});

setStatus(false);
renderActiveSymbols();
