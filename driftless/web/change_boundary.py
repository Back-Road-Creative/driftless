"""The one change and approval boundary every plan-changing assistant links to.

An assistant that proposes a hypothetical plan change — a schedule scenario, a
cost what-if — never gets its own way to make that change real. Whatever a
project's hybrid tailoring reads its day-to-day controls on
(``driftless.pmbok.tailoring``), a change to the approved plan itself always goes
through the one existing producer: ``POST /change-requests``
(``driftless.models.records.ChangeRequest``), which on approval becomes a new
``driftless.models.delivery.Baseline`` version. This module is the one place that
link is built, so a page can point at the boundary without hand-assembling its
own — and so a second, competing "approve the plan" surface never grows beside it
(pinned by ``tests/test_web_change_boundary.py``, which greps every template for a
second baseline-approval form).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChangeBoundary:
    """A link from a what-if page back to the one place a change becomes real."""

    href: str
    label: str
    origin_process_id: str
    instruction: str


def change_boundary(project_id: int, origin_process_id: str) -> ChangeBoundary:
    """The change-boundary link for ``project_id``, naming the process
    (``origin_process_id``, a PMBOK clause id) that raised the proposal — recorded
    on the request as ``ChangeRequest.origin_process_id`` when it is filed."""
    return ChangeBoundary(
        href=f"/projects/{project_id}/raid#changes",
        label="Raise a change request",
        origin_process_id=origin_process_id,
        instruction=(
            f'Submit a proposal with POST /change-requests with {{"project_id": '
            f'{project_id}, "origin_process_id": "{origin_process_id}"}}.'
        ),
    )
