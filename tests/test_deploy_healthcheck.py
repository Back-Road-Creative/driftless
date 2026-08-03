"""The container healthcheck must ask a question a database outage can fail.

``docker compose ps`` is the operator's first signal, and it used to be a lie: the
check hit ``/health``, which the token gate answered from a byte literal before auth
and without a store, so the service read *healthy* straight through a total Postgres
outage and the first real signal was a user complaint. The endpoint now reaches the
store (``driftless/api/app.py``); this file pins the compose half, because a correct
endpoint behind a check that never goes red is still a broken gate.

Two properties, and the second is the one that is easy to get wrong: the check must
name the endpoint that touches the store *and* use ``curl -f``, so a 503 body is a
failure rather than a successful download; and every check needs a ``start_period``,
without which the first migration's boot time is counted as an outage and the
retry budget is spent before the service has ever served a request.
"""

from __future__ import annotations

from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
SERVICES = ("driftless-app", "driftless-db")


def _nested(header: str, indent: int, lines: list[str]) -> list[str]:
    """The lines nested under the first ``header``, by indentation.

    Hand-read rather than parsed: PyYAML is not a dependency of this project, and
    adding one to reach four scalars would be pure supply-chain surface for a file
    whose shape is fixed two levels deep.
    """
    start = next(i for i, line in enumerate(lines) if line.strip() == header)
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    return body


def healthcheck(service: str) -> dict[str, str]:
    """``service``'s ``healthcheck:`` mapping, read off the shipped compose file."""
    lines = COMPOSE.read_text(encoding="utf-8").splitlines()
    block = _nested("healthcheck:", 4, _nested(f"{service}:", 2, lines))
    pairs = (line.partition(":") for line in block)
    return {key.strip(): value.strip() for key, _, value in pairs if key.strip()}


def _seconds(value: str) -> int:
    return int(value[:-1]) * (60 if value.endswith("m") else 1)


def test_the_app_check_asks_the_endpoint_that_reaches_the_store() -> None:
    """/health, which now answers 503 when the database does not — not a byte literal."""
    probe = healthcheck("driftless-app")["test"]
    assert "8000/health" in probe and "/health/ready" not in probe, (
        f"the app healthcheck no longer calls the liveness endpoint: {probe}"
    )
    assert "-f" in probe.split("curl")[1].split()[0], (
        f"curl without -f treats a 503 as a successful download, so the check never "
        f"goes red however sick the service is: {probe}"
    )


def test_every_check_grants_a_start_period_so_booting_is_not_an_outage() -> None:
    """``alembic upgrade head`` runs before uvicorn; initdb runs before Postgres."""
    for service in SERVICES:
        check = healthcheck(service)
        assert "start_period" in check, (
            f"{service} has no start_period, so its slowest legitimate start counts "
            f"against the retry budget and a first boot can be reported unhealthy: {check}"
        )
        assert _seconds(check["start_period"]) >= 30, check


def test_an_outage_is_reported_inside_a_minute() -> None:
    """The gate is only as good as the time it takes to flip — and to not overlap."""
    check = healthcheck("driftless-app")
    interval, retries = _seconds(check["interval"]), int(check["retries"])
    assert interval * retries <= 60, (
        f"an outage takes {interval * retries}s to reach `docker compose ps`: {check}"
    )
    assert _seconds(check["timeout"]) < interval, (
        f"a timeout at or past the interval lets one hung check overlap the next: {check}"
    )
