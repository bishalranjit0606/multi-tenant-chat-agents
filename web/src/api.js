async function request(path, { method = "GET", token, body, signal } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  const raw = await response.text();
  let data = {};
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    data = { detail: raw };
  }
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" && detail.trim()
      ? detail.trim()
      : `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

// Hit the API host directly in dev so Vite does not buffer SSE into one blob.
const STREAM_BASE = import.meta.env.DEV ? "http://127.0.0.1:8000" : "";

function parseSseBlock(block) {
  const lines = block.split(/\r?\n/);
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  return JSON.parse(dataLines.join("\n"));
}

async function chatStream(token, slug, message, conversationId, { signal, onEvent } = {}) {
  const headers = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${STREAM_BASE}/shops/${slug}/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, conversationId }),
    signal,
  });
  if (!response.ok) {
    const raw = await response.text();
    let detail = raw;
    try {
      const data = raw ? JSON.parse(raw) : {};
      detail = typeof data.detail === "string" ? data.detail : raw;
    } catch {
      /* keep raw */
    }
    const error = new Error((detail || "").trim() || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  if (!response.body) {
    throw new Error("Streaming is not available in this browser.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final = { text: "", tools: [], citations: [], conversationId };
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\n\n/);
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const event = parseSseBlock(chunk.trim());
      if (!event) continue;
      if (event.type === "meta" && event.conversationId) {
        final.conversationId = event.conversationId;
      }
      if (event.type === "done") {
        final = {
          ...final,
          text: event.text || "",
          tools: event.tools || [],
          citations: event.citations || [],
        };
      }
      if (event.type === "error") {
        throw new Error(event.detail || "Chat failed.");
      }
      if (onEvent) onEvent(event);
    }
  }
  return final;
}

export const api = {
  login: (email, password, shop) => request("/login", {
    method: "POST",
    body: shop ? { email, password, shop } : { email, password },
  }),
  logout: (token) => request("/logout", { method: "POST", token }),
  conversations: (token) => request("/conversations", { token }),
  createConversation: (token, title) => request("/conversations", { method: "POST", token, body: { title } }),
  renameConversation: (token, id, title) => request(`/conversations/${id}`, { method: "PATCH", token, body: { title } }),
  deleteConversation: (token, id) => request(`/conversations/${id}`, { method: "DELETE", token }),
  chat: (token, slug, message, conversationId, signal) => request(`/shops/${slug}/chat`, {
    method: "POST",
    token,
    body: { message, conversationId },
    signal,
  }),
  chatStream,
  orders: (token) => request("/me/orders", { token }),
  bookings: (token) => request("/me/bookings", { token }),
  adminOrders: (token) => request("/admin/orders", { token }),
  adminBookings: (token) => request("/admin/bookings", { token }),
};
