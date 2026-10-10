# Nightwave Chat

**One Global Chat, real-time direct messages, and absolutely no signup forms.** Visitors choose a unique username and chat instantly. Midnight-black and electric-blue UI, responsive on mobile.

This is a complete **single-service full-stack website**: FastAPI serves the frontend and its API at the same HTTPS address, and WebSockets keep messages live. SQLite stores usernames, browser sessions, chat history and DM read markers.

## Launch it on GitHub + Render (no programming necessary)

**You need:** a [GitHub](https://github.com) account and a [Render](https://render.com) account. The default production blueprint uses a **paid** Render service with a persistent disk to avoid losing messages. As of October 2026, the Starter-equivalent web instance is listed at **$7/month**, plus **$0.25/month** for the 1 GB disk (taxes and additional usage excluded). Check [Render pricing](https://render.com/pricing) before approving.

1. **Unzip the Nightwave GitHub-ready ZIP on your computer.** Do **not** upload the ZIP itself to GitHub.
2. On GitHub, choose **New repository**, name it `nightwave-chat` (or any name), and create an empty repository. For the easiest upload, do not initialize it with a README.
3. On the new repository page, choose **uploading an existing file** (or **Add file → Upload files**). Drag in **all extracted contents**, including the hidden `.github` folder, `.gitignore`, and `render.yaml`. Keep `Dockerfile`, `render.yaml`, `server.py`, and `static/` in the **repository root**, not inside an extra `nightwave-chat/` folder. Commit the files.
4. In your [Render dashboard](https://dashboard.render.com/), select **New → Blueprint**. Connect GitHub if asked, pick the Nightwave repository, and choose **Apply/Deploy**. Render reads the root `render.yaml` and builds a web service plus persistent disk. Approve the displayed paid-resource charges.
5. When the deploy succeeds, open the **`https://…onrender.com` URL** on your Render service page. This is your working public website. Share it with friends. They only enter a username.

Render provisions HTTPS automatically, and new commits on the linked GitHub branch trigger redeployments. You can connect your own domain under the service's **Settings → Custom Domains**. GitHub Pages cannot host the WebSocket backend, so use Render rather than GitHub Pages.

**If you prefer the command line**, see [`GITHUB_DEPLOY.md`](GITHUB_DEPLOY.md) for Git commands and a short troubleshooting checklist.

### Production costs and boundaries

- **Hosting is not free in the provided deployment.** `render.yaml` intentionally selects the paid Starter plan and a 1 GB disk. Free web services cannot attach persistent disks and can lose sessions/messages on redeploy.
- The app runs as **one instance/one Uvicorn worker**, because SQLite storage and live WebSocket presence use single-process state. For much larger traffic, you'd want Postgres and Redis with multi-instance broadcasting.
- Messages are persisted on Render's disk. Render provides disk snapshots, but establish your own recovery/backups if message history is business-critical.
- A server restart briefly disconnects WebSockets, which reconnect automatically.
- Users do not create passwords or recover accounts. The username belongs to the browser holding the anonymous session cookie. If the cookie is deleted, that identity can't be restored through the UI.
- DMs are visible only to their participants through the API/WebSocket but are **not end-to-end encrypted**. The server administrator can access stored content.
- Before operating a large public anonymous chat, add moderation, spam controls, reporting/blocking, and an abuse response process. Anonymous public chat attracts bots, regardless of how tasteful the colors are.

## Features

- One public **Global Chat**, with instant updates for connected users
- Private, real-time **1:1 direct messages**
- Automatically restored usernames with a random HTTP-only session cookie; no email or login
- Message history saved in SQLite and pagination of older messages
- Online presence, typing indicator, unread DM counts, user search, username changes
- Responsive modern black / blue interface, emoji picker, safe plain-text message rendering
- Message and username validation, reserved names, session cookies, per-sender/IP rate limits
- GitHub Actions tests, production Docker image, Render Blueprint, and Docker Compose

## Run on your computer

Install Docker, then from the folder that contains `compose.yaml` run:

```bash
docker compose up --build -d
```

Open **http://localhost:8000**. To stop: `docker compose down`. Messages remain in the `nightwave_data` named Docker volume.

Without Docker (Python 3.10+):

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

## Test locally

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The tests cover anonymous session creation/restoration, duplicate names, Global chat, DM isolation/unread status, live WebSocket delivery to multiple clients, frontend HTTP assets, and persisted history after a **real server restart**. GitHub Actions runs these tests on each push.

## Configuration

| Environment variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` in Docker | HTTP and WebSocket listening port. Render supplies it. |
| `DATABASE_PATH` | `./data/nightwave.db` | SQLite file; **must be on persistent storage** in production. |
| `FORCE_SECURE_COOKIE` | `0` locally / `1` on Render | Set secure browser cookies for HTTPS. |
| `PUBLIC_ORIGIN` | unset | Optional exact allowed browser WebSocket origin, e.g. `https://chat.example.com`. |

The Render Blueprint sets `DATABASE_PATH` and `FORCE_SECURE_COOKIE` automatically. **No API keys, frontend URL, OAuth, CORS setup, or database provisioning step is required.**

## Source layout

```text
.
├── server.py                     FastAPI, WebSockets, SQLite, rate limits
├── static/
│   ├── index.html               Interface
│   ├── styles.css               Black-and-blue responsive design
│   ├── app.js                   Chat client, socket reconnects, messages
│   └── favicon.svg
├── tests/                       API + real-server/WebSocket integration tests
├── .github/workflows/tests.yml  Run tests automatically on GitHub
├── render.yaml                  One-service Render production deployment
├── Dockerfile                   Containerized web + API
├── docker-entrypoint.sh         Mounted disk permissions / non-root runtime
├── compose.yaml                 Local/VPS deployment with persistent volume
├── requirements.txt
├── requirements-dev.txt
├── GITHUB_DEPLOY.md             Deployment checklist
└── .gitignore                   Excludes cookies/database/secrets
```

## API at a glance

- `GET /` frontend website, `/assets/...` JavaScript/CSS, `/healthz` health probe
- `POST /api/join`, `GET /api/me`, `PATCH /api/me` anonymous identity
- `GET /api/users`, `GET /api/conversations` directory and DMs
- `GET /api/messages/global`, `GET /api/messages/dm/{peer_id}` histories
- `POST /api/messages`, `POST /api/messages/dm/{peer_id}/read` send/read
- `WS /ws` real-time messages, presence and typing

**Status:** Application code and live local tests are ready. A public deployment is created **only once you push these files to GitHub and authorize Render to host it.**
