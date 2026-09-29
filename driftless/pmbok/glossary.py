"""``GLOSSARY``: the closed vocabulary of PMBOK terms of art the running app uses
without stopping to explain, so a reader never has to already know what "float"
or "EVM" means before a page can tell them anything else.

Frozen at import, the same shape as :mod:`driftless.pmbok.definitions`'s
``TECHNIQUES`` registry: one :class:`GlossaryEntry` per term, keyed by the word
``/glossary#{key}`` addresses and the ``gloss`` Jinja filter
(:mod:`driftless.web.templating`) looks a term up by. Every entry here is
required to be *used* somewhere a reader already reaches — a shipped technique
definition, a process name, an artifact display name, or a template —
``tests/test_glossary.py`` walks all four sources and refuses an entry no
surface actually says. A term this repo does not yet use anywhere a reader can
read (``RACI``, ``EEF``, ``OPA``, ``CPM``, ``OKR``, "definition of done" among
them) is left out rather than defined and orphaned; it belongs in whichever unit
first prints it.

``plain`` is the one-sentence, twenty-five-word-or-fewer explanation that never
assumes another glossary term: read it and you do not need to already know
"baseline" to understand "change request". An acronym's ``plain`` is its
expansion, spelled out rather than left as three more letters.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GlossaryEntry:
    """One term of art: the word a reader meets, explained twice — ``plain`` first
    (no other glossary term inside it), then ``longer`` for the reader who wants
    more than one sentence. ``see_also`` names other ``GLOSSARY`` keys, never a
    free-text cross-reference a rename could silently break."""

    term: str
    plain: str
    longer: str
    see_also: tuple[str, ...] = field(default_factory=tuple)
    defined_on: tuple[str, ...] = field(default_factory=tuple)


GLOSSARY: dict[str, GlossaryEntry] = {
    "as-of": GlossaryEntry(
        term="As-of",
        plain=(
            "As-of is the single date every report and page is calculated for, so "
            "numbers never quietly drift while you read them."
        ),
        longer=(
            "Every calculation in Driftless takes an as-of date as an explicit input "
            "rather than reading the clock, so a report regenerated later for the same "
            "as-of comes back byte-identical."
        ),
        see_also=("baseline",),
    ),
    "backlog": GlossaryEntry(
        term="Backlog",
        plain=(
            "Backlog is the full list of work not yet started, ordered by what should happen next."
        ),
        longer=(
            "A backlog is re-ordered as priorities change; nothing on it is "
            "committed to a particular period until it is pulled into one."
        ),
        see_also=("sprint", "velocity"),
        defined_on=("/methods/scrum",),
    ),
    "baseline": GlossaryEntry(
        term="Baseline",
        plain=(
            "Baseline is the approved plan a project is measured against, frozen "
            "until a change is formally approved."
        ),
        longer=(
            "Actuals are compared to the baseline, not to whatever the plan has "
            "since become, so a project's variance means something specific."
        ),
        see_also=("change-request", "earned-value"),
    ),
    "change-request": GlossaryEntry(
        term="Change request",
        plain=(
            "A change request is a formal ask to alter a project's scope, schedule, "
            "or cost after it was baselined."
        ),
        longer=(
            "It is decided on, not just noted: an approved change request updates "
            "the baseline, and a rejected one leaves it exactly where it was."
        ),
        see_also=("baseline", "sign-off"),
        defined_on=("/artifacts/change-requests",),
    ),
    "critical-path": GlossaryEntry(
        term="Critical path",
        plain=(
            "The critical path is the longest chain of dependent tasks through the "
            "schedule, and its length sets the shortest possible finish date."
        ),
        longer=(
            "Slip any task on the critical path and the whole project's finish "
            "date slips with it; slip a task off it and the finish date can hold. "
            "Its tasks usually have zero float, but not always -- a constraint can "
            "leave a critical-path task with float above zero."
        ),
        see_also=("float", "work-breakdown-structure"),
        defined_on=("/techniques/critical-path-method",),
    ),
    "crosswalk": GlossaryEntry(
        term="Crosswalk",
        plain=(
            "A crosswalk names the PMBOK-6 process or technique an agile practice "
            "most closely lines up with."
        ),
        longer=(
            "It never claims the two are the same thing, only that one answers the "
            "other's coverage question well enough to read from either side; a "
            "practice with no PMBOK-6 equivalent carries none, and says why instead."
        ),
        defined_on=("/methods",),
    ),
    "earned-value": GlossaryEntry(
        term="Earned value",
        plain=(
            "Earned value is the budgeted worth of the work actually completed by "
            "a given date, used to judge progress."
        ),
        longer=(
            "Compared against planned and actual cost, earned value is what turns "
            '"we spent the money" into "we got the work that money was for."'
        ),
        see_also=("evm", "baseline"),
        defined_on=("/techniques/earned-value-analysis",),
    ),
    "enterprise-environmental-factors": GlossaryEntry(
        term="Enterprise environmental factors",
        plain=(
            "Enterprise environmental factors are outside conditions, like market "
            "rules or company culture, that shape how a project can run."
        ),
        longer=(
            "They are not decided by the project and are not produced by it — a "
            "process reads them as a given, the way it reads a calendar."
        ),
        see_also=("organizational-process-assets",),
        defined_on=("/artifacts/enterprise-environmental-factors",),
    ),
    "evm": GlossaryEntry(
        term="EVM",
        plain=(
            "EVM is the practice of tracking cost and schedule performance "
            "together using a project's budgeted-versus-completed-work figures."
        ),
        longer=(
            "It is what turns a single earned-value figure into a repeatable "
            "reading a project takes at every as-of date, not just once."
        ),
        see_also=("earned-value",),
        defined_on=("/techniques/earned-value-analysis",),
    ),
    "float": GlossaryEntry(
        term="Float",
        plain=(
            "Float is how many days a task can slip without delaying the project's finish date."
        ),
        longer=(
            "A task with zero float is on the critical path; a task with days of "
            "float can run late and the project still finishes on time."
        ),
        see_also=("critical-path",),
        defined_on=("/techniques/critical-path-method",),
    ),
    "knowledge-area": GlossaryEntry(
        term="Knowledge area",
        plain=(
            "A knowledge area is one of the ten subject groupings PMBOK sorts "
            "project work into, like cost or risk."
        ),
        longer=(
            "Every PMBOK process sits in exactly one knowledge area and one "
            "process group, which is what makes the ITTO grid a grid."
        ),
        see_also=("process-group",),
        defined_on=("/pmbok",),
    ),
    "lessons-learned": GlossaryEntry(
        term="Lessons learned",
        plain=(
            "Lessons learned are the written takeaways from a project, captured "
            "so the next project can learn from them."
        ),
        longer=(
            "They are recorded through the project, not only at closeout, and "
            "feed forward as the raw material a later project's own planning reads."
        ),
        see_also=("organizational-process-assets",),
        defined_on=("/artifacts/lessons-learned-register",),
    ),
    "milestone": GlossaryEntry(
        term="Milestone",
        plain=(
            "A milestone is a single dated point on a schedule that marks a "
            "significant moment, with zero duration of its own."
        ),
        longer=(
            "A milestone is hit or missed, never partly done — it is a marker on "
            "the schedule, not a task with hours logged against it."
        ),
        see_also=("critical-path",),
        defined_on=("/artifacts/milestone-list",),
    ),
    "organizational-process-assets": GlossaryEntry(
        term="Organizational process assets",
        plain=(
            "Organizational process assets are the templates, policies, and past "
            "records an organization has built up from earlier projects."
        ),
        longer=(
            "Unlike enterprise environmental factors, these come from inside the "
            "organization itself, and a project both reads and adds to them."
        ),
        see_also=("enterprise-environmental-factors", "lessons-learned"),
        defined_on=("/artifacts/organizational-process-assets",),
    ),
    "bac": GlossaryEntry(
        term="BAC",
        plain=(
            "BAC is short for budget at completion, the total amount a project was "
            "originally budgeted to cost."
        ),
        longer=(
            "It is revised when an approved change request moves the baseline, "
            "but it does not drift with a project's day-to-day outlook the way "
            "EAC does -- only an approved change updates it."
        ),
        see_also=("eac",),
        defined_on=("/techniques/earned-value-analysis",),
    ),
    "dmaic": GlossaryEntry(
        term="DMAIC",
        plain=(
            "DMAIC is short for define, measure, analyze, improve, control, a "
            "five-step cycle for driving down defects in a repeatable way."
        ),
        longer=(
            "Each step feeds the next in order, and control is what keeps an "
            "improvement from quietly slipping back once attention moves elsewhere."
        ),
    ),
    "eac": GlossaryEntry(
        term="EAC",
        plain=(
            "EAC is short for estimate at completion, the current best guess of "
            "what a project will actually cost once it is finished."
        ),
        longer=(
            "Unlike the original budget, it is revised as the project runs, so it "
            "reflects performance to date rather than the plan made at the start."
        ),
        see_also=("bac",),
        defined_on=("/techniques/earned-value-analysis",),
    ),
    "ev": GlossaryEntry(
        term="EV",
        plain=(
            "EV is a running figure for the budgeted worth of the work a project "
            "has actually finished by a given date."
        ),
        longer=(
            "It is the number that turns progress into the same units as cost, so "
            "the two can be compared directly at any as-of date."
        ),
        see_also=("earned-value",),
        defined_on=("/techniques/earned-value-analysis",),
    ),
    "pdca": GlossaryEntry(
        term="PDCA",
        plain=(
            "PDCA is short for plan, do, check, act, a four-step cycle a team "
            "repeats to make a small improvement, test it, and keep what works."
        ),
        longer=(
            "Each pass around the cycle is deliberately small, so a bad idea is "
            "caught and reversed quickly rather than rolled out project-wide first."
        ),
    ),
    "pm": GlossaryEntry(
        term="PM",
        plain="PM is the short way of writing project manager, the person running the project day to day.",
        longer=(
            "It is a role, not a title tied to any one industry, and it is who a "
            "process usually means when it calls for a decision or a judgment call."
        ),
    ),
    "pmis": GlossaryEntry(
        term="PMIS",
        plain=(
            "PMIS is short for project management information system, the tools "
            "that hold a project's working data and make it usable by the team."
        ),
        longer=(
            "It covers scheduling tools, work-tracking boards, shared documents, "
            "and reporting layers together, not any one of them alone."
        ),
        defined_on=("/techniques/project-management-information-system",),
    ),
    "swot": GlossaryEntry(
        term="SWOT",
        plain=(
            "SWOT is short for strengths, weaknesses, opportunities, threats, a "
            "four-part layout for comparing a situation's internal and external factors."
        ),
        longer=(
            "Strengths and weaknesses look inward at what is already true; "
            "opportunities and threats look outward at what could change."
        ),
    ),
    "pert": GlossaryEntry(
        term="PERT",
        plain=(
            "PERT estimates a task's duration from three guesses, best case, "
            "worst case, and most likely, averaged into one number."
        ),
        longer=(
            "The weighting favors the most-likely guess, so one wildly optimistic "
            "or pessimistic estimate cannot swing the result on its own."
        ),
        see_also=("critical-path",),
        defined_on=("/techniques/three-point-estimating",),
    ),
    "process-group": GlossaryEntry(
        term="Process group",
        plain=(
            "A process group is one of the five logical groupings, like "
            "planning or closing, every PMBOK process belongs to."
        ),
        longer=(
            "A process group is not a calendar period a project passes through "
            "once — several can be active on a project at the same time."
        ),
        see_also=("knowledge-area",),
        defined_on=("/pmbok",),
    ),
    "procurement": GlossaryEntry(
        term="Procurement",
        plain=(
            "Procurement is the work of buying goods or services from an "
            "outside seller for the project."
        ),
        longer=(
            "It covers the whole path from deciding what to buy through choosing "
            "a seller to closing the agreement out."
        ),
    ),
    "rag": GlossaryEntry(
        term="RAG",
        plain=(
            "RAG is a three-colour status label, red, amber, or green, showing "
            "how healthy a project or task currently is."
        ),
        longer=(
            "A rollup's RAG is the worst of its children's: one red child makes "
            "the whole group read red, never averaged away."
        ),
        defined_on=("/scorecard",),
    ),
    "risk-register": GlossaryEntry(
        term="Risk register",
        plain=(
            "A risk register is the running list of identified risks, each with "
            "its likelihood, impact, and owner."
        ),
        longer=(
            "It is updated as risks are found, change, or close out, rather than "
            "written once at the start of a project and left alone."
        ),
        defined_on=("/artifacts/risk-register",),
    ),
    "sign-off": GlossaryEntry(
        term="Sign-off",
        plain=(
            "Sign-off is a named person's recorded decision to approve a piece "
            "of work, so approval is never assumed."
        ),
        longer=(
            "A sign-off names who decided and when, so approval is a fact the "
            "record holds rather than something everyone simply assumed happened."
        ),
        see_also=("change-request",),
    ),
    "sla": GlossaryEntry(
        term="SLA",
        plain=(
            "SLA, short for service level agreement, is a promised response or "
            "turnaround time a party commits to meet."
        ),
        longer=(
            "It is a measurable commitment, not a hope — a party either met the "
            "promised time or did not."
        ),
    ),
    "sprint": GlossaryEntry(
        term="Sprint",
        plain=(
            "A sprint is a fixed short period, often two weeks, in which a team "
            "commits to finishing a set slice of work."
        ),
        longer=(
            "A sprint's length does not change from one to the next, which is "
            "what makes a team's output across several of them comparable."
        ),
        see_also=("velocity", "backlog"),
        defined_on=("/methods/scrum",),
    ),
    "stakeholder": GlossaryEntry(
        term="Stakeholder",
        plain=(
            "A stakeholder is any person or group whose interests a project's "
            "outcome affects, positively or negatively."
        ),
        longer=(
            "A stakeholder need not be on the project team or even aware of the "
            "project — the definition is about who is affected, not who is involved."
        ),
        defined_on=("/artifacts/stakeholder-register",),
    ),
    "velocity": GlossaryEntry(
        term="Velocity",
        plain=(
            "Velocity is the amount of work a team reliably finishes in one "
            "fixed work period, used to plan the next one."
        ),
        longer=(
            "Velocity is measured, not set: a team does not decide its velocity "
            "in advance, it is read off however much the team actually finished."
        ),
        see_also=("sprint", "backlog"),
    ),
    "wbs": GlossaryEntry(
        term="WBS",
        plain=(
            "WBS is short for a hierarchical decomposition of the total scope "
            "a project must deliver -- the structure itself, not a step of "
            "building it."
        ),
        longer=(
            "Each level of a WBS is a fuller decomposition of the level above it; "
            "the bottom level is small enough to estimate and assign with confidence."
        ),
        see_also=("work-breakdown-structure",),
        defined_on=("/artifacts/work-breakdown-structure",),
    ),
    "work-breakdown-structure": GlossaryEntry(
        term="Work breakdown structure",
        plain=(
            "A work breakdown structure is a hierarchical breakdown of "
            "everything a project must deliver, split into progressively "
            "smaller pieces."
        ),
        longer=(
            "It is organized around deliverables, not the calendar or the "
            "org chart, so a piece of it names a thing produced rather than a "
            "date or a person."
        ),
        see_also=("wbs", "critical-path"),
        defined_on=("/artifacts/work-breakdown-structure",),
    ),
}
