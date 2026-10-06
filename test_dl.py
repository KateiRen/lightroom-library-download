import importlib.util
from pathlib import Path
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

import dl


MODULE_PATH = Path(__file__).with_name("extract-links.py")
SPEC = importlib.util.spec_from_file_location("extract_links", MODULE_PATH)
extract_links = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(extract_links)


class RemoteSizeTests(unittest.TestCase):
    @patch("dl.urlopen")
    def test_remote_size_returns_none_on_http_403(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(
            "https://example.com/file.zip",
            403,
            "Forbidden",
            hdrs=None,
            fp=None,
        )

        self.assertIsNone(dl.remote_size("https://example.com/file.zip"))


class ExtractLinksParsingTests(unittest.TestCase):
    def test_strip_adobe_json_guard_removes_prefix_and_trailing_noise(self):
        raw = "\n)]}'\n{\"archive_files\": [{\"name\": \"a.zip\"}], \"status\": \"ready\"}\n<script>ignored</script>"

        self.assertEqual(
            extract_links.strip_adobe_json_guard(raw),
            '{"archive_files": [{"name": "a.zip"}], "status": "ready"}',
        )

    def test_strip_adobe_json_guard_keeps_first_valid_object_when_extra_json_follows(self):
        raw = "\n)]}'\n{\"archive_files\": [{\"name\": \"first.zip\"}], \"status\": \"ready\"}\n{\"ignored\": true}\n"

        self.assertEqual(
            extract_links.strip_adobe_json_guard(raw),
            '{"archive_files": [{"name": "first.zip"}], "status": "ready"}',
        )

    def test_build_archive_from_visible_links_creates_archive_file_list(self):
        archive = extract_links.build_archive_from_links(
            [
                {"href": "https://example.com/a.zip", "name": "a.zip"},
                {"href": "https://example.com/b.zip", "name": "b.zip"},
            ]
        )

        self.assertIsNotNone(archive)
        self.assertEqual(archive["status"], "ready")
        self.assertEqual(
            [item["name"] for item in archive["archive_files"]],
            ["a.zip", "b.zip"],
        )

    def test_build_archive_from_visible_links_rejects_adobe_privacy_links(self):
        archive = extract_links.build_archive_from_links(
            [
                {"href": "https://www.adobe.com/privacy/opt-out.html", "name": "AdChoices"},
                {"href": "https://www.facebook.com/adobe", "name": "Follow Adobe"},
                {"href": "https://example.com/LightroomLibrary_1.zip?sig=abc", "name": "LightroomLibrary_1.zip"},
            ]
        )

        self.assertIsNotNone(archive)
        self.assertEqual(
            [item["name"] for item in archive["archive_files"]],
            ["LightroomLibrary_1.zip"],
        )

    def test_parse_markdown_ignores_junk_links(self):
        markdown = """# Adobe Lightroom library download links

| # | Description | File | Size | Download link |
|---:|---|---|---:|---|
| 1 | Lightroom library archive file AdChoices | `AdChoices` | 0 B | <https://www.adobe.com/de/privacy/opt-out.html#interest-based-ads> |
| 2 | Lightroom library archive file real archive | `photos.zip` | 15 MB | <https://download.adobe.com/archive/photos.zip> |
"""

        path = Path("junk.md")
        path.write_text(markdown, encoding="utf-8")
        try:
            entries = dl.parse_markdown(path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].filename, "photos.zip")
            self.assertEqual(entries[0].url, "https://download.adobe.com/archive/photos.zip")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
