"""``docs/user-guide.md`` is executed, not just written — ``test_docs_agent_guide``'s runner
plus the two kinds a reader's guide needs and an agent's does not: ``signin``, the real form
submitted with the CSRF pair the login page itself handed out, and ``page``, one address
opened as that signed-in browser carrying a cookie and no header at all. Every block reads a
store the demo seeder built through the validated API, so a screen, a label or an empty state
that stops being true fails here and not in front of the person who trusted it. Unchanged: a
fence with no marker fails, so no screen reaches the guide undescribed and unopened.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_docs_agent_guide import FENCED, PASSWORD, SHARED, Block, Guide, blocks

from driftless.api import app as app_module
from driftless.api.app import app
from driftless.api.secure import TokenGate
from driftless.auth import sessions
from driftless.auth.passwords import hash_password
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload
from driftless.models import User

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "user-guide.md"
PAIR = re.compile(r'name="csrf_token" value="([^"]+)"')


@dataclass
class Reader(Guide):  # the agent guide's runner, plus the kinds a browser's steps need
    def run(self, block: Block) -> None:
        runner = {"signin": self._signin, "page": self._page}.get(block.kind)
        runner(block) if runner else super().run(block)

    def _answered(self, block: Block, answer: Any) -> None:
        want, got = int(block.attrs["status"]), answer.status_code
        assert got == want, f"{block.where} documents {want}, got {got}: {answer.text[:200]}"
        self.raw = answer.text

    def _signin(self, block: Block) -> None:
        """What the reader types, submitted with the pair the form itself minted."""
        field = PAIR.search(self.client.get("/login").text)
        assert field, f"{block.where}: the sign-in form rendered no CSRF field"
        typed = dict(line.split(": ", 1) for line in self.expand(block.body).strip().splitlines())
        form = {name.lower(): value for name, value in typed.items()} | {"csrf_token": field[1]}
        self._answered(block, self.client.post("/login", data=form))

    def _page(self, block: Block) -> None:
        """One address, opened as the signed-in browser — the cookie, never a header."""
        self._answered(block, self.client.get(self.expand(block.body).strip()))


@pytest.fixture
def reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Reader]:
    """The demo store behind the real gate, and one contributor login to read it with."""
    engine = new_engine(f"sqlite:///{tmp_path / 'user.db'}")
    Base.metadata.create_all(engine)
    register_changelog(factory := new_session_factory(engine))
    monkeypatch.setattr(app_module, "_factory", factory)
    monkeypatch.setenv(sessions.SECRET_ENV, SHARED)
    monkeypatch.setenv("DRIFTLESS_COOKIE_SECURE", "0")  # the TestClient speaks plain HTTP
    with factory() as db:
        db.add(User(username="dana", password_hash=hash_password(PASSWORD), role="contributor"))
        db.commit()
    client = TestClient(TokenGate(app, SHARED))
    head = {"Authorization": f"Bearer {SHARED}"}  # seeding is the operator's job, not the reader's

    def post(path: str, body: dict[str, Any]) -> int:
        answer = client.post(path, json=body, headers=head)
        answer.raise_for_status()  # a refused row fails here, not as a missing "id"
        return int(answer.json()["id"])

    def patch(path: str, body: dict[str, Any]) -> None:
        client.patch(path, json=body, headers=head).raise_for_status()

    seed(post, demo_payload(ANCHOR), patch)
    yield Reader(client, factory, monkeypatch, {"USER_PASSWORD": PASSWORD})


def test_the_user_guide_runs_exactly_as_it_is_written(reader: Reader) -> None:
    written = GUIDE.read_text()
    unmarked = [
        written[: fence.start()].count("\n") + 1
        for fence in FENCED.finditer(written)
        if not written[: fence.start()].endswith("-->\n")
    ]
    assert not unmarked, f"user-guide.md lines {unmarked}: a fenced block with no run marker"

    marked = blocks(written, "user-guide.md")
    assert len(marked) >= 15, f"only {len(marked)} runnable blocks — the guide lost its markers"
    for block in marked:
        reader.run(block)
