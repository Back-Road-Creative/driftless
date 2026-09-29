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
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient
from test_docs_agent_guide import FENCED, PASSWORD, SHARED, Block, Guide, blocks

from driftless.api.app import app
from driftless.api.secure import TokenGate
from driftless.auth import sessions
from driftless.auth.passwords import hash_password
from driftless.db import Base, new_engine, new_session_factory
from driftless.db import session as db_session
from driftless.db.changelog import register_changelog
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload
from driftless.models import User
from driftless.pmbok.graph import EdgeKind
from driftless.web.method_map import TIE_VERB

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "user-guide.md"
PAIR = re.compile(r'name="csrf_token" value="([^"]+)"')
STYLES = Path(__file__).resolve().parents[1] / "driftless" / "web" / "static" / "driftless.css"
#: The guide's own account of what each dash pattern means, sliced by its first and
#: last sentence so a rewrite that drops the passage fails here rather than passing
#: vacuously on a guide that no longer explains the map at all.
DASHES = re.compile(r"The \*\*dashes\*\* carry.*?(?=\n\nA tie drawn)", re.S)


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
    monkeypatch.setattr(db_session, "_factory", factory)
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


def test_the_user_guide_explains_the_breadcrumb_trail() -> None:
    """The Method pages hang off the primary nav AND off a project's own history;
    a reader following either path needs the trail explained, not just the pages
    it links to left as bare addresses."""
    assert "breadcrumb" in GUIDE.read_text().lower()


def test_the_guide_says_what_every_tie_the_map_can_draw_looks_like() -> None:
    """``edge_legend`` builds a legend row per ``EdgeKind`` for free, so a new kind
    reaches the screen explained. The printed guide is hand-written and does not,
    which is how ``part_of`` came to be drawn but never described. Assert it."""
    passage = DASHES.search(GUIDE.read_text())
    assert passage, "the guide no longer explains what the map's dash patterns mean"

    undescribed = [verb for verb in TIE_VERB.values() if verb not in passage[0]]
    assert not undescribed, f"the guide never says which line {undescribed} is drawn with"


def test_every_tie_the_guide_describes_is_a_dash_pattern_the_stylesheet_draws() -> None:
    """The guide's promise is that the dash pattern is the ONLY thing carrying a tie's
    kind. That holds only while each kind owns a distinct ``stroke-dasharray``."""
    rules = {
        kind: re.search(rf"\.edge-{kind} {{[^}}]*stroke-dasharray: ([^;]+);", STYLES.read_text())
        for kind in get_args(EdgeKind)
    }
    missing = sorted(kind for kind, rule in rules.items() if rule is None)
    assert not missing, f"{missing} is drawn with no dash pattern of its own"

    patterns = [rule[1].strip() for rule in rules.values() if rule]
    assert len(set(patterns)) == len(patterns), f"two ties share a dash pattern: {patterns}"
