"""Plain-language content for the Procurement Management processes
(12.1-12.3), ``KnowledgeArea.PROCUREMENT``.

Procurement is buying what the project cannot produce itself: decide what to
buy and how, run the actual purchase, and manage the resulting agreement
through to its close.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "procurement"

CONTENT: dict[str, ProcessContent] = {
    "12.1": ProcessContent(
        plain_summary="Decide what the project will buy from outside, and how you will buy it.",
        why_bother=(
            "Deciding to buy something after the schedule already needs it leaves no time "
            "to shop around, and you end up paying more for less choice."
        ),
        done_when="A procurement plan names what will be bought, from whom, and by when.",
        first_time_tip=(
            "Decide build-versus-buy for each item as early as possible. A late decision to "
            "buy forces a rushed purchase with far less negotiating room."
        ),
        worked_example=(
            "The renovation buys the shelving and the contractor's crew, while the library's "
            "own volunteers do the painting prep. Settling that in January is what leaves time "
            "to get three shelving quotes before the May delivery slot has to be booked."
        ),
        pitfalls=(
            "Deciding to buy something in the week the schedule already needs it delivered.",
            "Planning what to buy without checking what the organization is required to tender.",
            "Leaving who signs the agreement unsettled until a seller is waiting on it.",
        ),
    ),
    "12.2": ProcessContent(
        plain_summary="Select a seller and put a signed agreement in place with them.",
        why_bother=(
            "Starting work with a seller before terms are signed leaves the project exposed "
            "if a disagreement about scope, price, or timing comes up later."
        ),
        done_when="A seller is selected and a signed agreement is in place covering the work.",
        first_time_tip=(
            "Get more than one bid even when you already have a preferred seller. A single "
            "quote gives you no leverage and no comparison to judge it against."
        ),
        worked_example=(
            "Three suppliers are asked for written quotes against the same specification — "
            "40 kg a shelf, delivered and installed in May. The cheapest cannot meet the date, "
            "so the award goes to the second, and the reason is written down beside it."
        ),
        pitfalls=(
            "Sending each bidder a different spec, so the quotes cannot be compared.",
            "Awarding on price alone when the date or the standard is what actually matters.",
            "Letting a seller start work on a verbal yes before the agreement is signed.",
        ),
    ),
    "12.3": ProcessContent(
        plain_summary="Manage the agreement day to day and formally close it when the work ends.",
        why_bother=(
            "A signed agreement left unmanaged drifts: deliverables slip, invoices go "
            "unchecked, and nobody notices until the relationship has already soured."
        ),
        done_when="The seller's performance has been tracked, deliverables accepted, and the agreement closed.",
        first_time_tip=(
            "Review seller performance against the agreement on a fixed schedule, not only "
            "when a deliverable is due. Regular reviews catch drift before it is a dispute."
        ),
        worked_example=(
            "The first run of shelving arrives with the wrong bracket spacing. The acceptance "
            "terms in the agreement are what let the project manager have it corrected at the "
            "supplier's cost, rather than absorbing it as a project overrun."
        ),
        pitfalls=(
            "Paying an invoice without checking it against what the agreement actually says.",
            "Accepting a deliverable informally, losing the remedy the agreement gave you.",
            "Closing the agreement without confirming every deliverable and payment is settled.",
        ),
    ),
}
