"""``driftless.web.receipt``: the reproducibility receipt footer attached to a
computed page — as-of, schema revision, build SHA and a sha256 of the response
body EXCLUDING the footer itself, since a footer that hashed itself could never
be verified against a saved copy of the page."""

import hashlib
import subprocess
from datetime import date

import pytest
from starlette.responses import HTMLResponse

from driftless.db.schema_version import EXPECTED_REVISION
from driftless.web import receipt


def test_git_sha_falls_back_to_unknown_with_no_repo_and_no_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("no git")

    monkeypatch.delenv(receipt._GIT_SHA_ENV, raising=False)
    monkeypatch.setattr(subprocess, "run", _raise)
    assert receipt._read_git_sha() == "unknown"


def test_git_sha_honours_the_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(receipt._GIT_SHA_ENV, "deadbeef")
    assert receipt._read_git_sha() == "deadbeef"


def test_attach_receipt_hashes_the_body_before_the_footer_is_added() -> None:
    body = b"<html><body><main>hello</main></body></html>"
    response = HTMLResponse(content=body)
    original_hash = hashlib.sha256(body).hexdigest()

    updated = receipt.attach_receipt(response, date(2026, 9, 22))

    assert updated is response  # mutated in place, not replaced
    text = bytes(response.body).decode("utf-8")
    assert original_hash in text
    assert "2026-09-22" in text
    assert EXPECTED_REVISION in text
    assert receipt.GIT_SHA in text
    # the receipt sits before the closing tag it was inserted in front of
    assert text.index(original_hash) < text.index("</body>")


def test_attach_receipt_appends_when_there_is_no_body_tag() -> None:
    body = b"<p>no body tag here</p>"
    response = HTMLResponse(content=body)
    original_hash = hashlib.sha256(body).hexdigest()

    receipt.attach_receipt(response, date(2026, 9, 22))

    assert original_hash in bytes(response.body).decode("utf-8")


def test_attach_receipt_updates_content_length() -> None:
    body = b"<html><body>x</body></html>"
    response = HTMLResponse(content=body)
    receipt.attach_receipt(response, date(2026, 9, 22))
    assert response.headers["content-length"] == str(len(response.body))


def test_verify_receipt_is_true_on_an_untouched_saved_page() -> None:
    body = b"<html><body><main>hello</main></body></html>"
    response = HTMLResponse(content=body)
    receipt.attach_receipt(response, date(2026, 9, 22))
    page = bytes(response.body).decode("utf-8")
    assert receipt.verify_receipt(page) is True


def test_verify_receipt_is_false_after_a_one_byte_edit() -> None:
    body = b"<html><body><main>hello</main></body></html>"
    response = HTMLResponse(content=body)
    receipt.attach_receipt(response, date(2026, 9, 22))
    page = bytes(response.body).decode("utf-8").replace("hello", "hellO")
    assert receipt.verify_receipt(page) is False


def test_verify_receipt_is_false_with_no_receipt_at_all() -> None:
    assert receipt.verify_receipt("<html><body>no receipt here</body></html>") is False
