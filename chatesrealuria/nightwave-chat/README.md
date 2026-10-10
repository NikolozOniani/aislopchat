# Nightwave Chat

A deployable, real-time chat website with a modern midnight-blue UI. Everyone joins by choosing a unique username. No email, password, OAuth, or account-creation flow.

## Features

- One shared **Global Chat** with live updates
- **1-to-1 direct messages**, delivered only to the two participants' sessions
- **Persistent chat history** in SQLite and paginated older messages
- **Username-only joining**, with a secure random, HTTP-only browser-session cookie
- **Online indicators**, live presence, typing indicators, and DM unread counts
- User discovery, searchable usernames, rename support, emojis, responsive mobile layout
- Message-length limits, sender rate limiting, input validation, reserved names, and HTML-safe message rendering
- A single-process FastAPI + WebSockets backend, no paid third-party services required
- Docker, Docker Compose, and Render deployment configuration

## Run locally

Requires Python 3.10+ (Python 3.12 recommended).

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://localhost:8000**. Open another browser/incognito window with a different username to test real-time messaging.

For a production-like local instance:

```bash
docker compose up --build -d
```

Open **http://localhost:8000**. The named Docker volume `nightwave_data` persists messages and usernames across container restarts. Run `docker compose logs -f` to view server logs.

## Deploy to Render

1. Create a private or public Git repository with these files, then push it to GitHub.
2. In Render, select **New → Blueprint**, then connect the repository. It will read `render.yaml`.
3. The blueprint provisions one Docker web service and a persistent 1 GB disk on the **Starter** plan. Disks are not supported on every free tier.
4. Open the deployed HTTPS URL. Optionally set `PUBLIC_ORIGIN=https://your-exact-domain.com` in the service environment. Render supplies HTTPS; `FORCE_SECURE_COOKIE=1` is set in the blueprint.
5. If you add a custom domain, point DNS to the host and update `PUBLIC_ORIGIN` if configured. Verify Global chat and DMs using two browsers.

For VPS deployment, use `docker compose up --build -d` behind a reverse proxy that terminates HTTPS and supports **WebSocket upgrades** (`/ws`). For HTTPS, set `FORCE_SECURE_COOKIE=1` and optionally set `PUBLIC_ORIGIN=https://chat.example.com`.

### Environment settings

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_PATH` | `./data/nightwave.db` | SQLite file. Store it on a persistent disk/volume in production. |
| `PORT` | `8000` in Docker | The listening port used by the Docker start command. |
| `PUBLIC_ORIGIN` | unset | Optional exact allowed browser origin for WebSockets. Use an HTTPS origin, without a trailing slash. |
| `FORCE_SECURE_COOKIE` | `0` locally; `1` on Render | Require HTTPS for session cookies. Set to `1` when running behind a TLS proxy. |

**Important:** Use **one Uvicorn worker** and one running app instance. WebSocket connections and presence are held in memory and SQLite is optimized here for a single instance. For multi-server scaling, move presence/fanout to Redis and data to Postgres.

## How identity and privacy work

- First visit: choose a unique username. The server creates a random 256-bit session token and stores only its SHA-256 hash in SQLite. The raw token is kept in an HTTP-only, SameSite browser cookie that lasts up to one year.
- Returning visits: the cookie automatically restores the same username, with no login prompt.
- DMs: each read request is limited to messages between the current session's user and the requested peer; live messages are sent only to the two users' sockets.
- **There is no password-based identity proof or account recovery.** A username is associated with its original browser session. If the cookie is deleted or the browser profile is lost, that username cannot be reclaimed through the UI. A user who gets hold of the cookie can impersonate its owner.
- **DMs are not end-to-end encrypted.** The server/database operator can read stored messages. This is an access-controlled chat, not a secure messenger.
- For a large open public community, add human moderation, abuse reporting/blocking, more durable distributed rate limits, database backups, and an account-recovery option before inviting large numbers of strangers.

## API / architecture

- `GET /api/me` and `POST /api/join`: restore/create an identity
- `PATCH /api/me`: rename the current identity
- `GET /api/users?query=` and `GET /api/conversations`: directory and DM list
- `GET /api/messages/global` and `GET /api/messages/dm/{peer_id}`: paginated history, `?before=<message_id>`
- `POST /api/messages`: write a Global or DM message; the server broadcasts it over WebSockets
- `POST /api/messages/dm/{peer_id}/read`: update unread state
- `WS /ws`: real-time messages, online presence, typing events, and username changes
- `GET /healthz`: deployment health check

Messages are saved to SQLite **before** their live broadcast. WebSocket reconnects automatically if the connection drops.

## Tests

Install the optional test dependency and run the unit/integration tests:

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

These tests cover sessions, Global chat, DM history isolation, unread/read markers, renaming, reserved usernames, duplicate names, and unauthorized API requests. The real WebSocket fanout was also tested with multiple simultaneous clients.

## Project structure

```text
server.py            FastAPI backend, SQLite tables, and WebSocket hub
static/index.html    App layout and entry modal
static/styles.css    Responsive black-and-blue theme
static/app.js        Chat UI, API calls, live events, navigation
Dockerfile           Standalone production container
compose.yaml         Local/VPS deployment with persistent storage
render.yaml          Render blueprint
requirements.txt     Runtime Python packages
requirements-dev.txt Test packages
```

Nightwave is a deployable MVP. Hosting, a domain name, and HTTPS are supplied by your deployment provider, not by the project archive.
