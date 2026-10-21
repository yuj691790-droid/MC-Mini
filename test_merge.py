import hashlib
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch

from aria2_downloads import executable, fetch
from installer import get_json, rewrite, source_urls
from loaders import installer_digest


class MergeTests(unittest.TestCase):
    def test_selected_source_keeps_priority(self):
        url = 'https://resources.download.minecraft.net/aa/hash'
        urls = source_urls(url, 'bmclapi', 'asset')
        self.assertEqual(urls[0], 'https://bmclapi2.bangbang93.com/assets/aa/hash')
        self.assertEqual(urls[1], url)
        self.assertEqual(source_urls(url, 'official', 'asset'), list(reversed(urls)))

    def test_metadata_network_failure_uses_alternate(self):
        calls = []
        def request(url):
            calls.append(url)
            if len(calls) == 1:
                raise urllib.error.URLError('TLS EOF')
            return io.BytesIO(b'{"ok":true}')
        with patch('installer.request', side_effect=request):
            data, _ = get_json('https://piston-meta.mojang.com/v1/test.json', 'bmclapi')
        self.assertTrue(data['ok'])
        self.assertIn('bmclapi', calls[0])
        self.assertIn('mojang', calls[1])

    def test_hash_and_json_failures_are_not_retried(self):
        for payload, sha in [(b'{}', '0' * 40), (b'invalid JSON', None)]:
            with patch('installer.request', return_value=io.BytesIO(payload)) as request:
                with self.assertRaises(ValueError):
                    get_json('https://piston-meta.mojang.com/v1/test.json', 'official', sha)
                self.assertEqual(request.call_count, 1)

    def test_neoforge_cdn_mirror_mapping(self):
        self.assertEqual(rewrite('https://neoforged.forgecdn.net/releases/net/neoforged/test.jar', 'bmclapi'),
                         'https://bmclapi2.bangbang93.com/maven/net/neoforged/test.jar')

    def test_missing_digest_never_disables_verification(self):
        with patch('loaders.request', return_value=io.BytesIO(b'not a checksum')):
            with self.assertRaises(ValueError):
                installer_digest('https://neoforged.forgecdn.net/releases/test.jar', 'official')

    def test_bundled_aria2_precedes_external_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'aria2/aria2c.exe'
            path.parent.mkdir()
            path.write_bytes(b'test placeholder, never executed')
            with patch.object(sys, '_MEIPASS', folder, create=True):
                self.assertEqual(executable(), path)

    @unittest.skipUnless((Path(__file__).parent / 'aria2/aria2c.exe').exists(), 'run fetch_aria2.py first')
    def test_real_alternate_uri_on_missing_primary(self):
        payload = b'alternate source verified'
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                requests.append(self.path)
                if self.path == '/missing':
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                base = f'http://127.0.0.1:{server.server_port}'
                target = Path(folder) / 'result'
                fetch([([base+'/missing', base+'/good'], target, hashlib.sha1(payload).hexdigest(),
                        len(payload), 'file')], threading.Event(), lambda _: None, Path(folder)/'logs')
                self.assertEqual(target.read_bytes(), payload)
                self.assertEqual(requests[:2], ['/missing', '/good'])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
