"""Artifact explanations for the environment family (artifacts.FAMILIES["environment"]).

Everything the project inherits rather than creates: the world it operates in,
the organization's own accumulated know-how, and the case that justified
starting it in the first place.
"""

from __future__ import annotations

from driftless.pmbok.artifact_content import ArtifactContent

FAMILY = "environment"

CONTENT: dict[str, ArtifactContent] = {
    "enterprise_environmental_factors": ArtifactContent(
        plain_summary="Outside conditions the project has to work within but didn't choose, like rules or the market.",
        why_it_matters="Ignoring these tends to produce a plan that looks good on paper and fails against reality.",
        what_it_looks_like_here="Stored as a short piece of prose attached to the project.",
    ),
    "organizational_process_assets": ArtifactContent(
        plain_summary="The organization's own past templates, records and know-how the project can reuse.",
        why_it_matters="Reusing what already worked before saves a project from reinventing it badly.",
        what_it_looks_like_here="Stored as a short piece of prose attached to the project.",
    ),
    "business_case": ArtifactContent(
        plain_summary="A written justification for why the project is worth doing at all.",
        why_it_matters="Without one, nobody can later check whether the project is still worth the money being spent.",
        what_it_looks_like_here="Not tracked: this earlier analysis happens before this system starts following the project.",
    ),
    "benefits_management_plan": ArtifactContent(
        plain_summary="A plan for how the project's promised value will actually be delivered and measured.",
        why_it_matters="A project can finish on time and still fail to deliver the value it was started for.",
        what_it_looks_like_here="Not tracked: this kind of value analysis is somebody else's tool, done before this system takes over.",
    ),
    "agreements_initial": ArtifactContent(
        plain_summary="The contract, letter of intent or other agreement with the customer or sponsor that the project starts from.",
        why_it_matters="It records what the customer or sponsor initially intends, and is often the basis on which the project is started.",
        what_it_looks_like_here="Not tracked: pre-project agreements happen elsewhere — once one is signed, read it as an agreement.",
    ),
}
