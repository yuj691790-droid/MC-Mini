import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from installer import library_files, maven_path, rewrite
from loaders import catalog, neoforge_minecraft, publish_profile, installer_digest, installer_url, install_component


class LoaderTests(unittest.TestCase):
    def test_maven_classifiers_and_extensions(self):
        self.assertEqual(maven_path("net.test:client:1.2:mappings@txt"),
                         "net/test/client/1.2/client-1.2-mappings.txt")
        info = library_files({"name": "net.fabricmc:loader:1", "url": "https://maven.fabricmc.net/",
                              "sha1": "abc", "size": 123})[0]
        self.assertEqual(info["sha1"], "abc")
        self.assertEqual(info["size"], 123)

    def test_loader_mirror_paths(self):
        self.assertEqual(rewrite("https://maven.fabricmc.net/net/fabricmc/a.jar", "bmclapi"),
                         "https://bmclapi2.bangbang93.com/maven/net/fabricmc/a.jar")
        self.assertEqual(rewrite("https://maven.neoforged.net/releases/net/neoforged/a.jar", "bmclapi"),
                         "https://bmclapi2.bangbang93.com/maven/net/neoforged/a.jar")

    def test_neoforge_digest_falls_back_to_official_when_mirror_has_no_sha1(self):
        calls = []

        class Response:
            def read(self):
                return b"c4d0035fa61fa24460831e3c686d3f68227e9d54  installer.jar\n"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_request(url):
            calls.append(url)
            if "bmclapi" in url:
                raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
            return Response()

        url = "https://maven.neoforged.net/releases/net/neoforged/neoforge/21.1.215/neoforge-21.1.215-installer.jar"
        with patch("loaders.request", side_effect=fake_request):
            digest = installer_digest(url, "bmclapi")
        self.assertEqual(digest, "c4d0035fa61fa24460831e3c686d3f68227e9d54")
        self.assertEqual(calls, ["https://bmclapi2.bangbang93.com/maven/net/neoforged/neoforge/21.1.215/neoforge-21.1.215-installer.jar.sha1",
                                 url + ".sha1"])

    def test_neoforge_mc_conventions(self):
        for loader, mc in [("21.0.167", "1.21"), ("21.1.215", "1.21.1"),
                           ("26.3.0.95", "26.3"), ("26.1.2.0-beta", "26.1.2"),
                           ("0.25w14craftmine.3-beta", "25w14craftmine")]:
            self.assertEqual(neoforge_minecraft(loader), mc)
        self.assertEqual(neoforge_minecraft("1.20.1-47.1.106", "forge"), "1.20.1")

    def test_neoforge_mirror_catalog_filters_game(self):
        data = {"files": [{"name": name, "type": "DIRECTORY"} for name in
                          ["21.1.9", "21.0.99", "21.1.100"]]}
        with patch("loaders.get_json", return_value=(data, b"")):
            self.assertEqual([r["version"] for r in catalog("NeoForge", "1.21.1", "bmclapi")],
                             ["21.1.100", "21.1.9"])

    def test_forge_catalog_excludes_non_installer_and_retains_branch(self):
        data = [{"version": "10.13.4.1614", "branch": "1.7.10",
                 "files": [{"category": "installer", "format": "jar", "hash": "abc"}]},
                {"version": "10.0", "files": [{"category": "universal", "format": "jar"}]}]
        with patch("loaders.get_json", return_value=(data, b"")):
            rows = catalog("Forge", "1.7.10", "bmclapi")
        self.assertEqual(len(rows), 1)
        self.assertIn("1.7.10-10.13.4.1614-1.7.10", installer_url("Forge", "1.7.10", rows[0], "bmclapi"))

    def test_optifine_stable_before_preview_and_mc_filter(self):
        rows = [{"mcversion": mc, "type": "HD_U", "patch": p, "filename": "test.jar"}
                for mc, p in [("1.20.1", "I6_pre6"), ("1.20.1", "I6"), ("1.20.2", "I7")]]
        with patch("loaders.get_json", return_value=(rows, b"")):
            result = catalog("OptiFine", "1.20.1", "official")
        self.assertEqual([r["version"] for r in result], ["HD_U_I6", "HD_U_I6_pre6"])

    def test_fabric_timestamp_changes_do_not_overwrite_custom_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            p = {"id": "fabric-test", "inheritsFrom": "1.20.1", "time": "old"}
            path = publish_profile(folder, p)
            publish_profile(folder, {**p, "time": "new"})
            with self.assertRaises(FileExistsError):
                publish_profile(folder, {**p, "mainClass": "custom.Main"})
            self.assertNotIn("mainClass", json.loads((path / "fabric-test.json").read_bytes()))

    def test_fabric_failed_dependency_does_not_publish_profile(self):
        from installer import Installer
        with tempfile.TemporaryDirectory() as folder:
            p = {"id": "fabric-test", "inheritsFrom": "1.20.1", "libraries": []}
            with patch("loaders.get_json", return_value=(p, b"")), patch(
                    "loaders.download_libraries", side_effect=OSError("download failed")):
                with self.assertRaises(OSError):
                    install_component(Installer(folder), "1.20.1", "Fabric", {"version": "0.16.10"})
            self.assertFalse((Path(folder) / "versions/fabric-test").exists())


if __name__ == "__main__":
    unittest.main()
