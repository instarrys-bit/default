import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from collect_domains import fetch


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return "https://raw.githubusercontent.com/example/rules/main/list.txt"

    def read(self, _limit):
        return b"example.com\n"


class FetchRetryTests(unittest.TestCase):
    def test_retries_transient_http_error_then_succeeds(self):
        transient = HTTPError(
            "https://raw.githubusercontent.com/example/rules/main/list.txt",
            503,
            "Service Unavailable",
            {},
            None,
        )
        with patch("collect_domains.urllib.request.urlopen", side_effect=[transient, Response()]) as mocked:
            with patch("collect_domains.time.sleep") as sleeper:
                self.assertEqual(
                    fetch("https://raw.githubusercontent.com/example/rules/main/list.txt"),
                    b"example.com\n",
                )
        self.assertEqual(mocked.call_count, 2)
        sleeper.assert_called_once_with(2)

    def test_does_not_retry_permanent_http_error(self):
        permanent = HTTPError(
            "https://raw.githubusercontent.com/example/rules/main/list.txt",
            404,
            "Not Found",
            {},
            None,
        )
        with patch("collect_domains.urllib.request.urlopen", side_effect=permanent) as mocked:
            with patch("collect_domains.time.sleep") as sleeper:
                with self.assertRaises(HTTPError):
                    fetch("https://raw.githubusercontent.com/example/rules/main/list.txt")
        self.assertEqual(mocked.call_count, 1)
        sleeper.assert_not_called()

    def test_rejects_non_raw_source_before_network_request(self):
        with patch("collect_domains.urllib.request.urlopen") as mocked:
            with self.assertRaises(ValueError):
                fetch("https://example.com/rules.txt")
        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
