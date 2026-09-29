"""Artifact explanations for the changes family (artifacts.FAMILIES["changes"]).

The two-step trail a change to the plan leaves behind: someone asks for it,
then someone with authority says yes.
"""

from __future__ import annotations

from driftless.pmbok.artifact_content import ArtifactContent

FAMILY = "changes"

CONTENT: dict[str, ArtifactContent] = {
    "change_requests": ArtifactContent(
        plain_summary="A formal ask to change something already agreed in the plan.",
        why_it_matters="Routing changes through a formal ask, instead of quiet edits, is what keeps the plan trustworthy.",
        what_it_looks_like_here="Not a separate list: stored as the project's change-request rows, surfaced as the change log.",
    ),
    "approved_change_requests": ArtifactContent(
        plain_summary="Change requests that have actually been approved and are now part of the plan.",
        why_it_matters="It is the line between someone merely asking for a change and the plan actually changing.",
        what_it_looks_like_here=(
            "Not tracked separately: an approval here causes a brand-new baseline "
            "version — read the change log."
        ),
    ),
}
