"""Plain-language content for the Stakeholder Management processes
(13.1-13.4), ``KnowledgeArea.STAKEHOLDER``.

Stakeholder management is finding everyone with a stake in the project,
deciding how to engage each of them, doing the actual engaging, and checking
whether it is working.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "stakeholder"

CONTENT: dict[str, ProcessContent] = {
    "13.1": ProcessContent(
        plain_summary="Find everyone with a stake in the project and write down what they care about.",
        why_bother=(
            "A stakeholder nobody identified cannot be planned for, and they tend to "
            "surface later as unexpected resistance to a decision already made."
        ),
        done_when="Stakeholders are identified and logged with their interest and level of influence.",
        first_time_tip=(
            "Ask each stakeholder you find who else you should be talking to. The list "
            "almost always grows past the names you started with."
        ),
        worked_example=(
            "The obvious names are the director and the board. Asking each of them who else "
            "cares is what adds the teen-program volunteer, an accessibility advocate, and the "
            "tenant next door whose wall the scaffold has to lean against."
        ),
        pitfalls=(
            "Listing only the people who hold budget and missing the ones who can block the work.",
            "Recording a name with no note of what that person actually cares about.",
            "Treating the register as finished, when new stakeholders appear as the work does.",
        ),
    ),
    "13.2": ProcessContent(
        plain_summary="Decide how you will engage each stakeholder based on what they need.",
        why_bother=(
            "Engaging every stakeholder the same way wastes effort on people who need "
            "little while under-serving the ones whose support the project actually needs."
        ),
        done_when="An engagement plan exists naming how each stakeholder will be involved.",
        first_time_tip=(
            "Set a separate engagement approach for a stakeholder who could block the "
            "project, not the same one used for a stakeholder who is merely interested."
        ),
        worked_example=(
            "The board chair gets a one-page summary each month, the director a standing place "
            "at the Friday walk-through, and the accessibility advocate is asked to review the "
            "teen-room layout before it is built rather than shown it afterwards."
        ),
        pitfalls=(
            "Giving everyone the same weekly email whatever their interest or influence.",
            "Planning to merely inform a stakeholder whose approval the project actually needs.",
            "Writing an engagement plan that costs more time than the project can spare.",
        ),
    ),
    "13.3": ProcessContent(
        plain_summary="Actually work with stakeholders to keep their support and address concerns.",
        why_bother=(
            "An engagement plan nobody follows leaves stakeholders exactly as uninvolved as "
            "if the plan had never been written."
        ),
        done_when="Stakeholders are being actively engaged per the plan and their concerns are addressed.",
        first_time_tip=(
            "Address a stakeholder's concern as soon as it is raised, even briefly. A "
            "concern left unanswered tends to grow into open resistance."
        ),
        worked_example=(
            "The accessibility advocate points out that the new shelving leaves too tight a "
            "turning circle. Answering her that week, and moving the layout, is what keeps her "
            "supporting the renovation instead of objecting to it at the board meeting."
        ),
        pitfalls=(
            "Hearing a concern and logging it without ever answering the person who raised it.",
            "Engaging a stakeholder only in the week something is needed from them.",
            "Letting every stakeholder conversation run through one person who then leaves.",
        ),
    ),
    "13.4": ProcessContent(
        plain_summary="Check whether stakeholder engagement is working and adjust if it is not.",
        why_bother=(
            "A stakeholder's support can quietly fade even when the engagement plan is "
            "being followed; this is what catches the gap before it becomes open opposition."
        ),
        done_when="Stakeholder engagement levels are tracked against the plan and gaps are addressed.",
        first_time_tip=(
            "Reassess a stakeholder's actual engagement level, not just whether the "
            "planned activities happened. Attending a meeting is not the same as being engaged."
        ),
        worked_example=(
            "The tenant next door stops replying to the weekly note. Treating that silence as a "
            "signal, rather than counting the note as engagement, is what surfaces the scaffold "
            "complaint while it is still a conversation and not a call to the council."
        ),
        pitfalls=(
            "Counting messages sent as engagement, without checking any were read or answered.",
            "Reassessing engagement only after a stakeholder has already objected publicly.",
            "Adjusting the plan on paper without changing what anyone actually does.",
        ),
    ),
}
