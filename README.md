# multi-tenant-chat-agents

Himali Tea House (org_a, tea) takes tea orders. Lotus Wellness Studio (org_b, studio) books massage, physio, and yoga. The shops do not share rows. Prices are NPR. Studio times use Asia/Kathmandu.

The first prototype is `n8n-prototype.json`. The app to review is `shop/` and `web/`.

## Setup

Postgres is on port 5433.

```
docker compose up -d
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make seed
make api
```

In another terminal, start the page:

```
cd web
npm install && npm run dev
```

The API is http://127.0.0.1:8000. The page is http://127.0.0.1:5173.
Put your own keys in `.env`. Chat needs `GROQ_API_KEY`. Embeddings use `GEMINI_API_KEY` when set.
LangSmith tracing turns on when `LANGSMITH_API_KEY` is set (`LANGSMITH_TRACING=true`, project `LANGSMITH_PROJECT`).

Run tests and eval with:

```
make test
make eval
```

`make eval` is the same as `python -m eval.run_eval`. It uses a fake tool planner and checks Postgres after each case. It does not call Groq.

## How a request runs

1. User opens `/shops/himali-tea` or `/shops/lotus-studio`.
2. Login or signup creates a session for that shop only.
3. The page streams chat with `POST /shops/{slug}/chat/stream` and `Authorization: Bearer <token>` (JSON `POST /shops/{slug}/chat` still works).
4. If the token shop does not match the URL shop, the API returns 403.
5. LangGraph builds a ReAct agent for that shop with that shop's tools only.
6. Tools run rules in `shop/rules.py` and read or write Postgres. Writes need a yes (`confirm`).

There is no webhook in the running app. The n8n file was the early prototype.

## Memory and streaming

Each side-list chat is a thread (`conversationId` / `threadId`).
Postgres stores every user and assistant message for that thread, so chats survive API restarts and crashes.
When a new message runs, the API loads the last 12 turns from that thread as short-term context for the agent.
The page reads Server-Sent Events (`token`, `tool`, `citation`, `done`) so the reply appears as it is generated.

## Test logins

Dev password: `devpass`

- nima@himali.test, customer, tea
- admin@himali.test, admin, tea
- maya@lotus.test, customer, studio
- admin@lotus.test, admin, studio

Signup on the tea URL saves org_a. Signup on the studio URL saves org_b. Signup creates a customer, not an admin. The database stores a bcrypt hash, not the plain password.

Advance a tea order status (admin only):

```
make advance ORDER=ord_nima_last STATUS=confirmed
```

Or `POST /shops/himali-tea/orders/{orderId}/status` with `{"status":"shipped"}` and an admin Bearer token.

## How the shops stay apart

The shop comes from the URL. `/shops/himali-tea/chat` is tea. `/shops/lotus-studio/chat` is studio.
A tea token on the studio chat route gets 403. The page also keeps a tea login on the tea screen.
A shop id in the body or in a header does not change the session. The session row wins.
The database reads orders, bookings, and chats with that session's shop and user. A tea token on `GET /me/bookings` gets 403, so no studio rows come back.

## Knowledge (RAG)

Chunking is by document section. One knowledge row is one chunk. There is no fixed-size split and no chunk overlap.
Each shop has at least 15 FAQ Q&A rows, plus About / policy / brewing or service notes.
Search filters by `org_id` first, then ranks with pgvector, then returns top-3 (`limit=3`).
Citations show the document and the section.
Tests use a local hash embedder. Live embeds use Gemini (`gemini-embedding-001`) when `GEMINI_API_KEY` is set.

## Eval

`make eval` runs 12 tea cases and 12 studio cases (24 total). Latest run: **24 pass, 0 fail**.

Coverage includes knowledge citations, unanswered questions, confirm gates, stock limits, cancel rules, reorder, booking conflicts, opening hours, cross-org access, and prompt injection. Each case checks reply text and Postgres rows after the tools run.

Failures and fixes: none on the current suite. If a case fails after a rules change, keep the case and fix the rule or the fake planner in `eval/run_eval.py`.

## Chat model and booking lock

The chat model is Groq (`GROQ_CHAT_MODEL`, default `openai/gpt-oss-20b`). The agent is built with LangGraph `create_react_agent` only when a message runs.
Each agent run is tagged for LangSmith with the shop and conversation id when tracing is on.
Tea tools cover products and orders. Studio tools cover services, slots, and bookings.
The booking lock checks the slot, then writes it. A second write sees the taken slot and saves nothing.

## How this was built

Cursor wrote the code from step prompts. The order and booking rules were reviewed and left as they are.
The chat UI was shaped with the [UIZZE](https://uizze.sh/) `ui-taste` skill (anti-ui-slop playbooks and real product references), installed under `.agents/skills/ui-taste`.

## Page

The tea page is Himali Tea House, in a green tea colour, with the greeting "What tea shall we pack today?"
The studio page is Lotus Wellness Studio, in a blue colour, with the greeting "When would you like to come in?"
Each shop keeps its own colour, greeting, and layout cues so the two chats do not look like one generic template.
The side list can start, rename, and delete a chat.
A tool name shows when the API sends one. A citation shows the document and the section.
Stop aborts the current request. Confirm sends Yes when the reply asks for a yes.

Send the token as `Authorization: Bearer`.
