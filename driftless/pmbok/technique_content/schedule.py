"""Technique explanations for the schedule family (tt.FAMILIES["schedule"]).

A note on scope: Driftless today stores exactly one point estimate per task.
No ranges, no dependency edges, no calendars, no float. Several entries below
say so explicitly, because a reader following this guide inside the product
will hit that wall directly and deserves to be told why rather than left to
guess whether the feature is missing or the technique doesn't apply.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "schedule"

CONTENT: dict[str, TechniqueContent] = {
    "rolling_wave_planning": TechniqueContent(
        summary=(
            "Planning near-term work in detail and far-off work only roughly, refining it as it gets closer."
        ),
        when_to_use=(
            "Use it whenever the far end of the schedule genuinely cannot be broken down "
            "yet — the requirements aren't settled, a vendor hasn't been chosen, or an "
            "earlier phase's output will determine what the later phase even contains. "
            "It is the honest alternative to guessing detail you don't have."
        ),
        when_to_avoid=(
            "Don't reach for it as an excuse to skip planning work you actually know how to "
            "detail today — that just relabels procrastination as a technique. And don't use "
            "it past the point the far-out work has become knowable: a wave that's two weeks "
            "away and still a single placeholder line is a planning gap, not rolling wave."
        ),
        steps=(
            "Split the schedule horizon into a near wave (detailed, task-level) and one or "
            "more far waves (summary-level placeholders with a rough duration and owner).",
            "Decompose and estimate the near wave to the level of detail the team will "
            "actually execute against.",
            "Set a trigger for each far wave — a date, a milestone, or a decision point — "
            "at which it becomes the new near wave and gets decomposed in turn.",
            "When a wave's trigger fires, re-plan it in detail using whatever estimating "
            "technique fits the information now available, and update the plan.",
        ),
        outputs=(
            "A schedule with mixed granularity: detailed near-term tasks, summary-level "
            "future placeholders, and stated triggers for when each placeholder gets "
            "detailed.",
        ),
        pitfalls=(
            "The far-wave placeholder gets treated as a real commitment by anyone who "
            "doesn't know it's provisional — a stakeholder reads a one-line summary task as "
            "a firm date.",
            "The trigger never fires because nobody owns watching for it, so a wave stays "
            "undetailed well past the point it should have been broken down.",
            "Re-planning a wave quietly changes scope as well as detail, and the change "
            "never goes through change control because it's framed as \"just detailing what "
            'was already there".',
        ),
        worked_example=(
            "A clinic intake system project details the first six-week sprint task by task, "
            'and represents "Phase 2: reporting module" as one summary bar pending the '
            "vendor's data export API being finalized. When the vendor confirms the API "
            "spec in week five, the team decomposes Phase 2 into real tasks before the "
            "current wave ends."
        ),
        further_reading=("PMBOK-6 §6.2.2.3",),
    ),
    "precedence_diagramming_method": TechniqueContent(
        summary=(
            "Drawing the schedule as linked task boxes, so its order is a picture, not a memory."
        ),
        when_to_use=(
            "Use it once you have more than a handful of tasks with real dependencies "
            "between them and need to see the whole sequence at once — it's the "
            "representation that critical path method and schedule network analysis are "
            "both built on top of."
        ),
        when_to_avoid=(
            "For a short, mostly-linear list of tasks, drawing a formal network adds "
            "ceremony without adding insight — a simple ordered list does the job. And it's "
            "only worth building if you're also going to keep it updated as dependencies "
            "change; a diagram that's stale by week two is worse than no diagram, because "
            "people trust it anyway."
        ),
        steps=(
            "List every task as a node.",
            "For each pair of tasks with a real dependency, draw an arrow and record the "
            "relationship type — finish-to-start is the default, but start-to-start, "
            "finish-to-finish and start-to-finish all occur.",
            "Check the network for orphan nodes (a task with no predecessor and no "
            "successor is usually a missed dependency, not a genuinely isolated task) and "
            "for cycles, which mean two tasks were each recorded as depending on the other.",
            "Use the finished network as the input to critical path method or schedule "
            "network analysis.",
        ),
        outputs=(
            "A dependency network of task nodes and typed arrows that unambiguously encodes "
            "the sequence the work has to happen in.",
        ),
        pitfalls=(
            "Every arrow gets drawn as finish-to-start by default because it's the easiest "
            "relationship to reason about, even where the real constraint is start-to-start "
            "or finish-to-finish — this artificially lengthens the schedule.",
            "A dependency that's organizational preference (\"we'd like to do it in this "
            'order") gets recorded as a hard technical dependency, which then blocks '
            "compression options that were actually available.",
            "The diagram is built once at kickoff and never touched again, so it silently "
            "diverges from how the team is actually sequencing work.",
        ),
        worked_example=(
            'A backyard deck build records "pour footings" -> "set posts" -> "frame '
            'joists" as finish-to-start, but "install railings" as start-to-start with '
            '"stain deck boards" plus a two-day lag, since staining can begin once railing '
            "installation is under way rather than only after it completes."
        ),
        further_reading=("PMBOK-6 §6.3.2.1",),
    ),
    "dependency_determination": TechniqueContent(
        summary=(
            "Sorting each link between tasks into what is a fixed fact and what is really a choice."
        ),
        when_to_use=(
            "Use it while building the dependency network, specifically when you're deciding "
            "whether a sequencing choice is negotiable. It's the technique that tells you "
            "which arrows in a precedence diagram are safe to challenge when you need to "
            "compress the schedule and which ones aren't."
        ),
        when_to_avoid=(
            "Skip formal classification for a small project where the whole team already "
            "knows, informally, which orderings are real constraints and which are habit — "
            "writing it down there is overhead without a decision it's going to change."
        ),
        steps=(
            "For each dependency in the network, ask whether the sequence is inherent to the "
            'work itself (mandatory / "hard logic", e.g. concrete must cure before '
            "framing) or a preference the team or organization chose (discretionary / "
            '"soft logic", e.g. doing design review before code review because that\'s the '
            "team's convention).",
            "Separately, ask whether the dependency involves a party outside the project "
            "(external, e.g. a permit from a city office) or is entirely within the team's "
            "control (internal).",
            "Tag each dependency with both classifications.",
            "When you need to compress the schedule, look first at discretionary "
            "dependencies — those are the ones you can legally reorder or overlap without "
            "violating a real constraint.",
        ),
        outputs=(
            "Every dependency in the network tagged mandatory-or-discretionary and "
            "external-or-internal, so a later compression pass knows which arrows are "
            "actually movable.",
        ),
        pitfalls=(
            "A discretionary dependency gets treated as mandatory because \"that's how we've "
            'always done it", which quietly removes real compression options from '
            "consideration.",
            "An external dependency gets classified but not tracked separately with its own "
            "lead time and owner, so its risk to the schedule goes unmanaged until it's "
            "already late.",
            "The classification is done once and never revisited, even after the "
            "circumstance that made a dependency mandatory (a specific vendor, a specific "
            "regulation) has changed.",
        ),
        worked_example=(
            'On a museum exhibit build, "install glass display cases" must follow "cure '
            'the epoxy floor coating" — mandatory and internal. "Submit exhibit signage '
            'for curator sign-off" must follow "finalize signage copy" and involves a '
            'party outside the project team — mandatory and external. "Paint gallery '
            'walls" before "hang wayfinding signs" is discretionary and internal — the '
            "team could do it the other way if wall painting slips."
        ),
        further_reading=("PMBOK-6 §6.3.2.2",),
    ),
    "leads_and_lags": TechniqueContent(
        summary=(
            "Adjusting timing between two linked tasks so one starts early or is deliberately delayed."
        ),
        when_to_use=(
            "Use a lag when a dependency involves a real waiting period the successor can't "
            "shortcut (paint drying, a required review turnaround, curing concrete). Use a "
            "lead when part of the successor can safely start before the predecessor fully "
            "finishes, to compress the schedule without breaking the real dependency."
        ),
        when_to_avoid=(
            "Don't use a lead to paper over a dependency you haven't actually resolved — "
            "if the successor genuinely needs the predecessor's output to do its work, "
            "starting it early just produces rework once the real output arrives. And don't "
            "let a lag become the default way of adding schedule buffer; an unexplained lag "
            "on every task is padding wearing a lead/lag costume."
        ),
        steps=(
            "For each dependency, determine whether the successor can start before the "
            "predecessor finishes (a candidate for a lead) or must wait past the "
            "predecessor's finish for a reason specific to the work (a candidate for a lag).",
            "Quantify the lead or lag as a duration, with the reason recorded next to it — "
            "not just the number.",
            "Apply it in the schedule and check whether it changed which path is now critical.",
            "Revisit the assumption behind each lead or lag whenever the surrounding tasks' "
            "durations or scope change; the number was derived from a specific reason and "
            "goes stale with it.",
        ),
        outputs=(
            "Dependencies annotated with a signed offset (lead as negative, lag as "
            "positive) and the reason for each, feeding directly into critical path method.",
        ),
        pitfalls=(
            "A lead is applied without checking that the overlapping work is actually "
            "independent of the predecessor's unfinished portion, so the successor ends up "
            "redoing work once the predecessor's later output invalidates its early "
            "assumptions.",
            "A lag's reason is forgotten, so nobody notices when the underlying constraint "
            "goes away (a review SLA gets shortened, a cure time gets reformulated) and the "
            "schedule keeps carrying dead time.",
            "Leads and lags get used to hit a target date rather than to reflect reality, "
            "which produces a schedule that looks feasible on paper and isn't.",
        ),
        worked_example=(
            '"Apply base coat of paint" finishes, then a two-day lag is added before '
            '"apply top coat" because the base coat needs 48 hours to cure. Separately, '
            '"write API documentation" is given a five-day lead against "finalize API '
            'implementation", since the documentation team can draft the stable parts of '
            "the interface before the last edge cases are coded."
        ),
        further_reading=("PMBOK-6 §6.3.2.3",),
    ),
    "agile_release_planning": TechniqueContent(
        summary=(
            "Deciding which features ship in which release from a prioritized backlog and the team's known speed, not a fixed long-range schedule."
        ),
        when_to_use=(
            "Use it on a project where the team is delivering in short iterations against a "
            "backlog and scope is expected to change as feedback comes in — a product build "
            'where "what exactly release 3 contains" is meant to stay negotiable until '
            "close to release 3."
        ),
        when_to_avoid=(
            "Don't use it where a fixed external deadline requires a specific, "
            "contractually-defined scope on a specific date — a regulatory filing or a "
            "fixed-price deliverable needs a committed schedule, not a velocity-based "
            "forecast that moves as the team learns."
        ),
        steps=(
            "Prioritize the backlog so the highest-value, most-informative items are near the top.",
            "Measure the team's velocity — how much backlog it clears per iteration — over "
            "several completed iterations, not just the first one.",
            "Group backlog items into releases by walking down the prioritized list and "
            "filling each release to roughly the team's demonstrated velocity times the "
            "number of iterations before that release date.",
            "Re-run the grouping at the start of each iteration as velocity is confirmed and "
            "the backlog is re-prioritized, rather than treating the first plan as final.",
        ),
        outputs=(
            "A release plan: which backlog items are targeted for which release, built from "
            "actual measured velocity and updated on a cadence rather than fixed once.",
        ),
        pitfalls=(
            "Velocity from the first one or two iterations, which are usually depressed by "
            "ramp-up, gets used as the planning number for the whole project.",
            "A release plan built from velocity gets communicated externally as a fixed "
            "commitment, so the whole point of planning against actuals instead of a "
            "guess gets lost the moment it leaves the team.",
            "The backlog isn't re-prioritized between releases, so a release plan that made "
            "sense at kickoff ships stale, lower-value work while something more valuable "
            "waits its turn.",
        ),
        worked_example=(
            "A mobile expense-reporting app team clears roughly 30 story points per "
            "two-week sprint. With six sprints before the next quarterly release, they plan "
            "roughly 180 points of backlog into it, front-loading the highest-priority "
            "items — receipt photo capture and approval routing — and re-checking the plan "
            "each sprint as actual velocity comes in."
        ),
        further_reading=(),
    ),
    "analogous_estimating": TechniqueContent(
        summary=(
            "Estimate a task's duration or cost by pointing at a genuinely similar past "
            "task and scaling from what that one actually took."
        ),
        when_to_use=(
            "Reach for this when you have a comparable completed project or task to point "
            "at and need a number fast — early in planning, or for a rough order-of-"
            "magnitude estimate before detail exists to support anything more precise. It's "
            "the estimate you can produce in an afternoon from history you already have."
        ),
        when_to_avoid=(
            "Don't use it when the past project you're comparing to isn't actually "
            "comparable — different team, different technology, different scale — because "
            "the estimate then inherits a false sense of grounding it hasn't earned. And "
            "don't use it as the final estimate for a task the decision genuinely needs "
            "precision on; it's the least accurate of the four estimating techniques here "
            "precisely because it skips decomposition."
        ),
        steps=(
            "Find one or more completed tasks or projects that are genuinely similar in "
            "scope, complexity and context — not just similar in name.",
            "Record what the analogous work actually took, from real historical data rather "
            "than someone's memory of it.",
            "Adjust for the specific differences between the analogous work and the task at "
            "hand (bigger, smaller, unfamiliar tech, different team) and state the "
            "adjustment, not just the final number.",
            "Record the estimate along with which analogous task it was based on and what "
            "was adjusted, so it can be checked later.",
        ),
        outputs=(
            "A duration or cost estimate for the task, with the analogous reference and the "
            "adjustment reasoning recorded alongside it.",
        ),
        pitfalls=(
            "The comparison task is chosen because its number is convenient (fits the "
            "target date) rather than because it's actually the closest match.",
            "The adjustment step gets skipped, so real differences between the two projects "
            "(a junior team versus the senior team that did the original work, say) never "
            "get reflected in the number.",
            "The estimate is presented with more confidence than the method supports — a "
            "single analogous data point dressed up to look like a calibrated estimate.",
        ),
        worked_example=(
            "A team scoping a new internal-tools migration recalls that last year's CRM "
            "migration, comparable in data volume and integration count, took eleven weeks. "
            "They estimate this migration at roughly ten weeks, adjusting down slightly "
            "because two of the four integrations this time are ones the team has already "
            "built connectors for."
        ),
        further_reading=("PMBOK-6 §6.4.2.2",),
    ),
    "parametric_estimating": TechniqueContent(
        summary=(
            "Estimating by multiplying a known amount of work by a rate drawn from past data."
        ),
        when_to_use=(
            "Use it when the work is genuinely unit-based and you have a trustworthy rate "
            "for that unit: lines of code per hour for a well-understood codebase, square "
            "feet of drywall per crew-day, records migrated per hour for a data conversion. "
            "It scales cleanly and is fast once the rate is established."
        ),
        when_to_avoid=(
            "Don't use it where the rate itself is shaky — one data point dressed up as a "
            "calibrated statistic — or where the work doesn't actually scale linearly with "
            "the unit you're counting (the last 10% of a migration is rarely the same "
            "per-record cost as the first 10%, because it's the exceptions and edge cases). "
            "A parametric estimate is only as good as the rate behind it."
        ),
        steps=(
            "Identify the quantifiable unit that drives the work's size (units of "
            "production, lines of code, drawings, test cases, square footage).",
            "Establish a rate — duration or cost per unit — from historical data covering "
            "enough past instances to be a real average, not a single anecdote.",
            "Count or estimate the quantity of units the current task involves.",
            "Multiply quantity by rate, and separately flag any part of the task that won't "
            "scale linearly (setup time, one-time integration work) to be estimated on its "
            "own rather than folded into the rate.",
        ),
        outputs=(
            "A duration or cost estimate derived from quantity times a stated, sourced rate "
            "— reproducible by anyone who has the same rate and the same count.",
        ),
        pitfalls=(
            "The rate is calibrated on a different context (a different team's throughput, "
            "a different codebase's complexity) and applied here without adjustment.",
            "Nonlinear cost — setup, integration, exception handling — gets folded into the "
            "per-unit rate anyway, which understates estimates for small tasks and "
            "overstates them for large ones.",
            "The rate is never revisited once established, so it silently drifts out of "
            "date as tooling, team composition or the nature of the work changes.",
        ),
        worked_example=(
            "A data-migration task involves porting 40,000 customer records. The team's "
            "historical rate for this record type, averaged across three prior migrations, "
            "is 1,150 records per hour. They estimate roughly 35 hours for the transfer "
            "itself, and separately estimate eight hours of one-time schema-mapping setup "
            "that the rate doesn't cover."
        ),
        further_reading=("PMBOK-6 §6.4.2.3",),
    ),
    "three_point_estimating": TechniqueContent(
        summary=(
            "Combining an optimistic, a pessimistic, and a most-likely estimate into one figure."
        ),
        when_to_use=(
            "Use it whenever a task has real uncertainty and you have someone (or several "
            "people) who can credibly bound it with a best case, worst case and most likely "
            "case — new or unfamiliar work, work with dependencies outside your control, "
            "anything where a single-point guess would be overconfident."
        ),
        when_to_avoid=(
            "Don't use it for well-understood, repetitive work where the range would just "
            "collapse to the most-likely point anyway — that's overhead without benefit. "
            "And don't use it if the three points are all supplied by one person guessing "
            "under time pressure; the technique's value comes from someone actually "
            "reasoning about best/worst case, not from three numbers filled into a template."
        ),
        steps=(
            "For the task, gather three estimates: optimistic (O, everything goes right), "
            "pessimistic (P, everything that plausibly goes wrong does), and most likely "
            "(M, the realistic case).",
            "Combine them with either the triangular formula, "
            "E = (O + M + P) / 3, which weights all three points equally, or the beta/PERT "
            "formula, E = (O + 4M + P) / 6, which weights the most-likely estimate four "
            "times as heavily as either extreme and is the more common default.",
            "Optionally compute a standard deviation, SD = (P - O) / 6, to express the "
            "estimate's spread rather than just its center — useful when several such "
            "estimates need to be combined into a project-level confidence range.",
            "Record all three original inputs alongside the combined estimate, not just the "
            "final number — the range itself is information a single point throws away.",
        ),
        outputs=(
            "A combined single-point estimate (E) suitable for building the schedule, plus "
            "the three original inputs and, optionally, a standard deviation expressing "
            "confidence — noting that Driftless today stores only the final E, so the O/M/P "
            "spread has to live in the worked notes rather than the product's task record.",
        ),
        pitfalls=(
            "The pessimistic estimate gets softened because naming a truly bad outcome feels "
            "uncomfortable, which quietly turns three-point estimating back into a "
            "single-point guess with extra steps.",
            "The optimistic case is treated as achievable rather than as the best case, and "
            "the final estimate drifts toward it under schedule pressure.",
            "The triangular and beta/PERT formulas get mixed up mid-project, so estimates "
            "from different tasks aren't actually comparable even though they look like the "
            "same kind of number.",
        ),
        worked_example=(
            "A task to integrate a third-party payment gateway gets estimates of O = 3 days "
            "(the documented happy path holds), M = 6 days (typical integration work with "
            "one or two surprises), P = 14 days (the gateway's sandbox environment turns out "
            "unreliable, as it has on a past project). Beta/PERT gives "
            "E = (3 + 4*6 + 14) / 6 = 6.83 days, versus a plain average of "
            "(3 + 6 + 14) / 3 = 7.67 days — the beta/PERT figure sits closer to the "
            "most-likely case because it weights M four times as heavily as either tail."
        ),
        further_reading=("PMBOK-6 §6.4.2.4",),
    ),
    "bottom_up_estimating": TechniqueContent(
        summary=(
            "Estimating each smallest piece of work separately, then adding them up for the most accurate, most labor-intensive total."
        ),
        when_to_use=(
            "Use it when the work is decomposable to a level of detail people can estimate "
            "confidently, and the decision riding on the estimate is important enough to "
            "justify the time it takes — a firm bid, a budget commitment, a task close "
            "enough in the schedule that its estimate needs to be trustworthy rather than "
            "roughly right."
        ),
        when_to_avoid=(
            "Don't use it on work that isn't decomposable yet (see rolling wave planning) — "
            "forcing a WBS onto poorly understood work just produces confident-looking "
            "nonsense at the leaf level. And don't use it for a rough early estimate where "
            "the decomposition cost outweighs the value of the extra precision; analogous or "
            "parametric estimating gets you a usable number far faster."
        ),
        steps=(
            "Decompose the task into the smallest components that can each be estimated "
            "with reasonable confidence — typically informed by a WBS.",
            "Estimate each component independently, using whichever technique fits that "
            "component (analogous, parametric or three-point are all fair game at the leaf "
            "level).",
            "Sum the component estimates to get the task or project total.",
            "Add explicit contingency for integration and coordination overhead between "
            "components — summing leaf estimates alone systematically undercounts the cost "
            "of stitching the pieces together.",
        ),
        outputs=(
            "A total estimate built from a documented decomposition, where every leaf "
            "component's own estimate and basis is visible and traceable back into the sum.",
        ),
        pitfalls=(
            "The decomposition stops too early — components are still too coarse to "
            "estimate confidently, so the leaf-level estimates are really just analogous "
            "guesses wearing a bottom-up label.",
            "Integration overhead between components is never added, so the sum understates "
            "the real total even though every individual leaf estimate was accurate.",
            "The technique's cost — the time spent decomposing and estimating dozens of "
            "small components — gets spent on work where a rougher technique would have "
            "answered the question just as well.",
        ),
        worked_example=(
            "A kitchen renovation is decomposed into demolition, rough plumbing, rough "
            "electrical, drywall, cabinetry, countertop installation, flooring, painting and "
            "final fixtures — nine components, each estimated by the trade who'll do it. "
            "The components sum to 34 crew-days; the contractor adds three more days of "
            "contingency for the coordination and inspection gaps between trades that no "
            "single component's estimate accounted for."
        ),
        further_reading=("PMBOK-6 §6.4.2.5",),
    ),
    "critical_path_method": TechniqueContent(
        summary=(
            "Finding the longest chain of dependent tasks, the one whose length sets how soon the project can finish."
        ),
        when_to_use=(
            "Use it on any schedule with a real dependency network of more than a few tasks, "
            "whenever you need to know which tasks actually control the finish date versus "
            "which ones have room to slip without consequence. It's the standard way to "
            'answer "what happens to the finish date if this task runs long".'
        ),
        when_to_avoid=(
            "It needs a real dependency network with durations and logic to work from — "
            "don't attempt it on a task list that hasn't gone through precedence diagramming "
            "and dependency determination first, and don't treat its output as gospel if the "
            "durations feeding it are unreliable single-point guesses; garbage estimates in "
            "the network produce a confident-looking but wrong critical path out."
        ),
        steps=(
            "Build the dependency network (precedence diagramming method) with a duration "
            "estimate for every task.",
            "Run the forward pass: compute each task's earliest start and earliest finish, "
            "working from project start to project end.",
            "Run the backward pass: compute each task's latest start and latest finish, "
            "working from the project end date back to the start, without moving the finish "
            "date found by the forward pass.",
            "Compute float for each task (latest start minus earliest start). The chain of "
            "tasks with zero float is the critical path; everything else has room to slip by "
            "its float amount without moving the finish date.",
        ),
        outputs=(
            "The critical path itself (the specific chain of tasks), the project's earliest "
            "finish date, and a float value for every task — noting that Driftless currently "
            "stores one estimate per task with no dependency edges or calendar, so this "
            "network and its float values live outside the product, in a spreadsheet or "
            "diagram, until dependency tracking exists here.",
        ),
        pitfalls=(
            "A task with float gets treated as low-priority and starved of attention, and "
            "then genuinely slips past its float — becoming critical after the fact, with no "
            'one watching for it because "it wasn\'t on the critical path".',
            "The critical path is computed once at planning and never recalculated as actual "
            "progress diverges from the plan — the path itself moves as the project runs, "
            "and a stale critical path is actively misleading.",
            "Float on individual tasks gets consumed piecemeal by different people without "
            'coordination, so a chain of "small" delays on non-critical tasks quietly '
            "creates a new critical path nobody planned around.",
        ),
        worked_example=(
            "A trade-show booth build has two parallel chains: graphics production (5 days) "
            "-> vinyl printing (3 days) -> panel mounting (2 days), and frame fabrication "
            "(4 days) -> electrical wiring (3 days) -> lighting test (2 days). The graphics "
            "chain totals 10 days; the frame chain totals 9 days. The graphics chain is "
            "critical with zero float; the frame chain has 1 day of float, meaning frame "
            "fabrication could start a day late without moving the booth's completion date."
        ),
        further_reading=("PMBOK-6 §6.5.2.2",),
    ),
    "critical_chain_method": TechniqueContent(
        summary=(
            "Scheduling around resource limits, removing padding from individual tasks, and pooling that padding into shared buffers."
        ),
        when_to_use=(
            "Use it when resource contention, not just task dependency, is what's actually "
            "constraining your schedule — the same specialist needed on three chains at "
            "once, a single test rig every team wants at the same time — and when individual "
            "task estimates are known to carry hidden personal safety margin that's masking "
            "the project's real risk rather than managing it."
        ),
        when_to_avoid=(
            "Don't use it on a resource-unconstrained schedule where critical path method's "
            "simpler float-based view already answers the question — pooling buffers and "
            "tracking consumption is real overhead that only pays off once resource "
            "contention is a live problem. It also asks a lot of a team culturally: it "
            "requires people to submit estimates without their usual personal padding, which "
            "needs trust that the padding won't just be cut and never restored elsewhere."
        ),
        steps=(
            "Build the dependency network as in critical path method, but this time also "
            "identify every point where the same resource is needed on more than one chain "
            "at once.",
            "Re-sequence the network to resolve resource conflicts — the same person or "
            "resource can't be in two places, so one chain has to wait, changing which chain "
            "is actually longest.",
            "Strip individual safety margin out of each task's estimate, aiming for a "
            "realistic (roughly 50% confidence) duration rather than a padded one, and pool "
            "the removed safety into a single project buffer at the end of the critical "
            "chain and feeding buffers where a non-critical chain feeds into it.",
            "Track progress by buffer consumption rather than by individual task lateness: "
            "watch how much of the pooled buffer has been used relative to how much of the "
            "critical chain has been completed, and act when consumption is outpacing "
            "progress.",
        ),
        outputs=(
            "A resource-feasible schedule with the true critical chain identified, "
            "individual task padding removed, and pooled buffers (project buffer plus "
            "feeding buffers) whose consumption rate is the tracking signal — again outside "
            "Driftless's current single-estimate task model, since it has no concept of a "
            "shared buffer or a feeding chain today.",
        ),
        pitfalls=(
            "The safety-stripping step happens without the buffer-pooling step actually "
            "landing anywhere the team trusts, so people quietly keep their personal padding "
            "anyway — the estimates look reduced on paper but aren't in practice.",
            "Buffer consumption is tracked but never acted on — the whole point of watching "
            "the rate is to trigger intervention before the buffer runs out, and a buffer "
            "chart nobody responds to is just a critical path with extra math.",
            'This gets confused with critical path method because both produce a "the '
            'chain" answer — but a critical chain answer that ignores resource contention '
            "is just a critical path with the wrong name on it, and float and buffer are not "
            "interchangeable concepts.",
        ),
        worked_example=(
            "Two workstreams on a lab-equipment installation both need the same certified "
            "electrician at the same point in the schedule: wiring the fume hood and wiring "
            "the centrifuge bay. Critical path method, ignoring the conflict, would show "
            "both chains as independently non-critical. Critical chain method resequences "
            "the electrician onto the fume hood first, which makes that chain the true "
            "critical chain, strips the padding each task lead had privately added, and "
            "places a single project buffer at the end plus a feeding buffer where the "
            "centrifuge chain rejoins — tracked afterward by how much of that buffer has "
            "burned relative to how far along the chain is."
        ),
        further_reading=(),
    ),
    "resource_optimization": TechniqueContent(
        summary=(
            "Adjusting the schedule to fit real resource limits, either by delaying work or shifting it within slack."
        ),
        when_to_use=(
            "Use leveling when a resource is genuinely over-allocated — assigned to more "
            "work than it can do in the available time — and the schedule has to accept a "
            "later finish to reflect reality. Use smoothing when the resource picture is "
            "merely lumpy (idle some weeks, overloaded others) but the total demand fits "
            "within capacity, and you want to flatten the peaks without touching the finish "
            "date."
        ),
        when_to_avoid=(
            "Don't reach for smoothing when the resource is actually over-allocated — "
            "smoothing has no slack to work with once every non-critical task is already "
            "fully used, and forcing it there just hides an over-allocation the schedule "
            "needs to show. And don't apply either technique without first confirming the "
            "resource conflict is real and not an artifact of an out-of-date assignment "
            "list."
        ),
        steps=(
            "Chart resource demand against resource availability across the schedule to see "
            "where allocation exceeds capacity and where it doesn't.",
            "For a genuine over-allocation, apply leveling: delay or re-sequence the "
            "lower-priority task competing for the resource, accepting that this may push "
            "the project's finish date or consume float on tasks that had some.",
            "For a lumpy-but-feasible demand curve, apply smoothing instead: shift "
            "non-critical tasks only within their existing float, flattening peaks without "
            "changing the finish date.",
            "Re-check the critical path after leveling specifically — moving a task to "
            "resolve resource contention can create a new critical path that didn't exist "
            "in the logic-only network.",
        ),
        outputs=(
            "A resource-feasible schedule, with a record of which adjustments were leveling "
            "(finish date affected) versus smoothing (finish date untouched), so the impact "
            "on the commitment date is traceable rather than buried in a re-sequenced "
            "Gantt chart.",
        ),
        pitfalls=(
            "Leveling and smoothing get used interchangeably in conversation, so a "
            'stakeholder is told "we smoothed the schedule" when what actually happened '
            "was leveling that pushed the finish date — a quiet, easily missed commitment "
            "change.",
            "Leveling resolves the over-allocation on paper by assigning the resource to "
            "impossible overlapping hours in practice, because the adjustment was made to "
            "the chart without checking the resource's actual calendar.",
            "Smoothing is applied repeatedly across many small adjustments without anyone "
            're-checking the critical path, and one of those "just using slack" moves '
            "quietly eats float that another task needed.",
        ),
        worked_example=(
            "One structural engineer is assigned to both a bridge inspection report (due in "
            "three weeks, has two weeks of float) and a foundation redesign (due in three "
            "weeks, zero float) in the same week. Leveling delays the inspection report by "
            "one week, consuming its float and leaving the finish date for that deliverable "
            "unchanged but shifting when it's produced. Separately, the same engineer's "
            "workload on two other non-critical tasks is smoothed — moved a few days later "
            "within their existing slack — purely to avoid a workload spike, with no effect "
            "on either task's due date."
        ),
        further_reading=("PMBOK-6 §6.5.2.3",),
    ),
    "schedule_compression": TechniqueContent(
        summary=(
            "Shortening a schedule without cutting scope, by adding resources or overlapping tasks."
        ),
        when_to_use=(
            "Use it when a real, specific deadline pressure exists and the schedule as "
            "planned doesn't meet it — never as a default first move, but as a deliberate "
            "response to a stated need to pull the finish date in."
        ),
        when_to_avoid=(
            "Don't use it as a routine planning step (\"compress everything a bit just in "
            'case") — both techniques carry real, specific costs, and paying them without a '
            "concrete deadline forcing the tradeoff wastes money or adds risk for nothing."
        ),
        steps=(
            "Confirm the compression is needed against the critical path specifically — "
            "shortening a task that isn't on the critical path doesn't shorten the project "
            "at all.",
            "For crashing: identify which critical-path tasks can be shortened by adding "
            "resources, and compute the cost of each option per day saved (the cost-per-day "
            "slope), then choose the cheapest options first.",
            "For fast-tracking: identify critical-path tasks currently sequenced "
            "finish-to-start that could instead overlap, and check what rework risk that "
            "overlap introduces — you're now starting the successor on unfinished, "
            "potentially-changing input from the predecessor.",
            "Apply the chosen compression, then re-run critical path method — compression "
            "frequently creates a new critical path, and a second round of compression "
            "aimed at the old path wastes effort.",
        ),
        outputs=(
            "A shortened schedule for a stated cost (crashing) or a stated rework risk "
            "(fast-tracking), with the tradeoff explicit rather than implied.",
        ),
        pitfalls=(
            "Crashing adds cost and coordination overhead — more people on a task means more "
            "communication paths, onboarding time for the newly added resource, and "
            "sometimes negative returns past a point (Brooks's-law-style diminishing or "
            "reversing returns) — and rarely returns the linear time-for-money tradeoff the "
            "plan assumed going in.",
            "Fast-tracking trades schedule time for rework risk that shows up later and gets "
            "attributed to something else — the successor task built on the predecessor's "
            "unfinished output has to be partly redone once the predecessor's real output "
            "lands, and that rework cost rarely gets traced back to the fast-tracking "
            "decision that caused it.",
            "Compression is applied and the finish date is reported as fixed, without "
            "carrying forward the added cost or risk it was purchased with — the deadline "
            "looks met and the bill (in cost or in later rework) arrives separately.",
        ),
        worked_example=(
            'A product launch date moves up by two weeks. The team crashes "integration '
            'testing" by adding a second QA engineer, cutting it from ten days to six at '
            'roughly 1.5x the original cost for that task, and fast-tracks "write release '
            'notes" to start once the feature list is 80% locked rather than waiting for '
            "final code freeze — accepting that a late feature cut will mean rewriting part "
            "of the notes."
        ),
        further_reading=("PMBOK-6 §6.5.2.6",),
    ),
    "schedule_network_analysis": TechniqueContent(
        summary=(
            "The general term for techniques that build a project schedule from its task dependencies."
        ),
        when_to_use=(
            "Reach for this framing when you need to talk about analyzing the schedule "
            "network as a category — choosing which specific technique(s) below fit the "
            "situation — rather than as a standalone technique with its own distinct steps."
        ),
        when_to_avoid=(
            'Don\'t cite "schedule network analysis" in place of naming the actual technique '
            "you used — it's a category label, and reporting it as the method obscures "
            "whether the real work was critical path method, resource optimization, or "
            "something else, each of which has different assumptions and different "
            "failure modes."
        ),
        steps=(
            "Build the dependency network (precedence diagramming method) with durations, "
            "leads and lags applied.",
            "Choose the specific analysis the schedule needs: critical path method to find "
            "the driving sequence, resource optimization if resource contention is a "
            "factor, critical chain method if buffer-based tracking fits the project "
            "better, or a what-if scenario run to test the impact of a specific risk or "
            "assumption on the network.",
            "Run that specific technique and read its output back into the schedule.",
            "Repeat as the network changes — schedule network analysis is not a one-time "
            "pass, it's the ongoing discipline of re-deriving the schedule from the network "
            "whenever the network changes.",
        ),
        outputs=(
            "Whatever the chosen specific technique produces — a critical path, a "
            "resource-leveled schedule, a buffer-tracked chain, or a what-if comparison — "
            'read through this umbrella framing as "the current best schedule derived from '
            'the network".',
        ),
        pitfalls=(
            "The umbrella term gets used as if it were itself a technique with a "
            'procedure, producing vague advice ("do schedule network analysis") that '
            "doesn't tell anyone what to actually do next.",
            "A what-if scenario run is performed once to answer a specific question and "
            "then treated as the ongoing schedule, rather than as a single scenario compared "
            "against the baseline.",
            "Analysis stops after the first pass even though the network keeps changing, so "
            'the schedule\'s "current" critical path or resource picture is quietly stale.',
        ),
        worked_example=(
            "Ahead of a board presentation, a program manager runs three separate schedule "
            "network analyses on the same dependency network: a straight critical path run "
            "for the base case, a resource-optimization run reflecting a hiring freeze, and "
            "a what-if run modeling a two-week permit delay — presenting all three as "
            "distinct scenarios rather than a single number."
        ),
        further_reading=("PMBOK-6 §6.5.2.1",),
    ),
}
