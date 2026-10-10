"""Run with: python -m unittest discover -s tests -v"""
import asyncio
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DATA_DIR = tempfile.mkdtemp(prefix='nightwave-test-')
os.environ['DATABASE_PATH'] = str(Path(TEST_DATA_DIR) / 'chat.db')
from server import app  # noqa: E402


class ChatAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clients = [httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') for _ in range(3)]
        self.names = ['Alice' + uuid.uuid4().hex[:9], 'Bob' + uuid.uuid4().hex[:9], 'Cary' + uuid.uuid4().hex[:9]]
        self.users = []
        for client, name in zip(self.clients, self.names):
            r = await client.post('/api/join', json={'username': name})
            self.assertEqual(r.status_code, 200, r.text)
            self.users.append(r.json())

    async def asyncTearDown(self):
        await asyncio.gather(*(client.aclose() for client in self.clients))

    async def test_sessions_global_dm_isolation_unread_and_rename(self):
        alice, bob, cary = self.clients
        a, b, c = self.users
        self.assertEqual((await alice.get('/api/me')).json()['id'], a['id'])
        global_msg = await alice.post('/api/messages', json={'kind': 'global', 'body': 'Hello everyone'})
        self.assertEqual(global_msg.status_code, 200, global_msg.text)
        self.assertEqual((await cary.get('/api/messages/global')).json()[-1]['body'], 'Hello everyone')

        direct = await alice.post('/api/messages', json={'kind': 'dm', 'recipient_id': b['id'], 'body': 'Private hello'})
        self.assertEqual(direct.status_code, 200, direct.text)
        self.assertEqual(len((await bob.get(f"/api/messages/dm/{a['id']}")).json()), 1)
        self.assertEqual(len((await cary.get(f"/api/messages/dm/{a['id']}")).json()), 0)
        self.assertEqual((await bob.get('/api/conversations')).json()[0]['unread'], 1)
        self.assertEqual((await bob.post(f"/api/messages/dm/{a['id']}/read")).status_code, 200)
        self.assertEqual((await bob.get('/api/conversations')).json()[0]['unread'], 0)

        renamed = await alice.patch('/api/me', json={'username': 'New' + uuid.uuid4().hex[:12]})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual((await bob.get(f"/api/messages/dm/{a['id']}")).json()[0]['sender_name'], renamed.json()['username'])

    async def test_validation_and_duplicate_username(self):
        alice, bob, cary = self.clients
        a, b, c = self.users
        self.assertEqual((await bob.patch('/api/me', json={'username': a['username'].upper()})).status_code, 409)
        self.assertEqual((await bob.patch('/api/me', json={'username': 'admin'})).status_code, 422)
        self.assertEqual((await alice.post('/api/messages', json={'kind': 'global', 'body': '   '})).status_code, 422)
        self.assertEqual((await alice.post('/api/messages', json={'kind': 'dm', 'recipient_id': a['id'], 'body': 'me'})).status_code, 422)
        self.assertEqual((await alice.post('/api/messages', json={'kind': 'global', 'recipient_id': b['id'], 'body': 'no'})).status_code, 422)
        anon = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost')
        self.assertEqual((await anon.get('/api/users')).status_code, 401)
        self.assertEqual((await anon.post('/api/messages', json={'kind': 'global', 'body': 'no'})).status_code, 401)
        self.assertEqual((await anon.post('/api/join', json={'username': a['username'].lower()})).status_code, 409)
        await anon.aclose()


if __name__ == '__main__':
    unittest.main()
