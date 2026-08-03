"""``docs/admin-guide.md`` is executed, not just written — ``test_docs_agent_guide``'s runner, reused,
plus the one thing an operator's guide needs that an agent's does not: a step no unit test can run (a
host, TLS, ``pg_dump`` against a live Postgres) carries a ``manual`` marker naming **why**, counted
and reported rather than faked — and held to :data:`MANUAL_BLOCKS`, an exact allowlist, so an
excused command cannot drift unnoticed. Unchanged: a fence with no marker fails, so no command
reaches the guide unrun *and* unexcused. The readiness answers need a store stamped three ways, so the marker
carries that precondition (``stamped=``); and ``driftless demo seed`` talks HTTP, so the transport —
only the transport — is the TestClient, every row it posts going through the real validated API.
"""

from __future__ import annotations

import io
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_docs_agent_guide import FENCED, PASSWORD, SHARED, Block, Guide, blocks

from driftless.api import app as app_module
from driftless.api.app import app
from driftless.api.secure import TokenGate
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "admin-guide.md"

#: Every block excused from execution, by its opening command — compared as an EXACT
#: set, so adding a manual escape, dropping one, or editing an excused command (the
#: wrong `git clone` of F-X1 drifted through the old bare count) must edit this list
#: in the same change, where a reviewer sees it.
MANUAL_BLOCKS = frozenset(
    {
        "git clone https://github.com/Back-Road-Creative/driftless.git && cd driftless",
        'export PGPASSWORD="$POSTGRES_PASSWORD"',
        "docker compose stop driftless-app",
    }
)


@dataclass
class Admin(Guide):  # the agent guide's runner, plus the kinds an operator's steps need
    manual: list[str] = field(default_factory=list)
    manual_ids: list[str] = field(default_factory=list)

    def run(self, block: Block) -> None:
        if "stamped" in block.attrs:  # this answer is about the store's own schema state
            self._stamp(block.attrs["stamped"])
        runner = {"manual": self._manual, "text": self._text}.get(block.kind)
        runner(block) if runner else super().run(block)

    def _manual(self, block: Block) -> None:  # not executed — but only against a stated reason
        why = block.attrs.get("why", "")
        assert len(why) >= 20, f"{block.where} is manual with no substantive why=: {why!r}"
        self.manual.append(f"{block.where} — {why}")
        self.manual_ids.append(block.body.strip().splitlines()[0])

    def _stamp(self, revision: str) -> None:
        """Stamp ``alembic_version`` — ``none`` for a store never migrated at all."""
        with self.factory() as db:
            db.execute(text("DROP TABLE IF EXISTS alembic_version"))
            if revision != "none":
                db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
                db.execute(text("INSERT INTO alembic_version VALUES (:rev)"), {"rev": revision})
            db.commit()

    def _text(self, block: Block) -> None:  # a line at a time: `user list` ends in a timestamp
        missing = [line for line in block.body.strip().splitlines() if line not in self.raw]
        assert not missing, f"{block.where} is not in the answer: {missing} vs {self.raw!r}"


@pytest.fixture
def admin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Admin]:
    """A throwaway store wired in as the app's own factory, exactly as the API builds it."""
    engine = new_engine(url := f"sqlite:///{tmp_path / 'admin.db'}")
    Base.metadata.create_all(engine)
    register_changelog(factory := new_session_factory(engine))
    monkeypatch.setattr(app_module, "_factory", factory)
    client = TestClient(TokenGate(app, SHARED))

    def urlopen(request: urllib.request.Request, *args: object, **kwargs: object) -> io.BytesIO:
        """``driftless demo seed``'s only socket, answered by this app in this process."""
        assert isinstance(body := request.data, bytes)
        path = urllib.parse.urlsplit(request.full_url).path
        headers = dict(request.header_items())
        answer = client.request(request.get_method(), path, headers=headers, content=body)
        answer.raise_for_status()  # a refused row fails here, not as a missing "id"
        return io.BytesIO(answer.content)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    tokens = dict.fromkeys(("DRIFTLESS_TOKEN", "DRIFTLESS_API_TOKEN"), SHARED)  # the shared bearer
    passwords = {"ADMIN_PW": PASSWORD, "OPS_PW": PASSWORD}
    yield Admin(client, factory, monkeypatch, {"DRIFTLESS_DATABASE_URL": url} | tokens | passwords)


def test_the_admin_guide_runs_exactly_as_it_is_written(admin: Admin) -> None:
    written = GUIDE.read_text()
    unmarked = [
        written[: fence.start()].count("\n") + 1
        for fence in FENCED.finditer(written)
        if not written[: fence.start()].endswith("-->\n")
    ]
    assert not unmarked, f"admin-guide.md lines {unmarked}: a fenced block with no run marker"

    marked = blocks(written, "admin-guide.md")
    for block in marked:
        admin.run(block)
    ran = len(marked) - len(admin.manual)
    print(f"\n{ran} blocks run, {len(admin.manual)} manual:\n" + "\n".join(admin.manual))
    drift = set(admin.manual_ids) ^ MANUAL_BLOCKS
    assert not drift, f"manual blocks differ from MANUAL_BLOCKS by: {drift}"
    assert ran >= 20, f"only {ran} of {len(marked)} ran; the rest are excused as manual"
