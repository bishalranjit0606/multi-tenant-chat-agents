import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { api } from "./api";

const SHOPS = {
  tea: {
    key: "tea",
    slug: "himali-tea",
    orgId: "org_a",
    path: "/tea",
    name: "Himali Tea House",
    greeting: "What tea shall we pack today?",
    listLabel: "My orders",
    emptyList: "No orders yet.",
  },
  studio: {
    key: "studio",
    slug: "lotus-studio",
    orgId: "org_b",
    path: "/studio",
    name: "Lotus Wellness Studio",
    greeting: "When would you like to come in?",
    listLabel: "My bookings",
    emptyList: "No bookings yet.",
  },
};

function shopFromPath(path) {
  if (path.startsWith("/studio")) return SHOPS.studio;
  if (path.startsWith("/tea")) return SHOPS.tea;
  return null;
}

function tokenKey(shop) {
  return `shop-token:${shop.key}`;
}

function roleKey(shop) {
  return `shop-role:${shop.key}`;
}

function defaultEmail(shop) {
  return shop.key === "tea" ? "bishal@tea.com" : "bishal@studio.com";
}

function asksForYes(text) {
  return /\byes\b/i.test(text || "");
}

// Fast human typing pace: ~2 chars / 28ms ≈ 70 characters per second.
const TYPE_CHARS = 2;
const TYPE_MS = 28;

function waitMs(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function Icon({ name }) {
  const paths = {
    arrow: (
      <>
        <path d="M19 12H5" />
        <path d="M11 6 5 12l6 6" />
      </>
    ),
    logout: (
      <>
        <path d="M9 6H5v12h4" />
        <path d="M10 12h9" />
        <path d="M16 8l4 4-4 4" />
      </>
    ),
    chat: <path d="M5 6h14v9H8l-3 3z" />,
    plus: (
      <>
        <path d="M12 5v14" />
        <path d="M5 12h14" />
      </>
    ),
    trash: (
      <>
        <path d="M4 7h16" />
        <path d="M9 7V5h6v2" />
        <path d="M8 7l1 12h6l1-12" />
      </>
    ),
    send: (
      <>
        <path d="M4 12 20 4l-6 16-2-6z" />
        <path d="M12 14l8-10" />
      </>
    ),
  };
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

function when(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kathmandu",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function App() {
  const [path, setPath] = useState(window.location.pathname);

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function go(next) {
    window.history.pushState({}, "", next);
    setPath(next);
  }

  const shop = shopFromPath(path);
  if (!shop) return <Gate onOpen={go} />;
  return <ShopScreen shop={shop} onHome={() => go("/")} />;
}

function Gate({ onOpen }) {
  return (
    <main className="gate">
      <a className="door door-tea" href="/tea" onClick={(event) => { event.preventDefault(); onOpen("/tea"); }}>
        <span>Tea</span>
        <strong>Himali Tea House</strong>
        <em>What tea shall we pack today?</em>
        <span className="door-button">Enter</span>
      </a>
      <a className="door door-studio" href="/studio" onClick={(event) => { event.preventDefault(); onOpen("/studio"); }}>
        <span>Studio</span>
        <strong>Lotus Wellness Studio</strong>
        <em>When would you like to come in?</em>
        <span className="door-button">Enter</span>
      </a>
    </main>
  );
}

function ShopScreen({ shop, onHome }) {
  const [token, setToken] = useState(() => sessionStorage.getItem(tokenKey(shop)));
  const [role, setRole] = useState(() => sessionStorage.getItem(roleKey(shop)) || "");
  const [email, setEmail] = useState(() => defaultEmail(shop));
  const [password, setPassword] = useState("devpass");
  const [chats, setChats] = useState([]);
  const [activeId, setActiveId] = useState("");
  const [mine, setMine] = useState([]);
  const [adminRows, setAdminRows] = useState([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const stopRef = useRef(null);

  const active = chats.find((chat) => chat.id === activeId) || null;
  const lastReply = [...(active?.messages || [])].reverse().find((row) => row.role === "assistant");
  const needsYes = asksForYes(lastReply?.text);
  const isAdmin = role === "admin";

  async function load(currentToken, currentRole = role) {
    setLoading(true);
    setError("");
    try {
      if (currentRole === "admin") {
        const data = shop.key === "tea"
          ? await api.adminOrders(currentToken)
          : await api.adminBookings(currentToken);
        setAdminRows(shop.key === "tea" ? data.orders || [] : data.bookings || []);
        setChats([]);
        setMine([]);
        setActiveId("");
        return;
      }
      const [chatData, sideData] = await Promise.all([
        api.conversations(currentToken),
        shop.key === "tea" ? api.orders(currentToken) : api.bookings(currentToken),
      ]);
      const rows = chatData.conversations || [];
      setChats(rows);
      setActiveId((current) => current || rows[0]?.id || "");
      setMine(shop.key === "tea" ? sideData.orders || [] : sideData.bookings || []);
      setAdminRows([]);
    } catch (err) {
      setError(err.message || "Could not load this shop.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setEmail(defaultEmail(shop));
    setPassword("devpass");
  }, [shop.key]);

  useEffect(() => {
    if (token) load(token, role);
  }, [token, shop.key, role]);

  async function onLogin(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const logged = await api.login(email, password, shop.key);
      if (logged.orgId !== shop.orgId) {
        await api.logout(logged.token);
        setError("This login is for the other shop.");
        return;
      }
      const nextRole = logged.role || "customer";
      sessionStorage.setItem(tokenKey(shop), logged.token);
      sessionStorage.setItem(roleKey(shop), nextRole);
      setRole(nextRole);
      setToken(logged.token);
    } catch (err) {
      setError(err.message || "Login failed.");
    } finally {
      setLoading(false);
    }
  }

  async function onLogout() {
    const current = token;
    sessionStorage.removeItem(tokenKey(shop));
    sessionStorage.removeItem(roleKey(shop));
    setToken("");
    setRole("");
    setChats([]);
    setMine([]);
    setAdminRows([]);
    setActiveId("");
    if (current) await api.logout(current).catch(() => {});
  }

  async function startChat() {
    setError("");
    try {
      const made = await api.createConversation(token, "New chat");
      setChats((rows) => [...rows, made]);
      setActiveId(made.id);
    } catch (err) {
      setError(err.message || "Could not start a chat.");
    }
  }

  async function renameChat(chat, title) {
    const next = title.trim();
    if (!next || next === chat.title) return;
    try {
      await api.renameConversation(token, chat.id, next);
      setChats((rows) => rows.map((row) => (row.id === chat.id ? { ...row, title: next } : row)));
    } catch (err) {
      setError(err.message || "Could not rename that chat.");
    }
  }

  async function deleteChat(chat) {
    try {
      await api.deleteConversation(token, chat.id);
      const rest = chats.filter((row) => row.id !== chat.id);
      setChats(rest);
      if (activeId === chat.id) setActiveId(rest[0]?.id || "");
    } catch (err) {
      setError(err.message || "Could not delete that chat.");
    }
  }

  function stop() {
    stopRef.current?.abort();
  }

  async function send(override) {
    const fromDraft = typeof override !== "string";
    const message = (fromDraft ? draft : override).trim();
    if (!message || sending) return;
    const controller = new AbortController();
    stopRef.current = controller;
    setSending(true);
    setError("");
    let conversationId = activeId;
    try {
      if (!conversationId) {
        const made = await api.createConversation(token, message.slice(0, 42));
        conversationId = made.id;
        setChats((rows) => [...rows, made]);
        setActiveId(made.id);
      }
      if (fromDraft) setDraft("");
      const userMsg = { role: "user", text: message, tools: [], citations: [] };
      const assistantMsg = { role: "assistant", text: "", tools: [], citations: [] };
      setChats((rows) => rows.map((row) => {
        if (row.id !== conversationId) return row;
        return { ...row, messages: [...row.messages, userMsg, assistantMsg] };
      }));

      let pendingText = "";
      let typing = false;
      let typeWaiters = [];

      function appendAssistantText(slice) {
        flushSync(() => {
          setChats((rows) => rows.map((row) => {
            if (row.id !== conversationId) return row;
            const messages = row.messages.slice();
            const last = messages[messages.length - 1];
            if (!last || last.role !== "assistant") return row;
            messages[messages.length - 1] = { ...last, text: `${last.text || ""}${slice}` };
            return { ...row, messages };
          }));
        });
      }

      async function pumpTyping() {
        if (typing) return;
        typing = true;
        try {
          while (pendingText.length) {
            if (controller.signal.aborted) {
              throw new DOMException("Aborted", "AbortError");
            }
            const slice = pendingText.slice(0, TYPE_CHARS);
            pendingText = pendingText.slice(TYPE_CHARS);
            appendAssistantText(slice);
            if (pendingText.length) {
              await waitMs(TYPE_MS, controller.signal);
            }
          }
        } finally {
          typing = false;
          const waiters = typeWaiters;
          typeWaiters = [];
          waiters.forEach((resolve) => resolve());
        }
      }

      function queueType(text) {
        if (!text) return Promise.resolve();
        pendingText += text;
        const ready = new Promise((resolve) => {
          typeWaiters.push(resolve);
        });
        void pumpTyping();
        return ready;
      }

      const reply = await api.chatStream(token, shop.slug, message, conversationId, {
        signal: controller.signal,
        onEvent(event) {
          if (event.type === "meta" && event.conversationId && event.conversationId !== conversationId) {
            conversationId = event.conversationId;
            setActiveId(conversationId);
          }
          if (event.type === "token" && event.text) {
            void queueType(event.text);
          }
          if (event.type === "tool" && event.name) {
            flushSync(() => {
              setChats((rows) => rows.map((row) => {
                if (row.id !== conversationId) return row;
                const messages = row.messages.slice();
                const last = messages[messages.length - 1];
                if (!last || last.role !== "assistant") return row;
                const tools = last.tools.includes(event.name) ? last.tools : [...last.tools, event.name];
                messages[messages.length - 1] = { ...last, tools };
                return { ...row, messages };
              }));
            });
          }
          if (event.type === "citation" && event.document && event.section) {
            flushSync(() => {
              setChats((rows) => rows.map((row) => {
                if (row.id !== conversationId) return row;
                const messages = row.messages.slice();
                const last = messages[messages.length - 1];
                if (!last || last.role !== "assistant") return row;
                const key = `${event.document}|${event.section}`;
                const exists = (last.citations || []).some(
                  (cite) => `${cite.document}|${cite.section}` === key,
                );
                if (exists) return row;
                messages[messages.length - 1] = {
                  ...last,
                  citations: [...(last.citations || []), { document: event.document, section: event.section }],
                };
                return { ...row, messages };
              }));
            });
          }
        },
      });
      while (typing || pendingText.length) {
        await waitMs(TYPE_MS, controller.signal);
      }
      setChats((rows) => rows.map((row) => {
        if (row.id !== conversationId) return row;
        const messages = row.messages.slice();
        const last = messages[messages.length - 1];
        if (!last || last.role !== "assistant") return row;
        messages[messages.length - 1] = {
          role: "assistant",
          text: last.text || reply.text || "",
          tools: reply.tools?.length ? reply.tools : last.tools,
          citations: reply.citations?.length ? reply.citations : last.citations,
        };
        return { ...row, messages };
      }));
    } catch (err) {
      if (err.name === "AbortError") return;
      setError(err.message || "The message did not send.");
      if (conversationId) {
        setChats((rows) => rows.map((row) => {
          if (row.id !== conversationId) return row;
          const messages = row.messages.slice();
          const last = messages[messages.length - 1];
          if (last?.role === "assistant" && !(last.text || "").trim()) {
            messages.pop();
          }
          return { ...row, messages };
        }));
      }
    } finally {
      if (stopRef.current === controller) stopRef.current = null;
      setSending(false);
    }
  }

  function onKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  }

  if (!token) {
    return (
      <main className={`shop shop-${shop.key} login-page`} data-shop={shop.key}>
        <button type="button" className="text-button home-link" onClick={onHome}><Icon name="arrow" />Both shops</button>
        <form className="login" onSubmit={onLogin}>
          <h1>{shop.name}</h1>
          <p>{shop.greeting}</p>
          <label>
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </label>
          {error ? <p className="error">{error}</p> : null}
          <button type="submit" className="send" disabled={loading}>{loading ? "Loading..." : "Log in"}</button>
        </form>
      </main>
    );
  }

  if (isAdmin) {
    return (
      <main className={`shop shop-${shop.key}`} data-shop={shop.key}>
        <header className="top">
          <button type="button" className="text-button" onClick={onHome}><Icon name="arrow" />Both shops</button>
          <h1>{shop.name}</h1>
          <p>Admin desk. No chat. Shop activity only.</p>
          <button type="button" className="text-button" onClick={onLogout}><Icon name="logout" />Log out</button>
        </header>
        <div className="band" />
        {error ? (
          <p className="error">
            {error} <button type="button" onClick={() => load(token, role)}>Try again</button>
          </p>
        ) : null}
        {loading ? <p className="status">Loading...</p> : null}
        <section className="admin-desk">
          <h2>{shop.key === "tea" ? "All orders" : "All bookings"}</h2>
          {adminRows.length === 0 && !loading ? <p className="empty">No rows yet.</p> : null}
          {shop.key === "tea" ? (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Order</th>
                  <th>Status</th>
                  <th>Items</th>
                  <th>Total</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {adminRows.map((order) => (
                  <tr key={order.id}>
                    <td>{order.customerName}</td>
                    <td>{order.id}</td>
                    <td>{order.status}</td>
                    <td>{(order.items || []).map((item) => `${item.qty}× ${item.name || item.sku}`).join(", ")}</td>
                    <td>NPR {order.total}</td>
                    <td>{when(order.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Service</th>
                  <th>Practitioner</th>
                  <th>Status</th>
                  <th>Start</th>
                  <th>End</th>
                  <th>Price</th>
                </tr>
              </thead>
              <tbody>
                {adminRows.map((booking) => (
                  <tr key={booking.id}>
                    <td>{booking.customerName}</td>
                    <td>{booking.service || booking.id}</td>
                    <td>{booking.practitioner || "—"}</td>
                    <td>{booking.status}</td>
                    <td>{when(booking.start)}</td>
                    <td>{when(booking.end)}</td>
                    <td>NPR {booking.price}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className={`shop shop-${shop.key}`} data-shop={shop.key}>
      <header className="top">
        <button type="button" className="text-button" onClick={onHome}><Icon name="arrow" />Both shops</button>
        <h1>{shop.name}</h1>
        <p>{shop.greeting}</p>
        <button type="button" className="text-button" onClick={onLogout}><Icon name="logout" />Log out</button>
      </header>
      <div className="band" />
      {error ? (
        <p className="error">
          {error} <button type="button" onClick={() => load(token, role)}>Try again</button>
        </p>
      ) : null}
      {loading ? <p className="status">Loading...</p> : null}
      <div className="layout">
        <aside className="chats">
          <div className="row">
            <h2><Icon name="chat" />Chats</h2>
            <button type="button" onClick={startChat}><Icon name="plus" />New chat</button>
          </div>
          {chats.length === 0 && !loading ? <p className="empty">No chats yet.</p> : null}
          <ul>
            {chats.map((chat) => (
              <li key={chat.id} className={chat.id === activeId ? "active" : ""}>
                <button type="button" className="pick" onClick={() => setActiveId(chat.id)}>{chat.title}</button>
                <input
                  aria-label={`Rename ${chat.title}`}
                  defaultValue={chat.title}
                  onBlur={(event) => renameChat(chat, event.target.value)}
                />
                <button type="button" onClick={() => deleteChat(chat)}><Icon name="trash" />Delete</button>
              </li>
            ))}
          </ul>
        </aside>
        <section className="thread">
          <div className="messages">
            {!active && !loading ? <p className="empty">{shop.greeting}</p> : null}
            {active && active.messages.length === 0 ? <p className="empty">{shop.greeting}</p> : null}
            {active?.messages.map((message, index) => (
              <article key={`${active.id}-${index}`} className={`bubble ${message.role}`}>
                <p>{message.text}</p>
                {(message.tools || []).map((tool) => <span key={tool} className="tool">{tool}</span>)}
                {(message.citations || []).map((cite) => (
                  <span key={`${cite.document}-${cite.section}`} className="cite">{cite.document} · {cite.section}</span>
                ))}
              </article>
            ))}
          </div>
          <div className="composer">
            <textarea
              value={draft}
              placeholder="Write a message"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onKeyDown}
            />
            <div className="send-row">
              <button type="button" className="send" onClick={() => send()} disabled={sending}><Icon name="send" />{sending ? "Sending..." : "Send"}</button>
              {sending ? <button type="button" className="stop" onClick={stop}>Stop</button> : null}
              {needsYes ? <button type="button" className="confirm" onClick={() => send("Yes")} disabled={sending}>Confirm</button> : null}
            </div>
          </div>
        </section>
        <aside className="mine">
          <h2>{shop.listLabel}</h2>
          {mine.length === 0 && !loading ? <p className="empty">{shop.emptyList}</p> : null}
          <ul>
            {shop.key === "tea" ? mine.map((order) => (
              <li key={order.id}>
                <strong>{order.id}</strong>
                <span>{order.status}</span>
                <span>NPR {order.total}</span>
              </li>
            )) : mine.map((booking) => (
              <li key={booking.id}>
                <strong>{booking.service || booking.id}</strong>
                <span>{booking.status}</span>
                <span>{when(booking.start)}</span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </main>
  );
}
