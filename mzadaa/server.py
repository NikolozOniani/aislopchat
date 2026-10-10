"""Nightwave: username-only, cookie-session real-time chat on SQLite."""
import asyncio
import hashlib
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv('DATABASE_PATH', str(ROOT / 'data' / 'nightwave.db')))
COOKIE = 'nightwave_session'
MAX_AGE = 60 * 60 * 24 * 365
NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]{2,19}$')
RESERVED = {'admin', 'administrator', 'system', 'support', 'moderator', 'mod', 'nightwave', 'official'}
PUBLIC_ORIGIN = os.getenv('PUBLIC_ORIGIN', '').rstrip('/')

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(str(DB_PATH), check_same_thread=False, isolation_level=None)
db.row_factory = sqlite3.Row
db_lock = threading.RLock()
with db_lock:
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=5000')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
          created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL CHECK(kind IN ('global', 'dm')),
          sender_id TEXT NOT NULL REFERENCES users(id),
          recipient_id TEXT REFERENCES users(id),
          body TEXT NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_messages_global ON messages(kind, id);
        CREATE INDEX IF NOT EXISTS ix_messages_dm_from ON messages(sender_id, recipient_id, id);
        CREATE INDEX IF NOT EXISTS ix_messages_dm_to ON messages(recipient_id, sender_id, id);
        CREATE TABLE IF NOT EXISTS dm_reads (
          viewer_id TEXT NOT NULL REFERENCES users(id),
          peer_id TEXT NOT NULL REFERENCES users(id),
          last_read_id INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(viewer_id, peer_id)
        );
    ''')


def now():
    return int(time.time() * 1000)


def hash_token(raw):
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


def user_from_token(raw):
    if not raw or len(raw) != 64:
        return None
    try:
        token_hash = hash_token(raw)
    except Exception:
        return None
    with db_lock:
        row = db.execute('''
            SELECT u.id, u.username, u.created_at FROM sessions s
            JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?''', (token_hash, now())).fetchone()
    return dict(row) if row else None


def current_user(request: Request):
    user = user_from_token(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail='Choose a username to join.')
    return user


def validate_name(value):
    value = value.strip()
    if not NAME_RE.fullmatch(value):
        raise HTTPException(status_code=422, detail='Username must be 3–20 characters, start with a letter, and use only letters, numbers or _.')
    if value.lower() in RESERVED:
        raise HTTPException(status_code=422, detail='That username is reserved. Pick another.')
    return value


class JoinBody(BaseModel):
    username: str = Field(min_length=1, max_length=60)


class SendBody(BaseModel):
    kind: Literal['global', 'dm']
    recipient_id: str | None = None
    body: str = Field(min_length=1, max_length=1500)


class Hub:
    def __init__(self):
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()

    async def join(self, user_id, ws):
        async with self.lock:
            is_new = not self.connections.get(user_id)
            self.connections[user_id].add(ws)
            online = list(self.connections)
        return is_new, online

    async def leave(self, user_id, ws):
        async with self.lock:
            self.connections[user_id].discard(ws)
            if not self.connections[user_id]:
                del self.connections[user_id]
                return True
        return False

    async def send_to(self, user_ids, payload):
        async with self.lock:
            sockets = [ws for uid in set(user_ids) for ws in self.connections.get(uid, ())]
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except (RuntimeError, OSError, WebSocketDisconnect):
                pass

    async def broadcast(self, payload):
        async with self.lock:
            sockets = [ws for group in self.connections.values() for ws in group]
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except (RuntimeError, OSError, WebSocketDisconnect):
                pass

    def online_ids(self):
        return list(self.connections)


hub = Hub()


class RateLimit:
    def __init__(self):
        self.entries = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key, count, seconds):
        stamp = time.monotonic()
        with self.lock:
            samples = self.entries[key]
            while samples and stamp - samples[0] >= seconds:
                samples.popleft()
            if len(samples) >= count:
                raise HTTPException(status_code=429, detail='Slow down a little and try again.')
            samples.append(stamp)
            if len(self.entries) > 10000:
                for k in list(self.entries)[:1000]:
                    if not self.entries[k] or stamp - self.entries[k][-1] > seconds:
                        self.entries.pop(k, None)


limits = RateLimit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    with db_lock:
        db.close()


app = FastAPI(title='Nightwave Chat', lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount('/assets', StaticFiles(directory=str(ROOT / 'static')), name='assets')


@app.middleware('http')
async def secure_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ws: wss:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response


@app.get('/')
async def home():
    return FileResponse(ROOT / 'static' / 'index.html', headers={'Cache-Control': 'no-cache'})


@app.get('/healthz')
async def health():
    with db_lock:
        db.execute('SELECT 1')
    return {'ok': True}


@app.get('/api/me')
async def me(user=Depends(current_user)):
    return user


@app.post('/api/join')
async def join(data: JoinBody, request: Request, response: Response):
    existing = user_from_token(request.cookies.get(COOKIE))
    if existing:
        return existing
    limits.check(('join', request.client.host if request.client else 'unknown'), 12, 900)
    username = validate_name(data.username)
    user_id = uuid.uuid4().hex
    token = secrets.token_hex(32)
    timestamp = now()
    with db_lock:
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO users (id, username, created_at) VALUES (?,?,?)', (user_id, username, timestamp))
            db.execute('INSERT INTO sessions (token_hash,user_id,created_at,expires_at) VALUES (?,?,?,?)',
                       (hash_token(token), user_id, timestamp, timestamp + MAX_AGE * 1000))
            db.execute('COMMIT')
        except sqlite3.IntegrityError:
            db.execute('ROLLBACK')
            raise HTTPException(status_code=409, detail='That username is already taken.')
        except Exception:
            db.execute('ROLLBACK')
            raise
    is_secure = bool(os.getenv('FORCE_SECURE_COOKIE', '0') == '1' or request.url.scheme == 'https')
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, path='/', httponly=True, secure=is_secure, samesite='lax')
    return {'id': user_id, 'username': username, 'created_at': timestamp}


@app.patch('/api/me')
async def rename(data: JoinBody, user=Depends(current_user)):
    username = validate_name(data.username)
    limits.check(('rename', user['id']), 5, 600)
    with db_lock:
        try:
            db.execute('UPDATE users SET username=? WHERE id=?', (username, user['id']))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail='That username is already taken.')
    await hub.broadcast({'type': 'user:renamed', 'user_id': user['id'], 'username': username})
    return {**user, 'username': username}


@app.get('/api/users')
async def users(query: str = Query(default='', max_length=60), user=Depends(current_user)):
    with db_lock:
        rows = db.execute('''SELECT id, username FROM users WHERE id != ? AND username LIKE ? ESCAPE '\\'
                             ORDER BY username COLLATE NOCASE LIMIT 80''',
                          (user['id'], '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')).fetchall()
    online = set(hub.online_ids())
    result = [dict(row) | {'online': row['id'] in online} for row in rows]
    return sorted(result, key=lambda r: (not r['online'], r['username'].lower()))


@app.get('/api/conversations')
async def conversations(user=Depends(current_user)):
    with db_lock:
        rows = db.execute('''
            WITH peers AS (
              SELECT CASE WHEN sender_id=:uid THEN recipient_id ELSE sender_id END AS peer_id,
                     MAX(id) AS last_id
              FROM messages WHERE kind='dm' AND (sender_id=:uid OR recipient_id=:uid)
              GROUP BY peer_id
            )
            SELECT u.id, u.username, m.body AS last_body, m.sender_id AS last_sender_id,
                   m.created_at AS last_at,
                   (SELECT COUNT(*) FROM messages x
                    WHERE x.kind='dm' AND x.sender_id=u.id AND x.recipient_id=:uid
                      AND x.id > COALESCE((SELECT r.last_read_id FROM dm_reads r
                            WHERE r.viewer_id=:uid AND r.peer_id=u.id), 0)) AS unread
            FROM peers p JOIN users u ON u.id=p.peer_id JOIN messages m ON m.id=p.last_id
            ORDER BY p.last_id DESC LIMIT 80
        ''', {'uid': user['id']}).fetchall()
    online = set(hub.online_ids())
    return [dict(row) | {'online': row['id'] in online} for row in rows]


def message_dict(row):
    return dict(row)


@app.get('/api/messages/global')
async def global_messages(before: int | None = Query(default=None, ge=1), user=Depends(current_user)):
    with db_lock:
        rows = db.execute('''SELECT m.id,m.kind,m.sender_id,u.username AS sender_name,
                             m.recipient_id,m.body,m.created_at FROM messages m
                             JOIN users u ON u.id=m.sender_id
                             WHERE m.kind='global' AND (? IS NULL OR m.id < ?)
                             ORDER BY m.id DESC LIMIT 60''', (before, before)).fetchall()
    return [message_dict(row) for row in reversed(rows)]


@app.get('/api/messages/dm/{peer_id}')
async def direct_messages(peer_id: str, before: int | None = Query(default=None, ge=1), user=Depends(current_user)):
    with db_lock:
        peer = db.execute('SELECT id FROM users WHERE id=?', (peer_id,)).fetchone()
        if not peer or peer_id == user['id']:
            raise HTTPException(status_code=404, detail='User not found.')
        rows = db.execute('''SELECT m.id,m.kind,m.sender_id,u.username AS sender_name,
                             m.recipient_id,m.body,m.created_at FROM messages m
                             JOIN users u ON u.id=m.sender_id
                             WHERE m.kind='dm'
                               AND ((m.sender_id=? AND m.recipient_id=?) OR (m.sender_id=? AND m.recipient_id=?))
                               AND (? IS NULL OR m.id < ?)
                             ORDER BY m.id DESC LIMIT 60''',
                          (user['id'], peer_id, peer_id, user['id'], before, before)).fetchall()
    return [message_dict(row) for row in reversed(rows)]


@app.post('/api/messages/dm/{peer_id}/read')
async def read_dm(peer_id: str, user=Depends(current_user)):
    with db_lock:
        peer = db.execute('SELECT id FROM users WHERE id=?', (peer_id,)).fetchone()
        if not peer:
            raise HTTPException(status_code=404, detail='User not found.')
        row = db.execute('''SELECT COALESCE(MAX(id), 0) AS id FROM messages
                            WHERE kind='dm' AND sender_id=? AND recipient_id=?''', (peer_id, user['id'])).fetchone()
        db.execute('''INSERT INTO dm_reads(viewer_id,peer_id,last_read_id) VALUES (?,?,?)
                      ON CONFLICT(viewer_id,peer_id) DO UPDATE SET
                      last_read_id=MAX(last_read_id,excluded.last_read_id)''', (user['id'], peer_id, row['id']))
    return {'ok': True}


@app.post('/api/messages')
async def send_message(data: SendBody, user=Depends(current_user)):
    limits.check(('message', user['id']), 12, 10)
    body = data.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail='Message cannot be empty.')
    recipient_id = None
    if data.kind == 'dm':
        recipient_id = data.recipient_id
        if not recipient_id or recipient_id == user['id']:
            raise HTTPException(status_code=422, detail='Choose another user to message.')
        with db_lock:
            if not db.execute('SELECT 1 FROM users WHERE id=?', (recipient_id,)).fetchone():
                raise HTTPException(status_code=404, detail='Recipient not found.')
    elif data.recipient_id is not None:
        raise HTTPException(status_code=422, detail='Global messages cannot have recipients.')
    timestamp = now()
    with db_lock:
        cursor = db.execute('''INSERT INTO messages(kind,sender_id,recipient_id,body,created_at)
                               VALUES (?,?,?,?,?)''', (data.kind, user['id'], recipient_id, body, timestamp))
        msg_id = cursor.lastrowid
    message = {'id': msg_id, 'kind': data.kind, 'sender_id': user['id'], 'sender_name': user['username'],
               'recipient_id': recipient_id, 'body': body, 'created_at': timestamp}
    packet = {'type': 'message:new', 'message': message}
    if data.kind == 'global':
        await hub.broadcast(packet)
    else:
        await hub.send_to([user['id'], recipient_id], packet)
    return message


def permitted_origin(origin: str | None, host: str | None):
    if not origin:
        return False
    parsed = urlparse(origin)
    if parsed.scheme not in ('http', 'https'):
        return False
    if PUBLIC_ORIGIN:
        return origin.rstrip('/') == PUBLIC_ORIGIN
    return parsed.netloc == host


@app.websocket('/ws')
async def realtime(ws: WebSocket):
    user = user_from_token(ws.cookies.get(COOKIE))
    if not user or not permitted_origin(ws.headers.get('origin'), ws.headers.get('host')):
        await ws.close(code=4401)
        return
    await ws.accept()
    first, online = await hub.join(user['id'], ws)
    await ws.send_json({'type': 'hello', 'online_ids': online})
    if first:
        await hub.broadcast({'type': 'presence', 'user_id': user['id'], 'username': user['username'], 'online': True, 'online_count': len(online)})
    last_typing = 0.0
    try:
        while True:
            packet = await ws.receive_json()
            if not isinstance(packet, dict) or packet.get('type') != 'typing':
                continue
            stamp = time.monotonic()
            if stamp - last_typing < 0.65:
                continue
            last_typing = stamp
            kind = packet.get('kind')
            if kind not in ('global', 'dm'):
                continue
            event = {'type': 'typing', 'user_id': user['id'], 'username': user['username'], 'kind': kind}
            if kind == 'global':
                await hub.send_to([uid for uid in hub.online_ids() if uid != user['id']], event)
            else:
                peer_id = packet.get('peer_id')
                if not isinstance(peer_id, str) or peer_id == user['id']:
                    continue
                event['peer_id'] = user['id']
                await hub.send_to([peer_id], event)
    except (WebSocketDisconnect, RuntimeError, ValueError, TypeError):
        pass
    finally:
        departed = await hub.leave(user['id'], ws)
        if departed:
            await hub.broadcast({'type': 'presence', 'user_id': user['id'], 'online': False,
                                 'online_count': len(hub.online_ids())})
