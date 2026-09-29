"""Technique explanations for the resource family (tt.FAMILIES["resource"]).

Driftless's resource model is narrow on purpose: a ``Person`` has a role, a
``cost_rate`` and ``capacity_hours`` under a ``Department``, and a ``Task``
points at exactly one assignee (``driftless/models/people.py``,
``driftless/models/hierarchy.py``). There is no RACI matrix, no resource
breakdown structure, and no non-person resource (equipment, materials,
facilities) anywhere in the schema. Several entries below say plainly what
that means for a reader trying to use the technique inside the product versus
on paper next to it.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "resource"

CONTENT: dict[str, TechniqueContent] = {
    "pre_assignment": TechniqueContent(
        summary=("Naming who will do the work before the project is even approved or planned."),
        when_to_use=(
            "Use it when the assignment is already a fact you can't undo: a "
            "proposal or contract named a specific person or firm, a specialist "
            "skill exists in exactly one person in the business, or a sponsor "
            "made the assignment a condition of funding the project at all."
        ),
        when_to_avoid=(
            "Don't reach for pre-assignment as a convenience just because a "
            "name comes to mind first. Locking an assignment before the plan "
            "exists removes a degree of freedom you may need later: if the "
            "schedule shifts and that person is unavailable in the window "
            "that now matters, there is no fallback because no one else was "
            "ever considered. Run the estimate first and pre-assign only what "
            "genuinely cannot be otherwise."
        ),
        steps=(
            "Write down the specific reason the assignment is fixed (contract "
            "clause, unique skill, sponsor condition) — if you can't state one, "
            "it isn't a pre-assignment, it's a preference.",
            "Record the person and role in the plan before activity resource "
            "estimating happens for that work, so estimators treat it as a "
            "constraint rather than an open question.",
            "In Driftless, create or select the Person record and set the "
            "task's assignee at planning time rather than leaving it blank "
            "for later triage.",
            "Check that person's capacity in hours against everything else "
            "already pointing at them — a pre-assignment made in isolation is "
            "exactly the assignment most likely to over-allocate someone, "
            "because it was decided before the rest of the plan existed.",
        ),
        outputs=(
            "A named assignee attached to specific tasks before general resource planning begins",
            "A documented reason the assignment was fixed rather than "
            "estimated, for anyone auditing the plan later",
        ),
        pitfalls=(
            "Treating every stakeholder's casual suggestion as a pre-assignment, "
            "which quietly fills the team roster with names before anyone has "
            "checked whether the people are actually free.",
            "Forgetting to re-check capacity once the rest of the schedule is "
            "built — the pre-assigned person can end up double-booked because "
            "their slot was reserved first and never revisited.",
            "Using pre-assignment to avoid a hard staffing conversation instead "
            "of having it; the assignment looks settled but the underlying "
            "shortage hasn't gone anywhere.",
        ),
        worked_example=(
            "A regional bakery chain wins a contract to supply a grocery "
            "partner, and the contract names the chain's head baker, Priya, as "
            "the person who must sign off on the new product line's recipe "
            "scaling. The PM sets Priya as assignee on the recipe-scaling task "
            "the day the project is chartered, before any other activity "
            "resource estimating happens, and flags in the plan that the "
            "assignment is contractual, not a scheduling convenience."
        ),
        further_reading=("PMBOK-6 §9.3.2.3",),
    ),
    "negotiation": TechniqueContent(
        summary=(
            "Working out directly with whoever controls a resource the terms on which the project gets it."
        ),
        when_to_use=(
            "Use it any time a resource the project needs is under someone "
            "else's authority: a matrixed team member whose manager sets their "
            "priorities, a shared specialist several projects want, or a "
            "vendor whose price and terms aren't fixed."
        ),
        when_to_avoid=(
            "Don't negotiate what you can simply state. If you have direct "
            "authority over the person or budget in question, opening a "
            "negotiation invites a trade that didn't need to be offered. And "
            "don't negotiate under time pressure without a walk-away position "
            "— a deal made because the deadline was closer than the leverage "
            "usually costs more than the delay would have."
        ),
        steps=(
            "Work out what you actually need (hours, timing, duration) and "
            "the minimum that still makes the plan work, before the "
            "conversation starts.",
            "Find out what the other side needs — a functional manager isn't "
            "withholding a person out of spite, they have their own capacity "
            "problem to solve.",
            "Propose specific terms: dates, hours per week, and what the "
            "project gives up or offers in return (a later start, a shared "
            "cost, a swap of a different person's time).",
            "Write the agreed terms down and reflect them immediately as "
            "capacity in hours on the Person record, so the plan matches what "
            "was actually promised rather than what was first requested.",
        ),
        outputs=(
            "An agreed allocation of a person's or vendor's time that both "
            "sides will actually honor",
            "A record of the terms, so a later capacity dispute has something to point at",
        ),
        pitfalls=(
            'Negotiating a headline number ("half time") without pinning '
            "down which half, which weeks, and what happens when both "
            "projects need the same week.",
            "Treating a one-time negotiation as permanent — priorities shift, "
            "and an agreement that isn't revisited quietly becomes fiction "
            "while the plan still relies on it.",
            "Winning the negotiation and losing the relationship: getting the "
            "hours this time by burning goodwill that costs more the next "
            "time a resource is needed from the same manager.",
        ),
        worked_example=(
            "A logistics software company needs a database specialist who "
            "reports to the platform team for six weeks. The PM meets with "
            "the platform manager, learns the platform team has a compliance "
            "deadline in week three, and agrees to three weeks now and three "
            "weeks after the deadline instead of insisting on six consecutive "
            "weeks the other manager could not actually deliver."
        ),
        further_reading=("PMBOK-6 §9.3.2.2",),
    ),
    "influencing": TechniqueContent(
        summary=(
            "Getting cooperation from people the project manager has no "
            "formal authority over, using relationships, evidence, and "
            "persuasion instead of a reporting line that doesn't exist."
        ),
        when_to_use=(
            "Use it constantly in a matrixed or cross-department project, "
            "where most of the people whose cooperation the plan depends on "
            "don't report to the PM: getting a department to prioritize a "
            "task, getting a stakeholder to make a timely decision, getting a "
            "peer PM to release a shared resource early."
        ),
        when_to_avoid=(
            "Don't reach for influence when you actually have authority — "
            "asking permission for something you're entitled to decide trains "
            "people to expect you to ask next time too. And don't lean on "
            "influence alone when a decision genuinely needs escalating: "
            "spending weeks persuading a peer to do what a sponsor could "
            "simply direct is a slower path to the same place."
        ),
        steps=(
            "Identify whose cooperation you actually need and what's in it "
            "for them — influence that ignores the other person's incentives "
            "is just repeated asking.",
            "Bring evidence, not just a request: a schedule showing the "
            "downstream effect of a delay persuades a manager an appeal to "
            "urgency alone does not.",
            "Use the relationship you have, or build one before you need it "
            "— the first conversation you have with someone should not be the "
            "one where you're asking for something.",
            "Follow through visibly on anything you promised in return, so "
            "the next ask still has credit to draw on.",
        ),
        outputs=(
            "Cooperation obtained without an escalation, and the relationship "
            "still intact afterward",
        ),
        pitfalls=(
            "Mistaking charm for influence — a favor granted once because "
            "someone likes you doesn't survive repeated asks with nothing "
            "offered back.",
            "Over-using influence on people who actually need a decision "
            "escalated, which leaves a real authority gap unaddressed while "
            "looking like progress.",
            "Burning a relationship on a low-stakes ask, leaving nothing in "
            "reserve for the time the project genuinely needs it.",
        ),
        worked_example=(
            "A hospital-equipment installer's PM needs a facilities technician "
            "who reports to building operations, not to her, to reschedule a "
            "maintenance window around the install. Rather than escalating to "
            "the facilities director immediately, she shows the technician the "
            "specific two-hour overlap causing the conflict and offers to "
            "shift the install crew's start time to give him a wider window, "
            "and he agrees without anyone above either of them getting "
            "involved."
        ),
        further_reading=("PMBOK-6 §9.5.2.1",),
    ),
    "organizational_theory": TechniqueContent(
        summary=(
            "Using known patterns of how people and teams behave to decide how to lead the project team."
        ),
        when_to_use=(
            "Reach for it when a real structural decision is on the table: "
            "whether a cross-functional team should report through the PM or "
            "stay embedded in their functional department, how a distributed "
            "team's reporting lines should work, or why a team that was "
            "productive last month has stalled — a known stage of team "
            "formation (forming/storming/norming/performing) explains that "
            "far better than a guess about individual performance."
        ),
        when_to_avoid=(
            "This is the entry easiest to over-apply. A small, single-team, "
            "single-department project doesn't need a theory of "
            "organizational design — the reporting line is the department, "
            "full stop, and reaching for organizational theory here is "
            "over-thinking a question the org chart already answered. Use it "
            "when a structural choice genuinely has more than one reasonable "
            "answer, not to justify a decision that was obvious anyway."
        ),
        steps=(
            "Name the actual structural question: reporting line, incentive "
            "design, or team-stage diagnosis — organizational theory answers "
            "different questions differently, and a vague \"team isn't "
            "working\" isn't yet one of them.",
            "Check what Driftless's model already fixes for you: a task has "
            "exactly one assignee and a project has one accountable "
            "department (driftless/models/hierarchy.py), so a matrixed "
            "dual-reporting structure is something you manage in conversation "
            "and documentation, not something the tool represents.",
            "Apply the relevant known pattern — a forming team needs explicit "
            "norms more than it needs a pep talk; a team split across two "
            "departments needs an explicit escalation path because informal "
            "resolution won't cross the department boundary on its own.",
            "State the structural decision and the reason for it in the plan, "
            "so it can be revisited when the project's shape changes rather "
            "than silently persisting past the point it stopped fitting.",
        ),
        outputs=(
            "A stated, reasoned decision about team structure, reporting, or "
            "the team's current developmental stage",
            "An explicit escalation path for anything Driftless's single-"
            "assignee, single-department model doesn't represent on its own",
        ),
        pitfalls=(
            "Using organizational-theory language to dress up a decision that "
            "was really just convenience, which makes the decision harder to "
            "question later because it now sounds authoritative.",
            'Diagnosing a team as "storming" and treating that as an '
            "explanation that excuses inaction, instead of the trigger for the "
            "specific facilitation a storming team actually needs.",
            "Applying a structure that fits a large multi-team program to a "
            "five-person project, adding coordination overhead a team that "
            "size never needed.",
        ),
        worked_example=(
            "A craft brewery's packaging-redesign project pulls two people "
            "from marketing and one from operations. Three weeks in, the "
            "operations person keeps missing meetings because their "
            "department head is unaware they were ever committed. The PM "
            "recognizes this as a reporting-line gap rather than a motivation "
            "problem, and sets up a standing biweekly check-in with the "
            "operations department head — not more meetings for the assignee "
            "— to close it."
        ),
        further_reading=("PMBOK-6 §9.1.2.3",),
    ),
    "virtual_teams": TechniqueContent(
        summary=(
            "Building a team that rarely shares a physical location, on purpose and with care."
        ),
        when_to_use=(
            "Use it whenever the team is distributed by necessity: remote "
            "hires, a specialist who works from a different city, a client-"
            "side team member who was never going to relocate. It is a fact "
            "of the team's makeup to manage well, not a discretionary choice "
            "to opt out of."
        ),
        when_to_avoid=(
            "Virtual teaming is not a cost-saving default to reach for "
            "whenever colocation is inconvenient. It trades away the "
            "incidental communication colocation buys for free — the "
            "overheard conversation that surfaces a misunderstanding before "
            "it becomes a defect, the five-minute hallway question that would "
            "have taken a scheduled call otherwise. If the work genuinely "
            "depends on tight, fast-turnaround collaboration and colocation "
            "is actually available, don't choose virtual to save an office "
            "cost and then be surprised when coordination gets worse."
        ),
        steps=(
            "Name the specific communication colocation would have given you "
            "for free — status awareness, quick clarification, informal "
            "trust-building — and build a deliberate replacement for each "
            "one rather than assuming video calls cover all of it.",
            "Set explicit norms: response-time expectations, which channel "
            "is for what, and core overlap hours if the team spans time "
            "zones, written down rather than left to be inferred.",
            "Schedule informal contact on purpose — a virtual team that only "
            "ever talks about status never builds the trust that makes "
            "raising a problem early feel safe.",
            "Over-communicate context in writing: decisions, rationale, and "
            "changes that a colocated team would absorb by osmosis have to "
            "be stated for a virtual one or they simply don't reach everyone.",
        ),
        outputs=(
            "Documented communication norms and channels the whole team actually uses",
            "A team that stays informed and coordinated without relying on "
            "incidental, in-person contact",
        ),
        pitfalls=(
            "Assuming a chat tool and a weekly call replace what colocation "
            "gave for free, then being surprised months later that "
            "misunderstandings surface as finished, wrong work instead of as "
            "a quick correction.",
            'Letting time-zone overlap shrink to nothing, so "the team" is '
            "really two teams that hand off asynchronously and rarely talk "
            "in real time at all.",
            "Skipping the informal contact because it doesn't look like work "
            "— the trust it builds is what makes someone flag a problem in "
            "week two instead of hiding it until week eight.",
        ),
        worked_example=(
            "A specialty coffee roaster's e-commerce project has a backend "
            "developer in Portland and a data analyst in Manila, five time "
            "zones apart. The PM sets a two-hour daily overlap window for "
            "synchronous questions, requires every decision to be written in "
            "the project's shared doc rather than said only on a call, and "
            "puts a fifteen-minute unstructured video chat on the calendar "
            "every Friday that has no status agenda at all."
        ),
        further_reading=("PMBOK-6 §9.4.2.2",),
    ),
    "colocation": TechniqueContent(
        summary=(
            "Putting most of a project team in one physical workspace to get faster, more informal communication."
        ),
        when_to_use=(
            "Use it when the work genuinely needs tight, fast-turnaround "
            "collaboration — early design, a crunch period, a crisis response "
            "— and the people involved and the budget can actually support "
            'putting them in one place, even temporarily (a shared "war '
            'room" for two weeks counts).'
        ),
        when_to_avoid=(
            "Colocation is expensive — office space, relocation, or travel — "
            "and often simply not available: team members may be permanent "
            "remote hires, in different cities by necessity, or the budget "
            "doesn't stretch to a shared workspace. It is not the default-"
            "correct answer to a coordination problem; when it isn't "
            "available, the honest response is deliberate virtual-team "
            "practice (see above), not treating the coordination gap as "
            "unsolvable."
        ),
        steps=(
            "Identify which part of the work actually benefits from "
            "colocation — usually a specific phase, not the whole project — "
            "so you're not paying for shared space the team doesn't need for "
            "the full duration.",
            "Confirm the people who matter most to that phase can actually "
            "be there; colocating three of five people and leaving the other "
            "two remote often just relocates the coordination problem rather "
            "than solving it.",
            "Set up a shared, visible workspace — a team room, a physical "
            "board — that makes status and blockers visible without a "
            "meeting, which is the actual benefit colocation is buying.",
            "Plan the end of the colocation period as deliberately as the "
            "start, so the team has a real transition plan back to distributed "
            "work instead of an abrupt drop in communication.",
        ),
        outputs=(
            "A team physically positioned to communicate quickly during the period that needed it",
            "A shared workspace that surfaces status and blockers without a scheduled meeting",
        ),
        pitfalls=(
            "Colocating for the whole project when only one phase needed it, "
            "which spends the budget on space the later, more independent "
            "work didn't require.",
            "Assuming colocation alone fixes a team that has a real conflict "
            "or unclear roles — proximity makes good communication faster, it "
            "doesn't manufacture communication that wasn't going to happen "
            "anyway.",
            "Ending the colocation period abruptly with no transition, so the "
            "team's coordination quality falls off a cliff the day the shared "
            "space closes instead of stepping down gradually.",
        ),
        worked_example=(
            "A small architecture firm colocates its four-person team for the "
            "three-week schematic design phase of a client renovation in a "
            "borrowed conference room, because the phase depends on fast "
            "back-and-forth sketching that email and video calls slow down "
            "badly. Once schematic design is approved, the team returns to "
            "its normal, mostly remote working pattern for construction "
            "documentation, which doesn't need the same tempo."
        ),
        further_reading=("PMBOK-6 §9.4.2.1",),
    ),
    "training": TechniqueContent(
        summary=(
            "Deliberately building a skill or certification a team member "
            "needs but doesn't yet have, aimed at a specific project need "
            "rather than general professional development."
        ),
        when_to_use=(
            "Use it when the gap is real and the timeline allows for it: a "
            "team member needs a tool, method or compliance certification the "
            "project genuinely requires, and there's enough runway before the "
            "work that needs it starts for the training to actually land."
        ),
        when_to_avoid=(
            "Don't schedule training as a box to check. The test of training "
            "is whether it changes what the person does at work, not whether "
            "a certificate was issued — a two-day course six weeks before the "
            "skill is used, with no practice in between, usually produces the "
            "certificate and not the behavior change. If the timeline can't "
            "support the skill being used soon after it's taught, either "
            "delay the training closer to when it's needed or acquire the "
            "skill instead of manufacturing it under time pressure."
        ),
        steps=(
            "Name the specific task the person can't yet do, not a general "
            'skill area — "can run the new deployment pipeline unassisted" '
            'trains differently than "learn DevOps."',
            "Check the timing: training that isn't followed by an "
            "opportunity to use the skill within a few weeks mostly evaporates "
            "before it's needed.",
            "Budget the person's capacity in hours for the training itself, not "
            "just the certificate cost — time in training is time not spent "
            "on assigned tasks, and a plan that ignores that quietly "
            "over-allocates them.",
            "Verify afterward with the actual task, not a survey: have them "
            "do the thing the training was for and see whether it worked, "
            "before the project depends on it under real pressure.",
        ),
        outputs=(
            "A team member who can perform the specific task the project "
            "needed, verified against the task itself",
            "An accurate account of the capacity in hours the training actually cost the schedule",
        ),
        pitfalls=(
            "Measuring training success by attendance or a certificate "
            "instead of by whether the behavior on the job actually changed.",
            "Scheduling training so far ahead of when the skill is needed "
            "that it has to be relearned anyway, wasting the capacity spent "
            "on it the first time.",
            "Training one person on a skill the whole team needs, creating a "
            "single point of failure the training was supposed to reduce, not "
            "create.",
        ),
        worked_example=(
            "A commercial print shop is adopting a new imposition tool for a "
            "large catalog job starting in three weeks. Rather than sending "
            "the prepress operator to a certification course scheduled two "
            "months out, the PM arranges a two-day hands-on session with the "
            "vendor the week before the catalog job starts, then has the "
            "operator run a real small job through the new tool before the "
            "catalog work depends on it."
        ),
        further_reading=("PMBOK-6 §9.4.2.6",),
    ),
    "team_building": TechniqueContent(
        summary=(
            "Deliberate activities that build how well a team works together, not just its skills."
        ),
        when_to_use=(
            "Use it early in a new team's life, when membership changes "
            "significantly, or when a team is functioning but not "
            "collaborating — people are doing their individual tasks "
            "correctly but not catching each other's problems or sharing "
            "context, which a status meeting doesn't fix and an off-site "
            "sometimes does."
        ),
        when_to_avoid=(
            "Don't reach for a team-building activity as a substitute for "
            "solving a structural problem: unclear roles, a genuine resource "
            "conflict, or a manager who won't release someone's time. An "
            "exercise doesn't fix a scheduling conflict, and using it to paper "
            "over one just delays the moment the real problem surfaces. And "
            "don't treat it as a one-time event — a single off-site early on "
            "doesn't sustain a team through a long project without ongoing "
            "reinforcement."
        ),
        steps=(
            "Diagnose what's actually missing — trust, shared context, or "
            "clarity about roles — since the activity that fixes one doesn't "
            "necessarily fix the others.",
            "Pick an activity proportional to the problem: a recurring short "
            "retrospective for an ongoing coordination issue, a single "
            "workshop for a one-time role-clarity gap.",
            "Make it genuinely collaborative, not a lecture — team building "
            "that's really a status update with snacks doesn't build "
            "anything.",
            "Reinforce it in the team's regular working pattern afterward; "
            "an isolated activity with no follow-through fades within a "
            "couple of weeks.",
        ),
        outputs=(
            "A team with clearer shared understanding of roles and better "
            "working trust than before the activity",
        ),
        pitfalls=(
            "Running a team-building exercise to avoid having a specific, "
            "uncomfortable conversation about a real conflict, which the "
            "activity was never going to substitute for.",
            "Treating team building as a single kickoff event rather than an "
            "ongoing practice, so its effect decays well before the project "
            "ends.",
            "Mandating participation in a way that makes the activity itself "
            "feel like one more task assigned from above, which undermines "
            "the trust it was meant to build.",
        ),
        worked_example=(
            "A boutique event-planning company staffs a wedding-season "
            "project with two planners who have never worked together. Three "
            "weeks in, tasks are getting done but neither planner is flagging "
            "the other's risks early. The PM runs a ninety-minute working "
            "session where the two of them map out who owns which client "
            "touchpoints and where the handoffs are, rather than assigning "
            "more individual tasks and hoping coordination improves on its "
            "own."
        ),
        further_reading=("PMBOK-6 §9.4.2.4",),
    ),
    "recognition_and_rewards": TechniqueContent(
        summary=(
            "Formally acknowledging and rewarding behavior the project needs "
            "more of — explicitly tied to what actually helped the project, "
            "not handed out generically for morale."
        ),
        when_to_use=(
            "Use it when you can name the specific behavior you're "
            "reinforcing and it's one you genuinely want repeated: a person "
            "who flagged a risk early, a pair who fixed a shared bottleneck "
            "together, a team that hit a hard deadline through real "
            "collaboration."
        ),
        when_to_avoid=(
            "Be careful what you're actually rewarding, because you will get "
            "more of it. An individual award for work that needed "
            "collaboration teaches people to protect credit instead of "
            "sharing it. Rewarding a hero who saved a deadline with a "
            "weekend of unplanned overtime teaches the team that heroics are "
            "the expected response to bad planning, rather than fixing the "
            "planning that made the heroics necessary in the first place. If "
            "you find yourself about to reward the fix, ask first whether the "
            "problem it fixed should have been prevented."
        ),
        steps=(
            "Name the specific behavior before deciding on the reward — "
            '"good work this quarter" reinforces nothing in particular and '
            "teaches nothing repeatable.",
            "Check whether the behavior was actually collaborative or "
            "individual, and match the reward's shape to it: a team outcome "
            "gets a team recognition, not a single name on it.",
            "Ask whether the situation being rewarded should have been "
            "preventable — if a hero saved a deadline that a better plan "
            "would have made unnecessary, fix the plan and recognize the "
            "effort quietly rather than celebrating the rescue publicly.",
            "Deliver the recognition close to the event, not batched into an "
            "end-of-project ceremony where the specific behavior has been "
            "forgotten by everyone including the person who did it.",
        ),
        outputs=(
            "A specific behavior publicly reinforced, with the team able to see what earned it",
        ),
        pitfalls=(
            "Rewarding the visible fix and never asking why the problem "
            "existed, which reliably produces more visible fixes and no fewer "
            "underlying problems.",
            "Giving individual recognition for work that was actually a team "
            "effort, which teaches the team to compete for credit on the next "
            "collaborative task instead of sharing it.",
            "Rewarding hours worked (staying late, working weekends) rather "
            "than outcomes, which reinforces overwork as the default response "
            "to a schedule problem instead of raising the schedule problem "
            "itself.",
        ),
        worked_example=(
            "A regional insurance broker's claims-system migration project "
            "nearly misses a regulatory deadline because two analysts spot a "
            "data-mapping error the week before go-live and work through the "
            "weekend to fix it. The PM recognizes their effort directly with "
            "the pair, but does not make the weekend rescue the project's "
            "headline story — instead the postmortem asks why the mapping "
            "error wasn't caught in the review three weeks earlier, and the "
            "review step's checklist is fixed for the next phase."
        ),
        further_reading=("PMBOK-6 §9.4.2.5",),
    ),
    "individual_and_team_assessments": TechniqueContent(
        summary=(
            "Using a structured tool, like a survey or profile, to surface team strengths and friction points."
        ),
        when_to_use=(
            "Use it at team formation to understand what the group actually "
            "has to work with, or when a team is visibly struggling and it "
            "isn't clear whether the cause is a skills gap, a working-style "
            "mismatch, or something else — an instrument can separate those "
            "explanations faster than guessing."
        ),
        when_to_avoid=(
            "Not every instrument on the market is worth the time it takes: "
            "some working-style and personality assessments are backed by "
            "solid, replicated evidence, and some are closer to "
            "astrology-with-a-report-format — plausible-sounding, memorable, "
            "and not actually predictive of anything. Don't pick one because "
            "it's popular or fun to discuss; check what it's actually "
            "validated to measure before you use its output to make a real "
            "staffing or coaching decision. And don't run one just to have "
            "run one — an assessment with no follow-up action wastes the "
            "team's time and teaches them the exercise doesn't matter."
        ),
        steps=(
            "Decide what you're actually trying to learn — skill gaps, "
            "working-style friction, or team dynamics — since different "
            "instruments measure different things and a mismatch wastes the "
            "exercise.",
            "Check the instrument's actual evidence base rather than its "
            "marketing; a skills inventory scored against real task history "
            "is on firmer ground than a proprietary personality typology with "
            "no published validity data.",
            "Run it with the team's understanding of why, and how the "
            "results will and won't be used — an assessment that feels like "
            "covert evaluation gets guarded, unreliable answers.",
            "Turn at least one result into a concrete action — a training "
            "plan, a changed pairing, an adjusted role — or the assessment "
            "was theater.",
        ),
        outputs=(
            "A clearer, evidence-grounded picture of the team's skills, "
            "working styles, or points of friction",
            "At least one concrete change made because of what the assessment showed",
        ),
        pitfalls=(
            "Treating an unvalidated personality typology as if it were "
            "diagnostic, and making real staffing decisions off a report that "
            "doesn't actually predict on-the-job behavior.",
            "Running the assessment and filing the results without acting on "
            "them, which teaches the team the exercise was performative.",
            "Using a team-level survey result to single out one person "
            "publicly, which turns a diagnostic tool into a punishment and "
            "guarantees dishonest answers on the next one.",
        ),
        worked_example=(
            "A small veterinary-software startup forms a five-person team for "
            "a new client-portal project, three of whom have never worked "
            "together. The PM runs a lightweight skills inventory scored "
            "against each person's actual prior project history rather than a "
            "generic personality quiz, finds that nobody on the team has "
            "shipped an accessibility-compliant interface before, and "
            "schedules targeted training (see above) before that gap becomes "
            "a launch-week discovery."
        ),
        further_reading=("PMBOK-6 §9.4.2.7",),
    ),
    "conflict_management": TechniqueContent(
        summary=(
            "Resolving disagreement between team members on purpose, by picking a response that fits the situation."
        ),
        when_to_use=(
            "Use it whenever a disagreement is affecting the work — not just "
            "personality friction, but a real difference over approach, "
            "priority, or resource claim that two people aren't resolving on "
            "their own. The earlier it's addressed, the fewer of the "
            "responses below require force."
        ),
        when_to_avoid=(
            "Don't manage a genuine one-off preference difference as if it "
            "were a conflict requiring a formal response — some "
            "disagreements resolve themselves in a five-minute conversation "
            "and inflating them into a facilitated process wastes everyone's "
            "time and signals the difference mattered more than it did."
        ),
        steps=(
            "Identify which of five response modes actually fits: withdraw/"
            "avoid (retreat from an actual or potential conflict), smooth/"
            "accommodate (emphasize agreement over difference), compromise/"
            "reconcile (find a solution that partially satisfies everyone), "
            "force/direct (push one viewpoint through, usually using "
            "positional power), or collaborate/problem-solve (incorporate "
            "multiple viewpoints into a solution everyone can support). They "
            "are not interchangeable defaults and not equally good — pick the "
            "one the situation actually calls for.",
            "Reach for collaborate/problem-solve first when time allows: it's "
            "the mode most likely to produce a solution that actually holds, "
            "because everyone involved helped build it.",
            "Reach for force/direct only when time pressure genuinely doesn't "
            "allow collaboration — a live production incident, a decision "
            "due in the next hour — and be explicit that you're using it, "
            "because a forced decision that isn't acknowledged as forced "
            "reads as collaboration that failed.",
            "Be honest that smoothing defers the problem rather than solving "
            "it: it can be the right short-term move to keep a meeting "
            "productive, but if the underlying disagreement never gets "
            "revisited, it will resurface, usually at a worse moment.",
        ),
        outputs=(
            "A resolved (or deliberately deferred, and named as such) "
            "disagreement, with the people involved aware of which response "
            "mode was used and why",
        ),
        pitfalls=(
            "Defaulting to smoothing because it's the most comfortable mode "
            "in the room, which reliably produces the same disagreement again "
            "later, often with more at stake.",
            "Using force/direct as a first resort because it's fast, which "
            "resolves the immediate disagreement but teaches the losing party "
            "to stop raising concerns rather than to trust the process.",
            "Treating compromise as automatically fair because it splits the "
            "difference — a compromise that leaves the technically correct "
            "position half-implemented can produce a worse outcome than "
            "either original position on its own.",
        ),
        worked_example=(
            "A custom cabinetry shop's two lead carpenters disagree over "
            "whether to build a client's kitchen island with a traditional "
            "joinery method (slower, more durable) or a faster mechanical-"
            "fastener method, and the disagreement is stalling the cut list. "
            "With three days of schedule slack available, the PM brings both "
            "carpenters together to walk through the client's actual "
            "priorities (this piece will see heavy daily use) and lets them "
            "jointly land on the joinery method — collaborate/problem-solve — "
            "rather than picking a side herself. Two weeks later, a similar "
            "disagreement comes up the morning of a delivery deadline with no "
            "slack left, and she directs the faster method herself, and says "
            "out loud that she's doing so because there's no time to work it "
            "out together this time."
        ),
        further_reading=("PMBOK-6 §9.5.2.1",),
    ),
}
