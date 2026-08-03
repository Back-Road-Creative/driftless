"""The request log: one JSON line per request, no credentials in it, quiet by default.

The last two are the point. A query string or an ``Authorization`` header in a
log line is a leak, and a log that shouts at the default level would bury every
other message the service emits.

Quiet by default is the *library's* contract, not the deployment's. The bottom
half of this file is the other side of it: the shipped image must hand uvicorn a
configuration that raises this one logger, or the container an operator actually
runs emits no driftless line at all.
"""

import io
import json
import logging
import logging.config
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_docker_build_context import _instructions, image_paths

from driftless.api.app import app, get_session
from driftless.db import Base, new_engine, new_session_factory

LOGGER = "driftless.request"
SERVICE = Path(__file__).resolve().parents[1]
LOG_CONFIG = SERVICE / "deploy" / "logging.json"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    # A file, not in-memory: TestClient serves the request on another thread.
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    session_factory = new_session_factory(engine)
    with session_factory() as session:

        def _session() -> Iterator[Session]:
            yield session

        app.dependency_overrides[get_session] = _session
        yield TestClient(app)
        app.dependency_overrides.clear()


def _lines(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == LOGGER]


def test_a_request_logs_exactly_one_json_line(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert client.get("/businesses").status_code == 200
    (line,) = _lines(caplog)
    assert set(line) == {"ts", "method", "path", "status", "duration_ms", "client"}
    assert line["method"] == "GET" and line["path"] == "/businesses" and line["status"] == 200
    assert isinstance(line["duration_ms"], float) and line["duration_ms"] >= 0


def test_a_missing_route_logs_its_status(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    client.get("/no-such-route")
    (line,) = _lines(caplog)
    assert line["status"] == 404 and line["path"] == "/no-such-route"


def test_neither_the_query_string_nor_the_token_is_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    client.get("/businesses?secret=leak", headers={"Authorization": "Bearer hunter2"})
    (record,) = [r for r in caplog.records if r.name == LOGGER]
    emitted = record.getMessage().lower()
    assert "leak" not in emitted and "hunter2" not in emitted and "authorization" not in emitted


def test_nothing_is_emitted_at_the_default_level(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Verbosity is the operator's `logging` level, so tests and quiet runs stay silent."""
    client.get("/businesses")
    assert _lines(caplog) == []


# --- the deployment's side of "quiet by default" -----------------------------
#
# The tests above prove the module. These prove the *shipped configuration*: the
# image's CMD must hand uvicorn a document that raises `driftless.request`, and
# that document must ship. Without one the container is silent by the contract
# above, and "what happened at 3am?" has no answer at all.


@pytest.fixture
def shipped_config() -> Iterator[io.StringIO]:
    """Apply `deploy/logging.json` the way the container does, into a buffer we can read.

    `uvicorn --log-config <file>.json` is `json.load` then `logging.config.dictConfig`,
    so this drives the same document through the same call. The only thing changed is
    the destination — a test cannot read the container's stdout — while the levels,
    formatters and handler classes stay the shipped ones. Restored on the way out, or
    every logging test after this one would inherit the deployment's configuration.
    """
    document = json.loads(LOG_CONFIG.read_text(encoding="utf-8"))
    loggers = {name: logging.getLogger(name) for name in ("", *document["loggers"])}
    saved = {n: (lg.level, lg.handlers[:], lg.propagate, lg.disabled) for n, lg in loggers.items()}
    logging.config.dictConfig(document)
    buffer = io.StringIO()
    for logger in loggers.values():
        for handler in logger.handlers:
            handler.setStream(buffer)  # type: ignore[attr-defined]
    try:
        yield buffer
    finally:
        for name, (level, handlers, propagate, disabled) in saved.items():
            logger = loggers[name]
            logger.setLevel(level)
            logger.handlers, logger.propagate, logger.disabled = handlers, propagate, disabled


def test_the_image_hands_uvicorn_a_log_config_it_actually_carries() -> None:
    """Two halves, both required, and both readable without building an image.

    Docker is not available here, so the honest assertion is on the shipped artefacts
    rather than on a running container: the CMD names a `--log-config` path, and the
    image's own COPY instructions put a file at exactly that path. A CMD naming a file
    no COPY carries is worse than no flag — uvicorn exits, and the container crash-loops.
    """
    cmd = json.loads(next(rest for head, rest in _instructions() if head == "CMD"))
    assert "--log-config" in cmd, (
        "the shipped CMD starts uvicorn with its default logging configuration, which "
        "knows nothing about driftless.request, so the container emits no request line "
        "at all and an operator cannot tell a failed request from a slow one"
    )
    path = cmd[cmd.index("--log-config") + 1]
    supplied = image_paths()
    assert path in supplied, (
        f"CMD passes --log-config {path}, which no COPY puts in the image: "
        f"uvicorn exits at startup. Copy it by name, as the entrypoint is."
    )
    assert (SERVICE / supplied[path]).exists()


def test_the_shipped_config_turns_the_request_log_on(
    client: TestClient, shipped_config: io.StringIO
) -> None:
    """The point of the whole change: under the deployment's document, a request logs.

    The whole line parses as JSON, which is the formatter's job — `docker logs … | jq`
    is how the operator asks "which requests failed, and how slow were they?", and a
    level/name prefix spliced in front of the line would break every one of those.
    """
    assert client.get("/businesses").status_code == 200
    (raw,) = [line for line in shipped_config.getvalue().splitlines() if "/businesses" in line]
    line = json.loads(raw)
    assert line["method"] == "GET" and line["status"] == 200
    assert isinstance(line["duration_ms"], float) and line["client"]


def test_the_shipped_config_cannot_print_a_query_string_or_a_header() -> None:
    """Structural, not a promise: no configured formatter has a field to leak one into.

    A `logging` format string can only interpolate `LogRecord` attributes, so the four
    allowed here cannot carry a header — and holding `uvicorn.access` above INFO removes
    the one line in the shipped image that *would* carry a query string: uvicorn builds
    its access line from the raw request target (`get_path_with_query_string`,
    uvicorn/protocols/utils.py), where `driftless.request` logs `request.url.path`.
    After this, the container's only per-request line is the one that drops the query.
    """
    document = json.loads(LOG_CONFIG.read_text(encoding="utf-8"))
    for name, formatter in document["formatters"].items():
        fields = set(re.findall(r"%\((\w+)\)", formatter["format"]))
        assert fields <= {"asctime", "levelname", "name", "message"}, f"{name} widens the line"
    access = logging.getLevelName(document["loggers"]["uvicorn.access"]["level"])
    assert access >= logging.WARNING, (
        "uvicorn's access line carries the query string, which driftless.request drops "
        "deliberately; raising it here would put `?token=…` back in the container log"
    )


def test_the_shipped_config_also_stamps_the_warnings(
    shipped_config: io.StringIO,
) -> None:
    """`DRIFTLESS_API_TOKEN is unset — the API is running open` reaches stderr today
    through `logging.lastResort`: no timestamp, no level, no logger name, an unattributed
    sentence among uvicorn's formatted lines. The document gives the whole `driftless`
    tree a handler, so a warning says when it happened and who said it."""
    logging.getLogger("driftless.secure").warning("running open")
    emitted = shipped_config.getvalue()
    assert "WARNING" in emitted and "driftless.secure" in emitted and "running open" in emitted
