"""Artifact explanations for the performance family (artifacts.FAMILIES["performance"]).

Raw numbers, those numbers read in context, and the periodic report that
summarizes both — the flow from data to a report a stakeholder can act on.
"""

from __future__ import annotations

from driftless.pmbok.artifact_content import ArtifactContent

FAMILY = "performance"

CONTENT: dict[str, ArtifactContent] = {
    "work_performance_data": ArtifactContent(
        plain_summary="The raw, unprocessed numbers collected as work actually happens.",
        why_it_matters="It is the starting material everything else in this family is built from.",
        what_it_looks_like_here="Not stored on its own: computed on the fly from actual cost and status rows rather than kept as a saved copy.",
    ),
    "work_performance_information": ArtifactContent(
        plain_summary="Raw numbers read together with the plan, so they actually mean something.",
        why_it_matters="A number alone doesn't say if things are going well; comparing it to the plan does.",
        what_it_looks_like_here=(
            "The approved plan read alongside recent actual costs and status updates; "
            "healthy only while that comparison is still recent."
        ),
    ),
    "work_performance_reports": ArtifactContent(
        plain_summary="A periodic write-up that turns the numbers into something a person can act on.",
        why_it_matters="It is what actually reaches a busy stakeholder, instead of a spreadsheet they'd have to interpret themselves.",
        what_it_looks_like_here=(
            "The project's most recent status update; healthy only while it is still recent."
        ),
    ),
}
