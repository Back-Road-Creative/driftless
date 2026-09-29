"""``driftless pmbok proof <claim>`` end to end against the seeded demo store —
the same store ``driftless demo seed`` builds, walked here directly through the
validated API (``tests/test_demo_web.py``'s pattern) rather than over HTTP.
"""

import argparse
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.responses import HTMLResponse

from driftless import cli
from driftless.api.app import app as real_app
from driftless.api.app import get_session
from driftless.db import Base, new_engine, new_session_factory
from driftless.demo.cli import seed
from driftless.demo.data import ANCHOR, demo_payload
from driftless.pmbok import cli as pmbok_cli
from driftless.pmbok import proof_checks as pc
from driftless.report.receipt import attach_markdown_receipt
from driftless.web.receipt import attach_receipt


@pytest.fixture
def demo_db_url(tmp_path: Path) -> Iterator[str]:
    """Seed the real demo payload into a throwaway sqlite file and hand back its URL."""
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        real_app.dependency_overrides[get_session] = lambda: session
        try:
            with TestClient(real_app) as client:

                def post(path: str, body: dict[str, object]) -> int:
                    result: int = client.post(path, json=body).json()["id"]
                    return result

                def patch(path: str, body: dict[str, object]) -> None:
                    client.patch(path, json=body)

                seed(post, demo_payload(ANCHOR), patch)
        finally:
            real_app.dependency_overrides.clear()
    yield url


def test_no_typed_status_exits_zero_on_the_demo_store() -> None:
    rc = cli.main(["pmbok", "proof", "no-typed-status"])
    assert rc == 0


def test_baseline_immutable_exits_zero_on_the_demo_store(demo_db_url: str) -> None:
    rc = cli.main(
        ["pmbok", "proof", "baseline-immutable", "Season 4 Rollout", "--db-url", demo_db_url]
    )
    assert rc == 0


def test_forecast_exits_zero_on_the_demo_store(demo_db_url: str) -> None:
    rc = cli.main(
        [
            "pmbok",
            "proof",
            "forecast",
            "Fleet Modernization",
            "--as-of",
            ANCHOR.isoformat(),
            "--db-url",
            demo_db_url,
        ]
    )
    assert rc == 0


def test_process_state_exits_zero_on_the_demo_store(
    demo_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(
        [
            "pmbok",
            "proof",
            "process-state",
            "Season 4 Rollout",
            "--as-of",
            ANCHOR.isoformat(),
            "--db-url",
            demo_db_url,
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK:" in out


def test_forecast_fails_for_a_project_with_no_sprint_history(
    demo_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """``Route Optimization Pilot`` runs predictive with no agile backlog, so the
    proof check itself — not just the CLI wiring — must report the fail branch."""
    rc = cli.main(
        [
            "pmbok",
            "proof",
            "forecast",
            "Route Optimization Pilot",
            "--as-of",
            ANCHOR.isoformat(),
            "--db-url",
            demo_db_url,
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL:" in out
    assert "no completed sprint" in out


def test_baseline_immutable_refuses_a_project_with_no_approved_baseline(
    demo_db_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """``Route Optimization Pilot`` is seeded with no baseline at all."""
    rc = cli.main(
        [
            "pmbok",
            "proof",
            "baseline-immutable",
            "Route Optimization Pilot",
            "--db-url",
            demo_db_url,
        ]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "no approved baseline" in err


def test_baseline_immutable_returns_2_for_an_unknown_project(demo_db_url: str) -> None:
    rc = cli.main(
        ["pmbok", "proof", "baseline-immutable", "No Such Project", "--db-url", demo_db_url]
    )
    assert rc == 2


def test_forecast_returns_2_for_an_unknown_project(demo_db_url: str) -> None:
    rc = cli.main(["pmbok", "proof", "forecast", "No Such Project", "--db-url", demo_db_url])
    assert rc == 2


def test_process_state_returns_2_for_an_unknown_project(demo_db_url: str) -> None:
    rc = cli.main(["pmbok", "proof", "process-state", "No Such Project", "--db-url", demo_db_url])
    assert rc == 2


def test_open_project_refuses_with_no_database_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("DRIFTLESS_DATABASE_URL", "PMHUB_DATABASE_URL", "PMHUB_DB_URL"):
        monkeypatch.delenv(name, raising=False)
    result = pmbok_cli._open_project(argparse.Namespace(db_url=None, project="anything"))
    assert result is None
    assert "no database URL" in capsys.readouterr().err


def test_reproduce_passes_on_an_untouched_markdown_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.md"
    report.write_text(attach_markdown_receipt("# Title\n\nsome body\n", ANCHOR), encoding="utf-8")
    rc = cli.main(["pmbok", "proof", "reproduce", str(report)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK:" in out


def test_reproduce_fails_on_a_one_byte_edit_to_a_markdown_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipted = attach_markdown_receipt("# Title\n\nsome body\n", ANCHOR)
    report = tmp_path / "report.md"
    report.write_text(receipted.replace("some body", "some bod1"), encoding="utf-8")
    rc = cli.main(["pmbok", "proof", "reproduce", str(report)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL:" in out


def test_reproduce_fails_with_no_receipt_in_a_markdown_looking_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.md"
    report.write_text("# Title\n\nno receipt here\n", encoding="utf-8")
    rc = cli.main(["pmbok", "proof", "reproduce", str(report)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL:" in out
    assert "no receipt found" in out


def test_reproduce_passes_on_an_untouched_saved_html_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = b"<html><body><main>hello</main></body></html>"
    response = HTMLResponse(content=body)
    attach_receipt(response, date(2026, 9, 22))
    page = tmp_path / "page.html"
    page.write_text(bytes(response.body).decode("utf-8"), encoding="utf-8")
    rc = cli.main(["pmbok", "proof", "reproduce", str(page)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK:" in out


def test_reproduce_fails_on_a_one_byte_edit_to_a_saved_html_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = b"<html><body><main>hello</main></body></html>"
    response = HTMLResponse(content=body)
    attach_receipt(response, date(2026, 9, 22))
    tampered = bytes(response.body).decode("utf-8").replace("hello", "hellO")
    page = tmp_path / "page.html"
    page.write_text(tampered, encoding="utf-8")
    rc = cli.main(["pmbok", "proof", "reproduce", str(page)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL:" in out


def test_reproduce_fails_with_no_receipt_in_an_html_looking_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    page = tmp_path / "page.html"
    page.write_text("<html><body>no receipt here</body></html>", encoding="utf-8")
    rc = cli.main(["pmbok", "proof", "reproduce", str(page)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "no receipt found" in out


def test_reproduce_returns_2_for_an_unreadable_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(["pmbok", "proof", "reproduce", str(tmp_path / "does-not-exist.md")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "cannot read" in err


def test_run_no_typed_status_returns_1_when_the_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pmbok_cli.proof_checks,
        "check_no_typed_status",
        lambda columns: pc.ProofCheck("claim", False, ("Project.percent_complete",)),
    )
    rc = pmbok_cli._run_no_typed_status(argparse.Namespace())
    assert rc == 1
