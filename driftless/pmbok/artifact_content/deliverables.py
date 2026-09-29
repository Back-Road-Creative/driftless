"""Artifact explanations for the deliverables family (artifacts.FAMILIES["deliverables"]).

The actual outputs the project exists to produce, and the sign-off trail that
turns "we built it" into "it's accepted and done."
"""

from __future__ import annotations

from driftless.pmbok.artifact_content import ArtifactContent

FAMILY = "deliverables"

CONTENT: dict[str, ArtifactContent] = {
    "deliverables": ArtifactContent(
        plain_summary="The actual things the project is building or producing.",
        why_it_matters="It is the point of the whole exercise — everything else exists to help produce these.",
        what_it_looks_like_here="Not stored separately: read directly off each task's status and how much of it is complete.",
    ),
    "verified_deliverables": ArtifactContent(
        plain_summary="Deliverables that have actually been checked to make sure they meet requirements.",
        why_it_matters="Checking a deliverable before calling it done catches problems while they're still cheap to fix.",
        what_it_looks_like_here="Not tracked: verification isn't recorded — read task status and completion percentage instead.",
    ),
    "accepted_deliverables": ArtifactContent(
        plain_summary="Deliverables the customer or sponsor has formally signed off as satisfactory.",
        why_it_matters="A sign-off is what actually closes out a piece of work — nothing else does.",
        what_it_looks_like_here="Recorded as an accepted status in the project's sign-off ledger.",
    ),
    "final_product_service_result": ArtifactContent(
        plain_summary="Everything the project was meant to deliver, taken together at the very end.",
        why_it_matters="It is the answer to 'did the project actually deliver what it set out to?'.",
        what_it_looks_like_here="Not tracked as a single closeout artifact: read the sign-off ledger for the full picture.",
    ),
    "final_report": ArtifactContent(
        plain_summary="A written summary looking back on the whole project once it's finished.",
        why_it_matters="It is where a project's lessons and outcomes get written down before everyone moves on and forgets.",
        what_it_looks_like_here="Not tracked as its own document: read the sign-off ledger for how the project actually finished.",
    ),
}
