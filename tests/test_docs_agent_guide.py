"""``docs/agent-guide.md`` is executed, not just written: every fenced block carries a
``<!-- driftless:run … -->`` marker, and this runs them all in document order against a real
app and a throwaway store — ``cli`` blocks through ``driftless.cli.main``, ``http`` blocks
through the real ``TokenGate``. A documented status, field or column that stops being true
fails here, not in somebody's integration. The marker is required (a regex guessing which
block runs would rot) and a fence carrying none fails too, so no command reaches the guide
unrun.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import shlex
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from driftless import cli
from driftless.api import app as app_module
from driftless.api.app import app
from driftless.api.secure import TokenGate
from driftless.db import Base, new_engine, new_session_factory
from driftless.db.changelog import register_changelog

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "agent-guide.md"
MARKED = re.compile(r"<!-- driftless:run (\w+)([^>]*)-->\n```[a-z]*\n(.*?)```", re.S)
FENCED = re.compile(r"```[a-z]+\n")  # an opening fence; the closing one carries no language
HEADERS = {"Authorization": "Bearer $DRIFTLESS_TOKEN", "Content-Type": "application/json"}
SHARED = "shared-bootstrap-token"  # pragma: allowlist secret  (in-test gate token)
PASSWORD = "correct horse battery"  # pragma: allowlist secret  (throwaway in-test password)


class Block(NamedTuple):
    kind: str
    attrs: dict[str, str]
    body: str
    where: str  # file:line and the block's first line, so a failure names itself


def blocks(md: str, name: str = "agent-guide.md") -> list[Block]:  # in document order, labelled
    found: list[Block] = []
    for m in MARKED.finditer(md):
        line, first = md[: m.start()].count("\n") + 1, m[3].splitlines()[0]
        attrs = dict(pair.split("=", 1) for pair in shlex.split(m[2]))  # a quoted value survives
        found.append(Block(m[1], attrs, m[3], f"{name}:{line} ({m[1]}, {first!r})"))
    return found


def leaves(value: Any, path: str = "") -> dict[str, Any]:
    """Every scalar in ``value``, keyed by its path: a documented payload is a subset."""
    if isinstance(value, dict):
        items = [(f"{path}.{key}", item) for key, item in value.items()]
    elif isinstance(value, list):
        items = [(f"{path}[{index}]", item) for index, item in enumerate(value)]
    else:
        return {path: value}
    return {k: v for sub, item in items for k, v in leaves(item, sub).items()}


@dataclass
class Guide:  # the guide's execution state: the variables it names, and the last answer
    client: TestClient
    factory: sessionmaker[Session]
    monkeypatch: pytest.MonkeyPatch
    variables: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    def expand(self, source: str) -> str:
        for name, value in self.variables.items():
            source = source.replace(f"${name}", value)
        return source

    def run(self, block: Block) -> None:
        runners = {"cli": self._cli, "http": self._http, "sql": self._sql, "json": self._json}
        runners.get(block.kind, self._text)(block)

    def _cli(self, block: Block) -> None:
        piped, _, command = self.expand(block.body).strip().rpartition("| ")
        if piped:  # `echo "$SECRET" | driftless …`: the password arrives on stdin, never argv
            self.monkeypatch.setattr("sys.stdin", io.StringIO(shlex.split(piped)[1] + "\n"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(shlex.split(command)[1:])
        assert code == int(block.attrs["exit"]), f"{block.where} exited {code}: {out.getvalue()}"
        self.raw = out.getvalue()
        if "capture" in block.attrs:
            self.variables[block.attrs["capture"]] = self.raw.strip()

    def _http(self, block: Block) -> None:
        head, _, body = self.expand(block.body).partition("\n\n")
        request, *given = head.splitlines()
        method, path = request.split()
        merged = HEADERS | dict(line.split(": ", 1) for line in given)
        headers = {name: self.expand(value) for name, value in merged.items()}
        answer = self.client.request(method, path, headers=headers, content=body.strip() or None)
        want, got = int(block.attrs["status"]), answer.status_code
        assert got == want, f"{block.where} documents {want}, got {got}: {answer.text}"
        self.raw = answer.text

    def _sql(self, block: Block) -> None:
        with self.factory() as db:
            rows = db.execute(text(self.expand(block.body).strip()))
            self.raw = json.dumps([dict(row._mapping) for row in rows], default=str)

    def _json(self, block: Block) -> None:
        answered, gone = leaves(json.loads(self.raw)), "<no such path in the answer>"
        documented = leaves(json.loads(block.body)).items()
        wrong = {p: (v, answered.get(p, gone)) for p, v in documented if answered.get(p, gone) != v}
        assert not wrong, f"{block.where} — documented vs answered: {wrong}"

    def _text(self, block: Block) -> None:
        answer = self.raw.replace("\r\n", "\n")  # CSV ends its rows CRLF; no fence carries one
        assert block.body.strip() in answer, f"{block.where} is not in the answer: {answer!r}"


@pytest.fixture
def guide(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Guide]:
    """A throwaway store wired in as the app's own factory, exactly as the API builds it."""
    engine = new_engine(url := f"sqlite:///{tmp_path / 'guide.db'}")
    Base.metadata.create_all(engine)
    register_changelog(factory := new_session_factory(engine))
    monkeypatch.setattr(app_module, "_factory", factory)
    client = TestClient(TokenGate(app, SHARED))  # no default credential: each block shows its own
    variables = {"DRIFTLESS_DATABASE_URL": url, "AGENT_PASSWORD": PASSWORD}
    yield Guide(client, factory, monkeypatch, variables)


def test_the_agent_guide_runs_exactly_as_it_is_written(guide: Guide) -> None:
    written = GUIDE.read_text()
    unmarked = [
        written[: fence.start()].count("\n") + 1
        for fence in FENCED.finditer(written)
        if not written[: fence.start()].endswith("-->\n")
    ]
    assert not unmarked, f"agent-guide.md lines {unmarked}: a fenced block with no run marker"

    marked = blocks(written)
    assert len(marked) >= 15, f"only {len(marked)} runnable blocks — the guide lost its markers"
    for block in marked:
        guide.run(block)
