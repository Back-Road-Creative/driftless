"""Technique explanations for the integration family (tt.FAMILIES["integration"]).

Three techniques: ``change_control_tools`` is the one with real teeth in this
product — driftless enforces change control structurally (a frozen approved
``Baseline``, a ``ChangeRequest`` whose approval mints a new baseline version)
rather than by policy alone. ``information_management`` and
``knowledge_management`` are easy to conflate; keep them apart deliberately —
one is about the system that stores and retrieves explicit information, the
other is about connecting people so tacit knowledge moves between them.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "integration"

CONTENT: dict[str, TechniqueContent] = {
    "change_control_tools": TechniqueContent(
        summary=(
            "Deciding whether a proposed change to an already-approved plan is accepted, and updating the plan only once it is."
        ),
        when_to_use=(
            "Once a Baseline exists with an approval date set, and someone wants to alter the "
            "scope, dates, or cost that baseline represents. Use it whenever the change would "
            "make current status reporting compare actuals to a plan nobody has actually "
            "agreed to anymore."
        ),
        when_to_avoid=(
            "Before a baseline is ever approved — a draft Baseline's lines can just be edited "
            "directly, because there is nothing frozen yet to protect. Also avoid routing "
            "every minor, in-tolerance adjustment through it: a board that rubber-stamps ten "
            "trivial requests a week stops reading the ones that matter. If the adjustment "
            "doesn't move an approved date or cost figure, it isn't a change to control."
        ),
        steps=(
            "Log the change as a ChangeRequest on the project — description and a raised date — "
            "with status left at its default, 'proposed'.",
            "Before anyone decides, assess the real impact: walk the BaselineLine rows for "
            "the affected tasks and anything downstream of them, not just the task the "
            "requester named.",
            "Bring the request and its assessed impact to whoever the project's change "
            "authority actually is, and record the decision as one of CHANGE_STATUSES.",
            "If approved, build the new Baseline: bump version, carry forward unaffected "
            "BaselineLine rows unchanged, and write new lines for whatever the change moved.",
            "Set the new Baseline's approval date, then link the ChangeRequest's "
            "resulting baseline id to it — the schema only allows that link once status is "
            "'approved', so cause and consequence stay tied together.",
            "Tell whoever reads the plan downstream (schedule views, cost baseline, "
            "milestones) that a new version exists, so nothing keeps citing the superseded "
            "one.",
        ),
        outputs=(
            "An approved ChangeRequest whose resulting baseline id names the version it produced.",
            "A new Baseline version with its own BaselineLine rows, sitting alongside every "
            "prior version rather than replacing it.",
            "A durable record of what was asked for, what it would have cost, and what was "
            "decided — including the requests that were rejected or withdrawn.",
        ),
        pitfalls=(
            "The emergency change made in the field and never logged afterward: the work "
            "happens, no ChangeRequest is ever raised, and the baseline silently stops "
            "matching reality with no record of why.",
            "Approving a request before its schedule and cost impact has actually been "
            "assessed — the CHECK constraint only stops the resulting baseline id from being set "
            "on anything but an approved request; it has no way to verify the approval was "
            "informed.",
            "Re-baselining so often, and so readily, that 'approved' stops meaning anything — "
            "if every slip gets absorbed into a fresh version instead of being questioned, the "
            "plan chases the actuals instead of the actuals being measured against the plan.",
            "Discarding a rejected or withdrawn request instead of keeping it — it has no "
            "resulting baseline id, but it is still the record of what was asked for and "
            "refused, and why.",
        ),
        worked_example=(
            "A community-center renovation has an approved Baseline v1 four months in. The "
            "contractor finds the electrical panel needs replacing: +$18,000, +2 weeks on that "
            "one task. The PM logs a ChangeRequest, then walks the BaselineLine rows for the "
            "panel task and the inspection and drywall tasks that depend on it, and finds the "
            "real schedule hit is 3 weeks once the dependency chain is included, not 2. The "
            "sponsor approves it with the corrected number. The PM creates Baseline v2, "
            "carrying forward every unaffected line as-is and writing new lines only for the "
            "panel, inspection, and drywall tasks, sets its approval date, and points the "
            "ChangeRequest's resulting baseline id at v2."
        ),
        further_reading=("PMBOK-6 §4.6.2.2",),
    ),
    "information_management": TechniqueContent(
        summary=(
            "The tools and habits for storing and finding project documents already written down."
        ),
        when_to_use=(
            "Whenever a fact the project generates repeatedly needs one durable, findable "
            "home — a budget line, a risk, a change request, a weekly status reading — so "
            "asking 'what is the current answer' is a lookup, not an investigation."
        ),
        when_to_avoid=(
            "When the thing that needs to move is judgment rather than a fact: why a call was "
            "made, what to watch out for next time, what a vendor is actually like to "
            "negotiate with. Forcing that into a form field produces a record that is "
            "technically searchable and practically useless. That is the knowledge management "
            "technique's job, not this one's."
        ),
        steps=(
            "Decide the artifact's structured home: a modelled row with fields the system "
            "computes over (a BudgetLine, a Risk, a ChangeRequest) if the data is structured, "
            "a NarrativeArtifact body if it is prose.",
            "Give it one owner and one place — matching driftless's one-row-per-(project, "
            "kind) convention for narrative artifacts — rather than letting duplicate drafts "
            "accumulate in parallel.",
            "Decide who updates the record and how often, and hold that cadence (a weekly "
            "StatusSnapshot, not a status page nobody has touched in a month).",
            "When a record is superseded, replace it explicitly rather than editing the old "
            "one in place, the way a new Baseline version supersedes the last — so a later "
            "search never turns up two conflicting 'current' answers.",
            "Confirm the record is actually reachable by whatever is supposed to read it — a "
            "report, a dashboard, a wizard's completeness check — because an artifact nothing "
            "queries is a file, not managed information.",
        ),
        outputs=(
            "A system of record for a specific category of project information, with a clear "
            "owner and refresh cadence.",
            "The retrievable artifact itself, in a form whatever needs it downstream can "
            "actually consume.",
        ),
        pitfalls=(
            "Recording the same fact through two paths — a hand-typed figure alongside a "
            "value the system already derives — so the two quietly drift apart and 'the "
            "system' now gives two different answers to one question.",
            "A repository so sprawling or so duplicated that finding the current version "
            "costs more than just asking the person who wrote it, which defeats the entire "
            "point of storing it.",
            "Confusing 'it is in the system' with 'someone will read it' — a record no "
            "process actually consumes is storage, not information management.",
        ),
        worked_example=(
            "A regional signage rollout keeps its planned spend as five BudgetLine rows, one "
            "per cost category, instead of a spreadsheet three people edit independently. "
            "When finance asks for planned spend by category, the answer is a single group-by "
            "query against BudgetLine, not a reconciliation between conflicting spreadsheet "
            "copies that were last saved on different days."
        ),
        further_reading=("PMBOK-6 §4.4.2.3",),
    ),
    "knowledge_management": TechniqueContent(
        summary=("Moving know-how from the person who has it to the person who needs it."),
        when_to_use=(
            "Onboarding someone into judgment a document can't transmit — reading a vendor's "
            "estimate skeptically, running a tense negotiation, recognizing a risk that looks "
            "routine but isn't. Also use it continuously through the project, whenever a "
            "decision's reasoning is worth more to a later reader than its outcome alone."
        ),
        when_to_avoid=(
            "When what's actually needed is a fact, a figure, or a document that already "
            "exists — routing that through a mentoring conversation instead of a lookup wastes "
            "both people's time and belongs to information management instead. Also avoid "
            "running it only as a single closeout ceremony: see the lessons-learned pitfall "
            "below."
        ),
        steps=(
            "Identify who holds knowledge nobody else on the project has — the estimator "
            "who's negotiated with this vendor before, the PM who's run this kind of cutover.",
            "Build a standing way to connect them to whoever needs it: pairing, a short "
            "recurring retro, a community of practice — not a one-off exit interview when "
            "someone is already walking out the door.",
            "Capture lessons as they happen into the project's lessons-learned narrative body, "
            "with enough of the reasoning attached that a later reader gets the 'why', not "
            "just the headline.",
            "Make that narrative something people actually open mid-project — attach it to "
            "the decisions it should inform, a similar change request or a similar risk — "
            "rather than filing it and moving on.",
            "Before anyone rolls off the project, have them walk a successor through the "
            "judgment calls they made, not just the documents they left behind.",
        ),
        outputs=(
            "A lessons-learned narrative body that grows continuously through the project, "
            "carrying the reasoning behind decisions, not only their outcomes.",
            "Working relationships and habits — pairing, a recurring retro — that are not "
            "themselves an artifact but are the reason later artifacts read as informed "
            "rather than boilerplate.",
        ),
        pitfalls=(
            "Lessons-learned theatre: a body written entirely at project closeout, when "
            "nobody is still around to act on it and nobody starting the next project reads "
            "it going in. driftless models lessons learned as one prose body per project, and "
            "a body that stays empty until the closeout meeting is a symptom of this, not a "
            "deliverable in its own right — capturing it continuously, into something people "
            "actually consult mid-project, is what makes the closeout version worth reading.",
            "Treating 'wrote it down' as the finish line — writing it down is "
            "information management; getting two specific people talking about a specific "
            "judgment call is the harder job this technique is actually for.",
            "Recording only the outcome of a decision and losing the reasoning behind it — a "
            "later reader who never saw the judgment exercised can't reuse it, only imitate "
            "the outcome blindly.",
            "Tying it to a single milestone instead of threading it through the project as a "
            "habit — a short retro every few weeks surfaces more usable knowledge than one "
            "retrospective at the end.",
        ),
        worked_example=(
            "A mid-size ERP migration runs a 20-minute retro at the end of every sprint, not "
            "just at project close. Partway through, the integration lead who handled a "
            "similar migration two years earlier explains, in that retro, why they insisted "
            "on a parallel-run week before cutover instead of a big-bang switch — a call that "
            "appears in no document because it was a judgment call made under uncertainty. "
            "The PM adds two sentences to the project's lessons-learned narrative capturing "
            "the reasoning, not just 'ran a parallel week'. When a similar cutover risk shows "
            "up in a later phase, a PM who wasn't in that room reads why the earlier call was "
            "made and reuses the reasoning, instead of repeating a checklist item without "
            "understanding it."
        ),
        further_reading=("PMBOK-6 §4.4.2.2",),
    ),
}
