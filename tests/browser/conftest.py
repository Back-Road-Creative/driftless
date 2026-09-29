"""A real browser against a real server — the tier the static gates cannot reach.

Everything else in ``tests/`` reads HTML as text. That answers a great deal
(``test_web_a11y`` does contrast ratios on the token block, ``test_web_responsive``
proves nothing is clipped and one breakpoint is declared) and it deliberately
stops short of layout: ``test_web_responsive``'s own docstring says "no test here
renders a viewport". Where the flex rows choose to wrap, whether a scrolled table
reads under a thumb, whether the count-up honours a reduced-motion preference --
those need a rendering engine.

This tier is OPT-IN and is not collected by the default suite (see the --ignore in
pyproject's addopts). It does NOT supersede ``bin/driftless-snapshot-pages.py``,
whose header argues against a browser dependency: the byte-diffable snapshots stay
the required floor and this runs beside them, on demand and nightly.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
import uvicorn
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import create_app, get_session
from driftless.db import Base, new_engine, new_session_factory

AS_OF = date(2026, 3, 31)
JAN = date(2026, 1, 31)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="session")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Session]:
    """One project with a costed, half-complete baseline: enough that every page
    under check renders rows rather than an empty state. Session-scoped because
    the server below serves it and starting one per test would dominate the run."""
    path: Path = tmp_path_factory.mktemp("browser") / "driftless.db"
    engine = new_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        portfolio = m.Portfolio(name="Content Brands", business=m.Business(name="BRC"))
        project = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
        stream = m.Workstream(name="GMS", project=project)
        task = m.Task(name="GMS", workstream=stream, estimate_unit="hours", percent_complete=50)
        baseline = m.Baseline(project=project, version=1, status="approved")
        line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
        line.planned_start, line.planned_finish = JAN, AS_OF
        session.add(line)
        session.add(m.CostEntry(project=project, category="labour", incurred_on=JAN, amount=400.0))
        session.commit()
        yield session


@pytest.fixture(scope="session")
def base_url(seeded: Session) -> Iterator[str]:
    """The whole app on a loopback port: the same ``create_app()`` the container
    runs, so the pages under check carry the real nav, the real /static CSS and the
    real scripts. Nothing is mounted by hand here -- a page that renders only
    because the test wired it up would prove nothing about the product."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: seeded
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    else:  # pragma: no cover - opt-in tier, not measured by the coverage floor
        raise RuntimeError("the browser tier's uvicorn server never came up")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
