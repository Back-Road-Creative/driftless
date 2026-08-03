"""The expected-revision constant, and the readiness probe that reads it.

The first test is the one that matters: it walks the real migration chain with
Alembic's own resolver and asserts it equals ``KNOWN_REVISIONS``. The constant
therefore cannot drift — the next migration fails this test until it is
appended — which is what makes a hardcoded revision safe in a package that
deliberately does not ship ``alembic/``.

The rest exercise the two health routes against databases stamped at head, at an
earlier revision, at a revision this code has never heard of, never migrated at
all, and unreachable. Both unreachable cases assert the body *exactly*, because
"no driver text, no DSN, no credentials" is the property being pinned — and it
binds harder on ``/health``, which answers anyone who can reach the port.

The split between them is the point: ``/health`` asks only whether the store
answered, so it can stay outside the credential gate and back the container
healthcheck; ``/health/ready`` adds the revision, which is why it does not.

The last group covers the startup refusal, which is the same *ahead* fact acted
on rather than reported. ``with TestClient(app)`` is what runs the lifespan, so
these enter the client as a context manager where the probe tests do not. The
behind and ``create_all`` cases are the load-bearing ones: every other test in
this suite builds its store one of those two ways, so a check that fired on
either would take the whole suite down with it.
"""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from driftless.api import app as app_module
from driftless.api.app import ALLOW_SCHEMA_AHEAD_ENV, app, get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.schema_version import EXPECTED_REVISION, KNOWN_REVISIONS, SchemaAheadError

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_the_constant_is_the_real_head_of_the_chain() -> None:
    """Base -> head off the scripts themselves; the package cannot read these."""
    script = ScriptDirectory.from_config(_config("sqlite://"))
    chain = tuple(rev.revision for rev in reversed(list(script.walk_revisions())))
    assert chain == KNOWN_REVISIONS, (
        "alembic/versions and driftless/db/schema_version.py disagree — append the new "
        "revision to KNOWN_REVISIONS (the deployed package cannot read alembic/)."
    )
    assert EXPECTED_REVISION == script.get_current_head()


def _client(url: str) -> Iterator[TestClient]:
    with new_session_factory(new_engine(url))() as session:
        app.dependency_overrides[get_session] = lambda: session
        yield TestClient(app)
        app.dependency_overrides.clear()


@pytest.fixture
def at_head(tmp_path: Path) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path / 'ready.db'}"
    command.upgrade(_config(url), "head")
    yield from _client(url)


def test_a_database_at_head_is_ready(at_head: TestClient) -> None:
    resp = at_head.get("/health/ready")
    assert resp.status_code == 200 and resp.json() == {"detail": "ready"}


def test_an_older_revision_reads_as_behind(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'old.db'}"
    command.upgrade(_config(url), KNOWN_REVISIONS[0])
    for client in _client(url):
        resp = client.get("/health/ready")
        assert resp.status_code == 503 and resp.json() == {"detail": "schema behind"}


def test_a_never_migrated_database_reads_as_behind(tmp_path: Path) -> None:
    """Reachable but with no ``alembic_version`` at all — behind, not unreachable."""
    for client in _client(f"sqlite:///{tmp_path / 'empty.db'}"):
        resp = client.get("/health/ready")
        assert resp.status_code == 503 and resp.json() == {"detail": "schema behind"}


def test_an_unknown_revision_reads_as_ahead(at_head: TestClient) -> None:
    """A revision this image has never heard of: the database moved past the code."""
    session: Session = app.dependency_overrides[get_session]()
    session.execute(text("UPDATE alembic_version SET version_num = 'ffffffffffff'"))
    session.commit()
    resp = at_head.get("/health/ready")
    assert resp.status_code == 503 and resp.json() == {"detail": "schema ahead"}


def test_an_unreachable_database_leaks_nothing(tmp_path: Path) -> None:
    """Exact body: no DSN, no credentials, no driver error text — by construction."""
    unopenable = tmp_path / "no-such-dir" / "x.db"
    for client in _client(f"sqlite:///{unopenable}"):
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        assert resp.json() == {"detail": "database unreachable"}


def test_health_says_unhealthy_when_the_store_cannot_answer(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The whole point of the route: a healthcheck that goes red during an outage.

    The store is genuinely unreachable — a real engine over a directory SQLite
    cannot open, the same shape :func:`test_an_unreachable_database_leaks_nothing`
    uses — rather than a stand-in for the code under test.

    Exact body, and the log line carries the exception type and nothing else: this
    route is unauthenticated, so a DSN, a host or driver text reaching either would
    be readable by anyone who can call it.
    """
    unopenable = tmp_path / "no-such-dir" / "x.db"
    for client in _client(f"sqlite:///{unopenable}"):
        with caplog.at_level(logging.WARNING, logger="driftless.api"):
            resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json() == {"status": "unhealthy"}
        assert "OperationalError" in caplog.text
        assert str(unopenable) not in caplog.text and "sqlite" not in caplog.text


def test_health_says_ok_when_the_store_answers(at_head: TestClient) -> None:
    """The healthy body is byte for byte what it always was — no caller re-reads."""
    resp = at_head.get("/health")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}


def test_health_asks_the_store_and_not_the_schema(tmp_path: Path) -> None:
    """A store behind this image is serving fine, so liveness stays green on it.

    Schema currency is deliberately NOT this route's question: *ahead* already
    refuses to start (:func:`refuse_if_schema_ahead`) so no request is served
    against it at all, and *behind* is the ordinary deploy-then-migrate state.
    Answering it here would also disclose schema state without a credential.
    """
    url = f"sqlite:///{tmp_path / 'behind.db'}"
    command.upgrade(_config(url), KNOWN_REVISIONS[0])
    for client in _client(url):
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/health/ready").json() == {"detail": "schema behind"}


def test_readiness_is_gated_while_liveness_stays_credential_free(at_head: TestClient) -> None:
    """Liveness needs no credential; readiness reveals schema state, so it does.

    ``/health`` is answered before auth — it reaches the store, but discloses only
    whether it answered, which is what makes it safe to leave open.
    """
    from driftless.api import secure

    gated = TestClient(secure.TokenGate(app, "s3cr3t-token"))
    assert gated.get("/health").status_code == 200
    assert gated.get("/health/ready").status_code == 401
    allowed = gated.get("/health/ready", headers={"Authorization": "Bearer s3cr3t-token"})
    assert allowed.status_code == 200 and allowed.json() == {"detail": "ready"}


UNKNOWN_REVISION = "ffffffffffff"  # pragma: allowlist secret


def _serving_from(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the app's own lazy factory — what the startup check reads — at ``url``."""
    monkeypatch.setattr(app_module, "_factory", new_session_factory(new_engine(url)))


def _ahead_store(tmp_path: Path) -> str:
    """A store stamped past this image, as a rolled-back deploy meets one.

    Stamped by hand rather than migrated: the stamp is the entire input the check
    reads, and Alembic's ``env.py`` calls ``fileConfig``, which would replace the
    root handlers — ``caplog`` included — out from under the escape-hatch test.
    """
    url = f"sqlite:///{tmp_path / 'ahead.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        session.execute(
            text("INSERT INTO alembic_version VALUES (:rev)"), {"rev": UNKNOWN_REVISION}
        )
        session.commit()
    return url


def test_a_schema_ahead_store_refuses_to_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole unit: the image that cannot read this schema never serves a request."""
    monkeypatch.delenv(ALLOW_SCHEMA_AHEAD_ENV, raising=False)
    _serving_from(_ahead_store(tmp_path), monkeypatch)
    with pytest.raises(SchemaAheadError) as refusal, TestClient(app):
        pass  # pragma: no cover -- startup raises before the body runs
    message = str(refusal.value)
    assert UNKNOWN_REVISION in message and EXPECTED_REVISION in message


def test_a_store_behind_this_image_starts_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behind is the ordinary pre-migration state — deploy the code, then migrate."""
    url = f"sqlite:///{tmp_path / 'behind.db'}"
    command.upgrade(_config(url), KNOWN_REVISIONS[0])
    _serving_from(url, monkeypatch)
    with TestClient(app) as client:
        assert client.get("/health/ready").json() == {"detail": "schema behind"}


def test_an_unstamped_create_all_store_starts_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load-bearing: dev and every other test in the suite build their store this way."""
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    Base.metadata.create_all(new_engine(url))
    _serving_from(url, monkeypatch)
    with TestClient(app) as client:
        assert client.get("/health/ready").json() == {"detail": "schema behind"}


def test_the_escape_hatch_starts_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An override with no record is how a temporary rollback becomes permanent."""
    monkeypatch.setenv(ALLOW_SCHEMA_AHEAD_ENV, "1")
    _serving_from(_ahead_store(tmp_path), monkeypatch)
    with caplog.at_level(logging.WARNING, logger="driftless.api"), TestClient(app) as client:
        assert client.get("/health/ready").json() == {"detail": "schema ahead"}
    assert any(
        UNKNOWN_REVISION in record.getMessage() and ALLOW_SCHEMA_AHEAD_ENV in record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


def test_a_database_that_will_not_answer_still_boots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An outage is readiness's question, not this one's: refusing here is a crash loop."""
    _serving_from(f"sqlite:///{tmp_path / 'no-such-dir' / 'x.db'}", monkeypatch)
    with TestClient(app) as client:
        assert client.get("/health/ready").json() == {"detail": "database unreachable"}
