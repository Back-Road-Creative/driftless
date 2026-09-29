"""Artifact explanations for the procurement family (artifacts.FAMILIES["procurement"]).

Everything to do with buying goods or services from an outside seller, from
deciding what to buy through choosing a seller to closing the signed deal.
"""

from __future__ import annotations

from driftless.pmbok.artifact_content import ArtifactContent

FAMILY = "procurement"

CONTENT: dict[str, ArtifactContent] = {
    "procurement_statement_of_work": ArtifactContent(
        plain_summary="A written description of exactly what an outside seller is being asked to deliver.",
        why_it_matters="A vague request to a seller invites a vague, disappointing delivery.",
        what_it_looks_like_here="Not tracked: work before a contract is signed happens outside this system — read the signed agreements.",
    ),
    "procurement_documentation": ArtifactContent(
        plain_summary="The paperwork trail behind buying something from an outside seller.",
        why_it_matters="It is what a reader would check to see how a purchase decision was actually made.",
        what_it_looks_like_here="Not tracked: this system starts tracking a purchase once it is signed — read the signed agreements.",
    ),
    "procurement_strategy": ArtifactContent(
        plain_summary="A plan for how the team will go about buying something, before shopping starts.",
        why_it_matters="Deciding how to buy something up front avoids scrambling once a need becomes urgent.",
        what_it_looks_like_here="Not tracked: this work happens before a contract is signed, outside this system — read the signed agreements.",
    ),
    "source_selection_criteria": ArtifactContent(
        plain_summary="The rules the team will use to judge which seller to pick.",
        why_it_matters="Written criteria keep a selection decision from looking like it was made on a whim.",
        what_it_looks_like_here="Not tracked: selection happens before a contract is signed — read the signed agreements for the outcome.",
    ),
    "bid_documents": ArtifactContent(
        plain_summary="The paperwork sent out asking outside sellers to submit an offer.",
        why_it_matters="It is what makes sure every seller is competing on the same terms.",
        what_it_looks_like_here="Not tracked: soliciting offers happens outside this system — read the signed agreements.",
    ),
    "seller_proposals": ArtifactContent(
        plain_summary="The offers outside sellers actually send back in response to a request.",
        why_it_matters="It is the raw material a selection decision is made from.",
        what_it_looks_like_here="Not tracked: proposals arrive before a contract is signed, outside this system — read the signed agreements.",
    ),
    "agreements": ArtifactContent(
        plain_summary="The signed contract between the project and an outside seller.",
        why_it_matters="It is what makes a deal enforceable instead of a friendly understanding.",
        what_it_looks_like_here=(
            "The project's recorded agreement rows; healthy only while none of them are in dispute."
        ),
    ),
    "selected_sellers": ArtifactContent(
        plain_summary="The outside sellers the team has actually chosen to work with.",
        why_it_matters="It is the decision everything else in the purchase depends on.",
        what_it_looks_like_here="Not tracked separately: read the outcome directly off the signed agreements.",
    ),
    "closed_procurements": ArtifactContent(
        plain_summary="Purchases that are finished and formally wrapped up with the seller.",
        why_it_matters="Closing a purchase properly avoids loose ends like unpaid invoices or unclear ownership.",
        what_it_looks_like_here="Not a separate document: it is simply an agreement whose recorded status is closed.",
    ),
    "independent_cost_estimates": ArtifactContent(
        plain_summary="The team's own estimate of a fair price, made before hearing what a seller quotes.",
        why_it_matters="It is a check against being overcharged, worked out before a seller's number can bias it.",
        what_it_looks_like_here="Not tracked: this kind of pre-purchase work happens outside this system.",
    ),
}
