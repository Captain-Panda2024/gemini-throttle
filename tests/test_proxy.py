import sys
import os
import unittest
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proxy"))

import httpx
from main import parse_retry_window, _join_path, estimate_tokens


def _make_response(status=429, headers=None, json_body=None, text=""):
    if headers is None:
        headers = {}
    if json_body is not None:
        content = json.dumps(json_body).encode()
        headers = dict(headers)
        headers.setdefault("content-type", "application/json")
    else:
        content = text.encode()
        headers = dict(headers)
    return httpx.Response(status_code=status, headers=headers, content=content)


class TestParseRetryWindow(unittest.TestCase):
    def test_retry_after_header(self):
        resp = _make_response(headers={"retry-after": "30"})
        assert parse_retry_window(resp) == 30.0

    def test_retry_after_capped(self):
        resp = _make_response(headers={"retry-after": "200"})
        assert parse_retry_window(resp) == 65.0

    def test_retry_info_json(self):
        resp = _make_response(json_body={
            "error": {"details": [{"retryDelay": "15s"}]}
        })
        assert parse_retry_window(resp) == 15.0

    def test_body_text(self):
        resp = _make_response(text="Please retry after 5 seconds")
        assert parse_retry_window(resp) == 5.0

    def test_default(self):
        resp = _make_response(text="Rate limited")
        assert parse_retry_window(resp) == 10.0


class TestJoinPath(unittest.TestCase):
    def test_basic(self):
        assert _join_path("v1", "models") == "/v1/models"

    def test_dedup_v1(self):
        assert _join_path("v1", "v1", "models") == "/v1/models"

    def test_dedup_openai(self):
        assert _join_path("v1", "openai", "v1", "models") == "/v1/openai/models"

    def test_empty(self):
        assert _join_path("") == "/"


class TestEstimateTokens(unittest.TestCase):
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_basic(self):
        assert estimate_tokens("a" * 40) == 10

    def test_minimum(self):
        assert estimate_tokens("ab") == 1


if __name__ == "__main__":
    unittest.main()
