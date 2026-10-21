import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from aria2_downloads import fetch


class Aria2Tests(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).parent / 'aria2/aria2c.exe').is_file(), 'run fetch_aria2.py first')
    def test_live_rpc_reports_bytes_and_speed_then_exits(self):
        payload = b'x' * (3 * 1024 * 1024)
        updates = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                for offset in range(0, len(payload), 16384):
                    self.wfile.write(payload[offset:offset+16384])
                    self.wfile.flush()
                    time.sleep(0.012)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                cached = root / 'cached'
                cached.write_bytes(b'cache')
                jobs = [(f'http://127.0.0.1:{server.server_port}/file', root / 'file',
                         hashlib.sha1(payload).hexdigest(), len(payload), 'file'),
                        ('https://example.com/cached', cached, hashlib.sha1(b'cache').hexdigest(), 5, 'file')]
                fetch(jobs, threading.Event(), lambda _: None, root / 'logs',
                      progress=lambda *data: updates.append(data))
                total = len(payload) + 5
                self.assertEqual(updates[0], (5, total, 0))
                self.assertTrue(any(5 < done < total and speed > 0 for done, _, speed in updates), updates)
                self.assertEqual(updates[-1], (total, total, 0))
                self.assertEqual((root / 'file').read_bytes(), payload)
        finally:
            server.shutdown()
            server.server_close()

    @unittest.skipUnless((Path(__file__).parent / 'aria2/aria2c.exe').is_file(), 'run fetch_aria2.py first')
    def test_cancel_stops_process_and_retains_partial_file(self):
        started = threading.Event()
        cancel = threading.Event()
        payload = b'x' * (1024 * 1024)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                try:
                    for offset in range(0, len(payload), 16384):
                        self.wfile.write(payload[offset:offset+16384])
                        self.wfile.flush()
                        started.set()
                        time.sleep(0.03)
                except ConnectionError:
                    pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        def interrupt():
            if started.wait(5):
                time.sleep(0.1)
                cancel.set()
        threading.Thread(target=interrupt, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'download'
                job = (f'http://127.0.0.1:{server.server_port}/file', path,
                       hashlib.sha1(payload).hexdigest(), len(payload), 'file')
                with self.assertRaises(InterruptedError):
                    fetch([job], cancel, lambda _: None, Path(folder) / 'logs')
                self.assertFalse(path.exists())
                self.assertTrue(path.with_name(path.name + '.mcmini-part').exists())
        finally:
            server.shutdown()
            server.server_close()

    def test_cached_file_needs_no_process(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cached'
            path.write_bytes(b'valid')
            with patch('aria2_downloads.executable', side_effect=AssertionError('must reuse cache')):
                fetch([('https://example.com/file', path, hashlib.sha1(b'valid').hexdigest(), 5, 'file')],
                      threading.Event(), lambda _: None, Path(folder) / 'logs')

    def test_input_file_injection_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                fetch([('https://example.com/file\n  dir=C:/', Path(folder) / 'file', None, None, 'file')],
                      threading.Event(), lambda _: None, Path(folder) / 'logs')

    @unittest.skipUnless((Path(__file__).parent / 'aria2/aria2c.exe').is_file(), 'run fetch_aria2.py first')
    def test_real_batch_resumes_interrupted_http_transfer(self):
        payload = bytes(range(256)) * 4096
        ranges = []
        broken = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                header = self.headers.get('Range')
                start = int(header.split('=')[1].split('-')[0]) if header else 0
                ranges.append(start)
                self.send_response(206 if header else 200)
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(len(payload) - start))
                if header:
                    self.send_header('Content-Range', f'bytes {start}-{len(payload)-1}/{len(payload)}')
                self.end_headers()
                if self.path == '/broken' and not broken.is_set():
                    broken.set()
                    self.wfile.write(payload[:65536])
                    self.wfile.flush()
                    self.close_connection = True
                else:
                    self.wfile.write(payload[start:])
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                sha = hashlib.sha1(payload).hexdigest()
                jobs = [(f'http://127.0.0.1:{server.server_port}/{name}', root / name,
                         sha, len(payload), 'file') for name in ('normal', 'broken')]
                fetch(jobs, threading.Event(), lambda _: None, root / 'logs')
                self.assertTrue(broken.is_set())
                self.assertTrue(any(offset > 0 for offset in ranges), ranges)
                for job in jobs:
                    self.assertEqual(job[1].read_bytes(), payload)
                    self.assertFalse(job[1].with_name(job[1].name + '.mcmini-part').exists())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
