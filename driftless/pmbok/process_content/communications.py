"""Plain-language content for the Communications Management processes
(10.1-10.3), ``KnowledgeArea.COMMUNICATIONS``.

Communications is deciding who needs to know what and when, actually
getting them the information, and then confirming it landed and was useful.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "communications"

CONTENT: dict[str, ProcessContent] = {
    "10.1": ProcessContent(
        plain_summary="Decide who needs which information, how often, and through what channel.",
        why_bother=(
            "Without a plan, some stakeholders are flooded with updates they do not need "
            "while others who need to know something important never hear it."
        ),
        done_when="A communications plan names each stakeholder's needs, format, and frequency.",
        first_time_tip=(
            "Ask each stakeholder how they prefer to receive updates before you set the "
            "plan. A channel that suits you but not them just gets ignored."
        ),
        worked_example=(
            "A small town is replacing the water mains under four residential streets. "
            "The project manager lists who is affected — the residents on those streets, "
            "the two businesses on the corner, the council, and the school whose bus route "
            "changes — and writes down what each one needs: residents want a week's notice "
            "of any shutoff by postcard and text, the council wants a monthly summary in its "
            "meeting packet, and the school needs the detour dates as soon as they are fixed."
        ),
        pitfalls=(
            "Planning every update as an email because that is easiest for you, when half "
            "the affected residents do not read email.",
            "Listing only the people who come to meetings, so the neighbors actually losing "
            "water never appear in the plan.",
            "Promising a frequency you cannot sustain, so the weekly bulletin quietly stops "
            "after three weeks.",
        ),
    ),
    "10.2": ProcessContent(
        plain_summary="Send the right information to the right people at the agreed times.",
        why_bother=(
            "A communications plan that is never actually executed is just a document; this "
            "is where stakeholders actually get what they were promised."
        ),
        done_when="Planned communications are going out on schedule and are being received.",
        first_time_tip=(
            "Keep a simple log of what was sent, to whom, and when. It settles disputes "
            "later about who was or was not told something."
        ),
        worked_example=(
            "With the plan agreed, the shutoff dates go out as postcards a week ahead and a "
            "text the night before, the council gets its summary in the meeting packet, and "
            "the school is emailed the detour dates the day they are confirmed. The project "
            "manager keeps a one-line log of every send, so when a resident later says nobody "
            "told them, the postcard date is there to check."
        ),
        pitfalls=(
            "Sending the notice late and assuming nobody noticed, when a week's warning was "
            "the whole point of it.",
            "Skipping the log, so a complaint about not being told comes down to one person's "
            "word against another's.",
            "Switching channels mid-project without saying so, leaving the people still "
            "watching the old one with nothing.",
        ),
    ),
    "10.3": ProcessContent(
        plain_summary="Check whether the information you are sending is landing and being useful.",
        why_bother=(
            "Sending updates nobody reads or understands is no better than sending nothing; "
            "this is what catches that before it becomes a stakeholder complaint."
        ),
        done_when="Stakeholder feedback on communications has been gathered and the plan adjusted if needed.",
        first_time_tip=(
            "Ask a stakeholder directly whether an update was useful, rather than assuming "
            "silence means it landed fine. Silence usually just means nobody read it."
        ),
        worked_example=(
            "Three weeks in, the project manager phones four residents and asks whether the "
            "postcard arrived in time and whether it made sense. Two say the shutoff hours "
            "were confusing and one never got a text at all, so the bulletin is reworded to "
            "give exact hours and the wrong phone number is corrected in the contact list."
        ),
        pitfalls=(
            "Reading no complaints as proof the updates are landing, when it usually means "
            "nobody read them.",
            "Asking only the stakeholders who are easy to reach, and hearing back only from "
            "the ones already content.",
            "Collecting feedback and then changing nothing, so the same confusion comes back "
            "next month.",
        ),
    ),
}
