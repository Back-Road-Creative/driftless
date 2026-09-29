"""The reproducibility receipt on CLI markdown reports (``driftless.report.receipt``)
and the ``X-Driftless-Receipt`` header on CSV exports — same digest and git-sha
primitives as the web page footer (``driftless.web.receipt``), never a second
hashing implementation (``driftless.calc.receipt``)."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from driftless import models as m
from driftless.api.app import app, get_session
from driftless.calc import receipt as calc_receipt
from driftless.db import Base, new_engine, new_session_factory
from driftless.report import cli
from driftless.report.receipt import attach_markdown_receipt, verify_receipt

AS_OF = date(2026, 3, 31)


def test_attach_markdown_receipt_appends_a_trailing_html_comment() -> None:
    text = "# Title\n\nsome body\n"
    receipted = attach_markdown_receipt(text, AS_OF)
    assert receipted.startswith(text)
    assert receipted.rstrip().endswith("-->")
    assert "2026-03-31" in receipted
    assert calc_receipt.GIT_SHA in receipted


def test_verify_receipt_is_true_on_an_untouched_report() -> None:
    receipted = attach_markdown_receipt("# Title\n\nsome body\n", AS_OF)
    assert verify_receipt(receipted) is True


def test_verify_receipt_is_false_after_a_one_byte_edit() -> None:
    receipted = attach_markdown_receipt("# Title\n\nsome body\n", AS_OF)
    tampered = receipted.replace("some body", "some bod1")
    assert verify_receipt(tampered) is False


def test_verify_receipt_is_false_with_no_receipt_line_at_all() -> None:
    assert verify_receipt("# Title\n\nno receipt here\n") is False


def _seed_report_db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'driftless.db'}"
    engine = new_engine(url)
    Base.metadata.create_all(engine)
    with new_session_factory(engine)() as session:
        business = m.Business(name="BRC")
        portfolio = m.Portfolio(name="Content Brands", business=business)
        proj = m.Project(name="GMS", portfolio=portfolio, delivery_mode="predictive")
        stream = m.Workstream(name="GMS", project=proj)
        task = m.Task(name="GMS", workstream=stream, estimate_unit="hours", percent_complete=50)
        baseline = m.Baseline(project=proj, version=1, status="approved")
        line = m.BaselineLine(baseline=baseline, task=task, planned_cost=1000.0)
        line.planned_start, line.planned_finish = date(2026, 1, 31), AS_OF
        session.add(line)
        session.commit()
    return url


def test_report_all_writes_a_verifiable_receipt_on_every_document(tmp_path: Path) -> None:
    url = _seed_report_db(tmp_path)
    out = tmp_path / "reports"
    rc = cli.main(["report", "all", "--as-of", "2026-03-31", "--out", str(out), "--db-url", url])
    assert rc == 0
    written = list(out.rglob("*.md"))
    assert written
    for path in written:
        assert verify_receipt(path.read_text(encoding="utf-8"))


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    engine = new_engine(f"sqlite:///{tmp_path / 'driftless.db'}")
    Base.metadata.create_all(engine)
    factory = new_session_factory(engine)

    def _session() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_csv_export_carries_a_reproducibility_receipt_header(api_client: TestClient) -> None:
    response = api_client.get("/tasks", params={"format": "csv"})
    assert response.status_code == 200
    header = response.headers["x-driftless-receipt"]
    assert calc_receipt.verify_line(response.text.encode("utf-8"), header)


def test_csv_receipt_header_is_false_for_a_tampered_body() -> None:
    body = b"a,b\n1,2\n"
    line = calc_receipt.format_line(calc_receipt.digest(body))
    assert calc_receipt.verify_line(body + b"x", line) is False
