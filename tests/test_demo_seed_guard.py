"""``demo seed`` refuses a populated store, an empty token, and raw tracebacks.

F-D1: seeding a store that already holds businesses duplicates the demo and the
API's integrity guards (409s on DELETE) make the copies unremovable — so a
second seed must refuse unless ``--force``. F-X15: an unreachable or refusing
API surfaces as a one-line message and a non-zero exit, never a traceback, and
an empty ``--token`` is refused before any request is made.

Driven against a fake ``urlopen`` injected into ``_run_seed`` — no live HTTP,
matching ``tests/test_demo_seed.py``'s injected-callable pattern.
"""

import argparse
import io
import itertools
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pytest

from driftless import cli as top_cli
from driftless.demo.cli import _run_seed


class FakeApi:
    """A stand-in for ``urllib.request.urlopen`` recording every request."""

    def __init__(self, businesses: list[dict[str, Any]], error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._businesses = businesses
        self._error = error
        self._ids = itertools.count(1)

    def __call__(self, request: urllib.request.Request) -> io.BytesIO:
        # The admin-guide doc harness requires every request to carry bytes,
        # probe included — hold the CLI to the same wire shape here.
        assert isinstance(request.data, bytes)
        method = request.get_method()
        path = urllib.parse.urlsplit(request.full_url).path
        self.calls.append((method, path))
        if self._error is not None:
            raise self._error
        if method == "GET":
            return io.BytesIO(json.dumps(self._businesses).encode())
        if method == "POST":
            return io.BytesIO(json.dumps({"id": next(self._ids)}).encode())
        return io.BytesIO(b"{}")


def _args(monkeypatch: pytest.MonkeyPatch, *extra: str) -> argparse.Namespace:
    """Parse real CLI args so the test exercises the registered flags."""
    monkeypatch.delenv("DRIFTLESS_API_TOKEN", raising=False)
    argv = ["demo", "seed", "--base-url", "http://api.test", *extra]
    return top_cli._build_parser().parse_args(argv)


def test_seed_on_an_empty_store_seeds_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(businesses=[])
    assert _run_seed(_args(monkeypatch, "--token", "t"), urlopen=api) == 0
    assert capsys.readouterr().out.startswith("Seeded: ")
    assert api.calls[0] == ("GET", "/businesses")  # the guard probes first
    assert ("POST", "/businesses") in api.calls


def test_second_seed_refuses_a_populated_store(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(businesses=[{"id": 1, "name": "Prairie Roasters"}])
    assert _run_seed(_args(monkeypatch, "--token", "t"), urlopen=api) != 0
    err = capsys.readouterr().err
    assert "--force" in err  # the refusal names the override
    assert all(method != "POST" for method, _ in api.calls)  # nothing was written


def test_force_seeds_a_populated_store(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(businesses=[{"id": 1, "name": "Prairie Roasters"}])
    assert _run_seed(_args(monkeypatch, "--token", "t", "--force"), urlopen=api) == 0
    assert capsys.readouterr().out.startswith("Seeded: ")
    assert ("POST", "/businesses") in api.calls


def test_empty_token_refuses_before_any_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(businesses=[])
    assert _run_seed(_args(monkeypatch), urlopen=api) != 0
    assert "token" in capsys.readouterr().err.lower()
    assert api.calls == []  # refused before touching the network


def test_unreachable_api_is_one_line_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    api = FakeApi(businesses=[], error=urllib.error.URLError("connection refused"))
    assert _run_seed(_args(monkeypatch, "--token", "t"), urlopen=api) != 0
    err = capsys.readouterr().err
    assert "http://api.test" in err and "connection refused" in err


def test_default_transport_is_looked_up_at_call_time(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No ``urlopen=`` passed: the CLI must honour a monkeypatched
    ``urllib.request.urlopen`` (the admin-guide doc test relies on this),
    so the default may never be bound at import time."""
    api = FakeApi(businesses=[])
    monkeypatch.setattr("urllib.request.urlopen", api)
    assert _run_seed(_args(monkeypatch, "--token", "t")) == 0
    assert capsys.readouterr().out.startswith("Seeded: ")
    assert api.calls[0] == ("GET", "/businesses")


def test_http_error_reports_status_and_server_detail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    body = io.BytesIO(json.dumps({"detail": "invalid token"}).encode())
    error = urllib.error.HTTPError("http://api.test/businesses", 401, "Unauthorized", None, body)
    api = FakeApi(businesses=[], error=error)
    assert _run_seed(_args(monkeypatch, "--token", "t"), urlopen=api) != 0
    err = capsys.readouterr().err
    assert "401" in err and "invalid token" in err
