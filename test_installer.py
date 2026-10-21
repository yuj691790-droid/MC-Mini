import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from installer import Installer, allowed, library_files, rewrite, safe_path, checked


class InstallerTests(unittest.TestCase):
    def test_download_routes(self):
        self.assertEqual(rewrite("https://libraries.minecraft.net/a.jar", "bmclapi", "library"),
                         "https://bmclapi2.bangbang93.com/maven/a.jar")
        self.assertEqual(rewrite("https://resources.download.minecraft.net/ab/abcd", "bmclapi", "asset"),
                         "https://bmclapi2.bangbang93.com/assets/ab/abcd")
        self.assertEqual(rewrite("https://piston-data.mojang.com/v1/client.jar", "bmclapi"),
                         "https://bmclapi2.bangbang93.com/v1/client.jar")

    def test_remote_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("../escape", "/escape", "C:/escape", "..\\escape"):
                with self.assertRaises(ValueError):
                    safe_path(folder, name)

    def test_windows_native_selection(self):
        self.assertFalse(allowed([{"action": "allow", "os": {"name": "osx"}}]))
        library = {"downloads": {"artifact": {"path": "main.jar"},
                                "classifiers": {"natives-windows-64": {"path": "win.jar"}}},
                   "natives": {"windows": "natives-windows-${arch}"}}
        self.assertEqual([x["path"] for x in library_files(library)], ["main.jar", "win.jar"])

    def test_corruption_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "client.jar"
            path.write_bytes(b"previous")
            job = ("https://example.com/client", path, hashlib.sha1(b"correct").hexdigest(), 7, "file")
            process = Mock(returncode=0)
            process.poll.return_value = 0
            def corrupt(*args, **kwargs):
                path.with_name(path.name + '.mcmini-part').write_bytes(b'corrupt')
                return process
            with patch('aria2_downloads.executable', return_value=Path('aria2c.exe')), patch(
                    'aria2_downloads.subprocess.Popen', side_effect=corrupt):
                with self.assertRaises(OSError):
                    Installer(folder).download(job)
            self.assertEqual(path.read_bytes(), b'previous')


    def test_full_install_and_reuse(self):
        blobs = {"client": b"jar", "asset": b"sound", "library": b"library"}
        def info(key):
            data = blobs[key]
            return {"url": "https://example.com/" + key,
                    "sha1": hashlib.sha1(data).hexdigest(), "size": len(data)}
        asset = info("asset")
        index = {"objects": {"sound/test.ogg": {"hash": asset["sha1"], "size": asset["size"]}},
                 "virtual": True, "map_to_resources": True}
        blobs["index"] = json.dumps(index).encode()
        meta = {"id": "test", "downloads": {"client": info("client")},
                "libraries": [{"downloads": {"artifact": {**info("library"), "path": "a/lib.jar"}}}],
                "assetIndex": {**info("index"), "id": "test"}}
        blobs[asset["sha1"]] = blobs["asset"]
        raw = json.dumps(meta).encode()
        with tempfile.TemporaryDirectory() as folder:
            installer = Installer(folder, "official", lambda _: None)
            def transfer(items, cancel, log, logdir, progress=None):
                for urls, dest, sha1, size, kind in items:
                    url = urls[0] if isinstance(urls, list) else urls
                    data = blobs[url.rsplit('/', 1)[1]]
                    checked(data, sha1, size)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
            with patch("installer.get_json", return_value=(meta, raw)), patch('installer.fetch', side_effect=transfer):
                target = installer.install({"id": "test", "url": "https://example.com/meta"})
            self.assertEqual((target / "test.json").read_bytes(), raw)
            self.assertEqual((Path(folder) / "resources/sound/test.ogg").read_bytes(), b"sound")
            with patch("installer.get_json", return_value=(meta, raw)), patch("installer.request") as request:
                installer.install({"id": "test", "url": "https://example.com/meta"})
                request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
