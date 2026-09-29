"""Artifact explanations for the plans family (artifacts.FAMILIES["plans"]).

Charters, the overall plan, and the subsidiary management plans it binds
together — the documents that say what the team agreed to do and how, before
any of it starts happening.
"""

from __future__ import annotations

from driftless.pmbok.artifact_content import ArtifactContent

FAMILY = "plans"

CONTENT: dict[str, ArtifactContent] = {
    "project_charter": ArtifactContent(
        plain_summary="A short paper that officially starts the project and says who is in charge.",
        why_it_matters=(
            "Without it nobody has the standing to spend money or ask people for time — it "
            "is the permission slip the rest of the project depends on."
        ),
        what_it_looks_like_here=(
            "Driftless generates it on demand from the project's own record (its sponsor, "
            "goal and manager), rather than storing a separate copy that could drift from them."
        ),
    ),
    "project_management_plan": ArtifactContent(
        plain_summary="The single plan that ties together every smaller plan for how the work will run.",
        why_it_matters=(
            "It is the one place a reader can check that scope, schedule, cost, quality, "
            "risk and every other angle were actually thought through together, not separately."
        ),
        what_it_looks_like_here=(
            "There is no stored document with this name; Driftless rolls it up live from "
            "the ten subsidiary plans below, so it is only complete once all ten are."
        ),
    ),
    "scope_management_plan": ArtifactContent(
        plain_summary="A short note on how the team will decide, and defend, what is and isn't included.",
        why_it_matters=(
            "Without a written rule for handling scope questions, every new request turns "
            "into a fresh argument instead of a quick check against an agreed process."
        ),
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "requirements_management_plan": ArtifactContent(
        plain_summary="Notes on how needs will be collected, written down and kept from changing quietly.",
        why_it_matters=(
            "It keeps everyone working from the same understanding of what people actually "
            "need, instead of everyone's private guess."
        ),
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "schedule_management_plan": ArtifactContent(
        plain_summary="Notes on how the timeline will be built, updated and kept honest.",
        why_it_matters=(
            "A schedule nobody agreed to maintain the same way quickly stops meaning anything."
        ),
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "cost_management_plan": ArtifactContent(
        plain_summary="Notes on how the budget will be planned, tracked and controlled.",
        why_it_matters="It sets the rules for what counts as overspending before money is on the line.",
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "quality_management_plan": ArtifactContent(
        plain_summary="Notes on what good work means here and how it will be checked.",
        why_it_matters="Without an agreed standard, 'good enough' is decided after the fact, too late to matter.",
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "resource_management_plan": ArtifactContent(
        plain_summary="Notes on how people and other resources will be found, organized and looked after.",
        why_it_matters="It is the difference between staffing being planned and staffing being scrambled for.",
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "communications_management_plan": ArtifactContent(
        plain_summary="Notes on who needs to hear what, how often, and through which channel.",
        why_it_matters="A team that never agreed how to talk to each other ends up finding out things too late.",
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "risk_management_plan": ArtifactContent(
        plain_summary="Notes on how the team will look for things that could go wrong and respond.",
        why_it_matters="It turns risk from a vague worry into a routine the team actually follows.",
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "procurement_management_plan": ArtifactContent(
        plain_summary="Notes on how the team will buy things or hire outside help.",
        why_it_matters="It sets the rules before a contract is signed, not while negotiating one.",
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "stakeholder_engagement_plan": ArtifactContent(
        plain_summary="Notes on how the team will keep the people affected by the project involved.",
        why_it_matters="People who feel ignored tend to become obstacles later, whether or not they meant to.",
        what_it_looks_like_here="Written as a short narrative attached to the project.",
    ),
    "change_management_plan": ArtifactContent(
        plain_summary="Notes on how a request to change the plan gets reviewed and decided.",
        why_it_matters="Without a rule for this, changes either sneak in unreviewed or stall forever.",
        what_it_looks_like_here=(
            "Not stored as its own document: the rule is enforced structurally — a change "
            "is only real once it produces a new, approved baseline version."
        ),
    ),
    "configuration_management_plan": ArtifactContent(
        plain_summary="Notes on how versions of the plan itself are tracked and kept from getting confused.",
        why_it_matters="Without it, nobody can say with confidence which version of the plan is the current one.",
        what_it_looks_like_here=(
            "Enforced structurally by baseline versioning rather than written as a document: "
            "each approved baseline carries its own version number."
        ),
    ),
    "development_approach": ArtifactContent(
        plain_summary="A one-word answer to how the team will work: in steady sprints, in stages, or something in between.",
        why_it_matters="It shapes almost everything else — how progress is tracked, planned and reported.",
        what_it_looks_like_here="Stored directly as a field on the project record, not as a separate document.",
    ),
}
