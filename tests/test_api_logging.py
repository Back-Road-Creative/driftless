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
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_docker_build_context import _instructions, image_paths

from driftless.api.app import app, get_session
from driftless.api.logging import REQUEST_ID_HEADER, install_request_log
from driftless.db import Base, new_engine, new_session_factory
from driftless.web.errors import install_page_errors

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
    assert set(line) == {"ts", "method", "path", "status", "duration_ms", "client", "request_id"}
    assert line["method"] == "GET" and line["path"] == "/businesses" and line["status"] == 200
    assert isinstance(line["duration_ms"], float) and line["duration_ms"] >= 0
    assert isinstance(line["request_id"], str) and line["request_id"]


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


# --- request-id correlation ---------------------------------------------------
#
# The line above says who asked and how long it took; it says nothing that ties
# that line to the response the caller actually held. These pin the token that
# closes the loop: generated when the caller supplies none, honoured when it
# does, and always both logged and echoed back.


def test_a_request_with_no_inbound_id_gets_one_generated_and_echoed(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    response = client.get("/businesses")
    (line,) = _lines(caplog)
    assert response.headers[REQUEST_ID_HEADER] == line["request_id"]
    assert line["request_id"]


def test_a_well_formed_inbound_id_is_honoured_not_replaced(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    response = client.get("/businesses", headers={REQUEST_ID_HEADER: "caller-supplied-id-123"})
    (line,) = _lines(caplog)
    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id-123"
    assert line["request_id"] == "caller-supplied-id-123"


@pytest.mark.parametrize(
    "supplied",
    [
        'bad"id',  # a quote could close the JSON string early
        "bad\nid",  # a newline would forge a second, unrelated log line
        'bad,id\r\n{"forged": true}',  # a full forged record appended to the stream
        "x" * 129,  # one past the length this module accepts
        "",  # an empty header is not a usable token either
    ],
)
def test_a_malformed_inbound_id_is_replaced_not_logged_verbatim(
    client: TestClient, caplog: pytest.LogCaptureFixture, supplied: str
) -> None:
    """An inbound header is untrusted input reaching a JSON log line and a response
    header, so anything outside the accepted shape is replaced wholesale rather than
    echoed — escaping it would still hand a caller-chosen string to the log, and this
    module draws the line at generating a fresh one instead."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    response = client.get("/businesses", headers={REQUEST_ID_HEADER: supplied})
    (line,) = _lines(caplog)
    assert line["request_id"] != supplied
    assert response.headers[REQUEST_ID_HEADER] == line["request_id"]
    # The line must still be exactly one JSON object — a forged newline or quote
    # would otherwise either break `json.loads` or smuggle a second record in.
    (raw_record,) = [r for r in caplog.records if r.name == LOGGER]
    assert raw_record.getMessage().count("\n") == 0
    json.loads(raw_record.getMessage())


def test_operations_lists_exactly_the_fields_the_log_actually_emits(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """``OPERATIONS.md``'s *Request log* section names the fields an operator will find
    in a line, and a hand-maintained list of that kind rots silently: it was stale by one
    field the moment ``request_id`` was added, and nothing said so.

    So every key of a line the middleware really emitted must appear somewhere in that
    section. Deliberately "somewhere" and not "in the comma-separated list": a field
    explained in a paragraph of its own is documented, and pinning the sentence shape
    would fail on a rewrite that improved it. What cannot pass is a field the section
    never mentions at all — an operator reading it would not know to look for the field,
    or what it means. The claim is always read off a real line, never off the prose.
    """
    caplog.set_level(logging.INFO, logger=LOGGER)
    assert client.get("/businesses").status_code == 200
    (line,) = _lines(caplog)
    section = (SERVICE / "OPERATIONS.md").read_text(encoding="utf-8").split("\n## Request log")[1]
    documented = set(re.findall(r"`([a-z_]+)`", section.split("\n## ")[0]))
    assert set(line) <= documented, (
        f"the request log emits {sorted(set(line) - documented)}, which OPERATIONS.md's "
        "Request log section never names — an operator reading that section would not "
        "know to look for the field, or what it means"
    )


def test_a_raising_route_still_logs_its_request_id(caplog: pytest.LogCaptureFixture) -> None:
    """The `finally` shape carries the id through the same path it carries `status`
    through: a route that raises past this middleware is answered from above it
    (`ServerErrorMiddleware`), so there is no response here to stamp a header on, but
    the id was already resolved before `call_next` and the log line still carries it.
    A throwaway app, as `tests/test_request_log_failures.py` uses, because a route
    that always explodes does not belong on the service's own app.
    """
    caplog.set_level(logging.INFO, logger=LOGGER)
    exploding = FastAPI()

    @exploding.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("the route exploded")

    install_request_log(exploding)
    client = TestClient(exploding, raise_server_exceptions=False)

    response = client.get("/boom", headers={REQUEST_ID_HEADER: "caller-supplied-id-123"})
    assert response.status_code == 500
    (line,) = _lines(caplog)
    assert line["status"] == 500
    assert line["request_id"] == "caller-supplied-id-123"


def test_a_raising_route_answers_its_500_with_the_same_id_it_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The gap the log-only version above leaves: an operator reading the log line
    above can tie it to *a* request, but the user holding the 500 has nothing on the
    response to quote back unless the id also lands on the header the error handler
    (`driftless.web.errors.page_server_error`) builds — the one thing that ever does
    answer a raising route, sitting above this middleware in the stack.
    """
    caplog.set_level(logging.INFO, logger=LOGGER)
    exploding = FastAPI()

    @exploding.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("the route exploded")

    install_request_log(exploding)
    install_page_errors(exploding)
    client = TestClient(exploding, raise_server_exceptions=False)

    response = client.get("/boom", headers={REQUEST_ID_HEADER: "caller-supplied-id-123"})
    assert response.status_code == 500
    (line,) = _lines(caplog)
    assert response.headers[REQUEST_ID_HEADER] == line["request_id"] == "caller-supplied-id-123"


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
