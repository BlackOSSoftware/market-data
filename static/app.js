let socket = null;
const lastPrices = {};

const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const connectBtn = document.getElementById("connectBtn");
const disconnectBtn = document.getElementById("disconnectBtn");
const generateKeyBtn = document.getElementById("generateKeyBtn");
const dataBody = document.getElementById("dataBody");
const lastUpdate = document.getElementById("lastUpdate");

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
}

function formatTime(epoch) {
  if (!epoch) return "—";
  const d = new Date(epoch * 1000);
  return d.toLocaleTimeString();
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
      <td>${item.symbol || "—"}</td>
      <td class="${bidClass}">${item.bid ?? "—"}</td>
      <td class="${askClass}">${item.ask ?? "—"}</td>
      <td>${item.open ?? "—"}</td>
      <td>${item.high ?? "—"}</td>
      <td>${item.low ?? "—"}</td>
      <td>${item.close ?? "—"}</td>
      <td>${formatTime(item.time)}</td>
      <td><span class="${statusClass}">${status}</span></td>
    `;
    dataBody.appendChild(row);
  });
}

function connect() {
  const serverUrl = document.getElementById("serverUrl").value.trim();
  const symbols = document.getElementById("symbols").value.trim();
  const interval = document.getElementById("interval").value.trim();
  const apiKey = document.getElementById("apiKey").value.trim();

  if (!serverUrl || !symbols || !apiKey) {
    alert("Server URL, Symbols, and API key are required.");
    return;
  }

  const url = new URL(serverUrl);
  url.searchParams.set("symbols", symbols);
  if (interval) url.searchParams.set("interval_ms", interval);
  url.searchParams.set("key", apiKey);

  socket = new WebSocket(url.toString());
  socket.onopen = () => setStatus(true);
  socket.onclose = () => setStatus(false);
  socket.onerror = () => setStatus(false);
  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.data) {
        renderRows(data.data);
        lastUpdate.textContent = `Last update: ${new Date().toLocaleTimeString()}`;
      }
    } catch (err) {
      console.error(err);
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
generateKeyBtn.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/keys/request", {
      method: "POST",
    });
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
