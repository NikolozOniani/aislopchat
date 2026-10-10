"""End-to-end HTTP/WebSocket smoke test against a real Uvicorn process."""
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class LiveDeploymentTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_url_frontend_api_websocket_and_persistence(self):
        with tempfile.TemporaryDirectory(prefix='nightwave-live-') as tmp:
            db_path = str(Path(tmp) / 'live.db')
            port = free_port()
            origin = f'http://127.0.0.1:{port}'
            env = dict(os.environ, DATABASE_PATH=db_path, FORCE_SECURE_COOKIE='0')

            def start():
                return subprocess.Popen(
                    [sys.executable, '-m', 'uvicorn', 'server:app', '--host', '127.0.0.1',
                     '--port', str(port), '--workers', '1'],
                    cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                )

            async def ready(proc):
                for _ in range(100):
                    if proc.poll() is not None:
                        raise AssertionError('Uvicorn quit unexpectedly: ' + proc.stderr.read().decode()[-1500:])
                    try:
                        async with httpx.AsyncClient(base_url=origin, timeout=0.35) as c:
                            if (await c.get('/healthz')).json() == {'ok': True}:
                                return
                    except (OSError, httpx.RequestError):
                        pass
                    await asyncio.sleep(0.075)
                raise AssertionError('Uvicorn did not start within 8 seconds')

            def stop(proc):
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                proc.stderr.close()

            proc = start()
            try:
                await ready(proc)
                async with httpx.AsyncClient(base_url=origin, timeout=5) as alice, \
                           httpx.AsyncClient(base_url=origin, timeout=5) as bob, \
                           httpx.AsyncClient(base_url=origin, timeout=5) as third:
                    homepage = await alice.get('/')
                    self.assertEqual(homepage.status_code, 200)
                    self.assertIn('Nightwave', homepage.text)
                    self.assertEqual((await alice.get('/assets/app.js')).status_code, 200)
                    self.assertEqual((await alice.get('/assets/styles.css')).status_code, 200)

                    users = []
                    for c, name in [(alice, 'AliceLiveTest'), (bob, 'BobLiveTest'), (third, 'ThirdLiveTest')]:
                        r = await c.post('/api/join', json={'username': name})
                        self.assertEqual(r.status_code, 200, r.text)
                        self.assertIn('nightwave_session', c.cookies)
                        users.append(r.json())

                    async def socket_for(client):
                        cookie = client.cookies.get('nightwave_session')
                        return connect(
                            f'ws://127.0.0.1:{port}/ws', origin=origin,
                            additional_headers={'Cookie': f'nightwave_session={cookie}'},
                        )

                    async with await socket_for(alice) as wa, \
                               await socket_for(bob) as wb, \
                               await socket_for(third) as wc:
                        async def message_for(ws, msg_id):
                            for _ in range(15):
                                packet = await asyncio.wait_for(ws.recv(), timeout=2)
                                import json
                                payload = json.loads(packet)
                                if payload.get('type') == 'message:new' and payload['message']['id'] == msg_id:
                                    return payload['message']
                            raise AssertionError('Did not receive expected message event')

                        public = await alice.post('/api/messages', json={'kind': 'global', 'body': 'Online test'})
                        self.assertEqual(public.status_code, 200)
                        for ws in (wa, wb, wc):
                            self.assertEqual((await message_for(ws, public.json()['id']))['body'], 'Online test')

                        secret = await alice.post('/api/messages', json={
                            'kind': 'dm', 'recipient_id': users[1]['id'], 'body': 'DM test'})
                        self.assertEqual(secret.status_code, 200)
                        self.assertEqual((await message_for(wa, secret.json()['id']))['body'], 'DM test')
                        self.assertEqual((await message_for(wb, secret.json()['id']))['body'], 'DM test')
                        self.assertEqual((await third.get(f"/api/messages/dm/{users[0]['id']}")).json(), [])

                    # After process restart, browser cookie and message history still work.
                    token = alice.cookies.get('nightwave_session')
                stop(proc)
                proc = start()
                await ready(proc)
                async with httpx.AsyncClient(base_url=origin, timeout=5) as after:
                    after.cookies.set('nightwave_session', token)
                    self.assertEqual((await after.get('/api/me')).json()['username'], 'AliceLiveTest')
                    self.assertEqual((await after.get('/api/messages/global')).json()[-1]['body'], 'Online test')
            finally:
                if proc.poll() is None:
                    stop(proc)


if __name__ == '__main__':
    unittest.main()
