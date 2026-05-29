#!/usr/bin/env python3
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import importlib.util

SCRIPT = Path('/root/.hermes/profiles/sitekick/skills/productivity/pocket-ai/scripts/pocket_connect.py')
spec = importlib.util.spec_from_file_location('pocket_connect', SCRIPT)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


class PocketConnectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get('HERMES_HOME')
        os.environ['HERMES_HOME'] = self.tmp.name

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop('HERMES_HOME', None)
        else:
            os.environ['HERMES_HOME'] = self.old_home
        self.tmp.cleanup()

    def test_state_mismatch_refuses_exchange(self):
        pc.write_private_json(pc.pending_path('telegram-1'), {
            'state': 'expected',
            'client': {'client_id': 'cid'},
            'auth_meta': {'token_endpoint': 'https://auth/token'},
            'redirect_uri': 'http://localhost:11226/oauth/callback',
            'code_verifier': 'verifier',
            'resource': pc.POCKET_MCP_URL,
        })
        args = type('Args', (), {
            'user_id': 'telegram-1',
            'callback_url': 'http://localhost:11226/oauth/callback?code=abc&state=wrong',
            'verify': False,
        })()
        with self.assertRaises(pc.ConnectorError) as ctx:
            pc.command_complete(args)
        self.assertIn('state mismatch', str(ctx.exception))
        self.assertFalse(pc.token_path('telegram-1').exists())

    def test_start_writes_pending_without_tokens(self):
        def fake_http_json(url, **kwargs):
            if url == pc.RESOURCE_METADATA_URL:
                return {'authorization_servers': ['https://production.heypocketai.com'], 'resource': pc.POCKET_MCP_URL}
            if url.endswith('/.well-known/oauth-authorization-server'):
                return {
                    'issuer': 'https://production.heypocketai.com',
                    'authorization_endpoint': 'https://production.heypocketai.com/oauth/authorize',
                    'token_endpoint': 'https://production.heypocketai.com/oauth/token',
                    'registration_endpoint': 'https://production.heypocketai.com/oauth/register',
                }
            if url.endswith('/oauth/register'):
                return {'client_id': 'client-test'}
            raise AssertionError(url)

        args = type('Args', (), {
            'user_id': 'telegram-2',
            'port': 11226,
            'scope': pc.DEFAULT_SCOPE,
            'client_name': 'Test Client',
        })()
        with patch.object(pc, 'http_json', side_effect=fake_http_json):
            pc.command_start(args)
        pending = json.loads(pc.pending_path('telegram-2').read_text())
        self.assertEqual(pending['client']['client_id'], 'client-test')
        self.assertIn('code_verifier', pending)
        mode = pc.pending_path('telegram-2').stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_complete_stores_token_and_deletes_pending(self):
        pc.write_private_json(pc.pending_path('telegram-3'), {
            'state': 'ok',
            'client': {'client_id': 'cid'},
            'auth_meta': {'token_endpoint': 'https://auth/token'},
            'redirect_uri': 'http://localhost:11226/oauth/callback',
            'code_verifier': 'verifier',
            'resource': pc.POCKET_MCP_URL,
            'scope': pc.DEFAULT_SCOPE,
        })
        args = type('Args', (), {
            'user_id': 'telegram-3',
            'callback_url': 'http://localhost:11226/oauth/callback?code=abc&state=ok',
            'verify': False,
        })()
        with patch.object(pc, 'http_form', return_value={'access_token': 'at', 'refresh_token': 'rt', 'expires_in': 3600, 'scope': pc.DEFAULT_SCOPE}):
            pc.command_complete(args)
        data = json.loads(pc.token_path('telegram-3').read_text())
        self.assertEqual(data['access_token'], 'at')
        self.assertEqual(data['refresh_token'], 'rt')
        self.assertFalse(pc.pending_path('telegram-3').exists())
        mode = pc.token_path('telegram-3').stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)


if __name__ == '__main__':
    unittest.main()
