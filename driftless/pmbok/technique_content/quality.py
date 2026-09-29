"""Technique explanations for the quality family (tt.FAMILIES["quality"]).

Quality techniques attract the vaguest writing in the whole standard —
"continuously improve" is not guidance. Every entry here is written to
survive a reader asking "so what do I do on Monday?"

driftless has no storage for audit findings, checklists, statistical
samples, or control charts. It has ``QualityMetric`` (a named, directional
threshold) and ``QualityMeasurement`` (a dated target/actual reading against
one). Where a technique's output has nowhere to land in this product today,
that is said plainly rather than implied away.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "quality"

CONTENT: dict[str, TechniqueContent] = {
    "root_cause_analysis": TechniqueContent(
        summary=(
            "Tracing a problem back to the condition that, once fixed, stops the whole pattern recurring."
        ),
        when_to_use=(
            "A recurring defect, a pattern showing up across more than one report or project, "
            "or a single problem expensive enough that a repeat of it would cost more than the "
            "investigation."
        ),
        when_to_avoid=(
            "A genuine one-off with no pattern behind it. A full root cause analysis on an "
            "isolated defect can cost more than the defect itself — log it, fix it, and move "
            "on unless it recurs."
        ),
        steps=(
            "Write the problem down as an observed effect, not a diagnosis — "
            "'14% of returned units failed the seal test', not 'bad supplier'.",
            "Ask why that effect happened, and write the answer as something you have "
            "evidence for, not an assumption.",
            "Ask why again of that answer, and keep going (five whys) until the chain reaches "
            "something someone can actually change, and that is not itself just another "
            "symptom restated.",
            "Cross-check the chain against a fishbone/Ishikawa diagram sorted by category "
            "(method, machine, material, people, measurement, environment) so a "
            "plausible-but-wrong single chain doesn't crowd out a second contributing cause.",
            "For a cause with more than one contributing path, or safety-critical work, build "
            "a fault tree working backward from the failure through the combinations of "
            "conditions that produce it.",
            "Test the candidate root cause: would removing it have prevented this occurrence, "
            "and would it prevent the next one? If either answer is no, keep digging.",
            "Assign an owner and a corrective action to the confirmed root cause, and record "
            "the discarded intermediate causes too — they tend to resurface.",
        ),
        outputs=(
            "A documented cause chain.",
            "A confirmed root cause, distinguished in writing from the symptoms found along "
            "the way.",
            "A corrective action with a named owner.",
        ),
        pitfalls=(
            "Stopping at the first plausible cause that happens to implicate nobody in the room.",
            "Landing on 'human error' or 'miscommunication' — that names an outcome, not a "
            "cause; ask why the error was possible in the first place.",
            "Single-cause tunnel vision when two or more independent causes combined to "
            "produce the failure.",
            "Re-running a root cause analysis on a symptom that was already investigated, "
            "without checking the earlier record first.",
        ),
        worked_example=(
            "A fit-out contractor, Larch & Rowe Builders, logs three separate callbacks in one "
            "quarter for water intrusion around the same window flashing detail, on unrelated "
            "projects. The site super's first instinct is 'the installer rushed it.' Five "
            "whys: rushed — why? — the crew was behind schedule — why? — the flashing detail "
            "wasn't on the standard install checklist — why? — the checklist was last updated "
            "before that window model was approved for use — why? — there's no step that "
            "links a product substitution to a checklist update. Root cause: no trigger "
            "connects material substitutions to checklist revisions. The fix is a "
            "checklist-review step added to the substitution approval, not retraining the "
            "installer."
        ),
        further_reading=("PMBOK-6 §8.2",),
    ),
    "audits": TechniqueContent(
        summary=(
            "A structured, independent check of whether the project's actual quality process "
            "was followed — as distinct from whether the product it produced meets its "
            "requirements."
        ),
        when_to_use=(
            "On a routine cadence, before a major deliverable handoff, after a serious quality "
            "escape to check whether the process failed or was simply skipped, or where a "
            "certification or compliance obligation requires it."
        ),
        when_to_avoid=(
            "When the process being audited is one the team doesn't believe is workable — fix "
            "the process first, or the audit measures compliance with a rule nobody follows "
            "and becomes theatre. Also avoid auditing when the real question is whether one "
            "specific product is good; that's testing/inspection, not an audit."
        ),
        steps=(
            "Define the standard being audited against — the actual documented process, not "
            "an assumed best practice.",
            "Assign an auditor who did not do the work being checked.",
            "Choose a sample of activities or records: recent work, plus at least one item "
            "flagged as risky.",
            "Compare what happened — interviews, records, artifacts — against what the "
            "process says should have happened.",
            "Record each gap as a finding: what the process required, what actually happened, "
            "and the evidence for it.",
            "Separate findings that are process failures (the process itself doesn't fit how "
            "the work actually happens) from findings that are compliance failures (the "
            "process was workable and wasn't followed).",
            "Agree corrective actions and a follow-up date with the process owner, not only "
            "with the team that was audited.",
        ),
        outputs=(
            "An audit report listing findings against the stated process.",
            "Agreed corrective actions with owners and a follow-up date.",
            "Good practices identified that are worth reusing elsewhere on the project.",
        ),
        pitfalls=(
            "Auditing compliance with a process nobody believes in — teams learn to perform "
            "for the audit rather than change how they work; fix or retire the process "
            "instead.",
            "An auditor who is also accountable for the result being audited, so findings get "
            "softened.",
            "Treating a clean audit as proof the product is good. An audit checks whether the "
            "process was followed, not whether the output meets spec — pair it with testing "
            "or inspection for that question.",
            "Findings that nobody is assigned to actually fix.",
        ),
        worked_example=(
            "At Larch & Rowe, a quarterly audit of the change-order approval process finds "
            "that 6 of 20 sampled change orders were verbally approved on site, with paperwork "
            "filed after the fact. The audit doesn't fault the PM's workmanship — it flags "
            "that the approval process, which requires a signature before work starts, doesn't "
            "fit how change orders actually arise on a job site. The corrective action revises "
            "the process to allow a documented verbal approval with a 24-hour paper "
            "follow-up, rather than keep failing everyone against a rule nobody follows."
        ),
        further_reading=("PMBOK-6 §8.2",),
    ),
    "design_for_x": TechniqueContent(
        summary=(
            "A family of design rules that shapes a product around one specific later concern, like safety or cost."
        ),
        when_to_use=(
            "Early in design, while changing the design is still cheap and the downstream "
            "concern (how it will be built, maintained, or paid for) is already known."
        ),
        when_to_avoid=(
            "Once the design is locked and in production — applying Design for X at that "
            "point turns a pencil edit into an expensive redesign for a benefit that no longer "
            "offsets the cost. Also avoid piling on every possible X for a low-stakes "
            "deliverable; pick the X that actually matters for that product."
        ),
        steps=(
            "Identify which downstream concern matters most for this product — examples "
            "include Design for Manufacturability, Design for Reliability, Design for "
            "Maintainability/Serviceability, Design for Cost, and Design for Safety.",
            "Bring in whoever owns that downstream concern — production, maintenance, "
            "procurement — while the design is still a draft, not after handoff.",
            "Set specific, checkable guidelines for that X, for example 'minimize unique part "
            "count' and 'standardize fastener sizes' for Design for Manufacturability.",
            "Review the design draft against the guidelines and flag violations before the "
            "design is finalized.",
            "Where two X's conflict — cheapest part versus most serviceable part — make the "
            "trade-off on purpose and write down which one won and why.",
        ),
        outputs=(
            "A design revised against explicit, named criteria.",
            "A documented record of trade-offs made between competing X's.",
        ),
        pitfalls=(
            "Treating 'Design for X' as one generic review instead of naming the specific X "
            "and its guidelines — a design reviewed against no explicit criteria isn't Design "
            "for X, it's just a review.",
            "Applying it after the design is already committed, when the fix costs a redesign "
            "instead of an edit.",
            "Optimizing one X, such as cost, while quietly degrading another, such as "
            "serviceability, without anyone deciding that trade-off on purpose.",
        ),
        worked_example=(
            "Larch & Rowe is designing a custom stair railing bracket for a repeat client. A "
            "Design for Manufacturability pass catches that the sketch specifies three "
            "different screw sizes; standardizing to one cuts fabrication time and inventory. "
            "A separate Design for Serviceability pass flags that the mounting screws would be "
            "hidden behind finished trim once installed — the design is changed to leave an "
            "access panel, because a future maintenance callback to remove trim would cost "
            "more than the panel does now."
        ),
        further_reading=("PMBOK-6 §8.2",),
    ),
    "problem_solving": TechniqueContent(
        summary=("A disciplined path from noticing something is wrong to a tested fix."),
        when_to_use=(
            "A problem whose cause or best fix isn't already known, especially one with "
            "several plausible solutions worth comparing before committing."
        ),
        when_to_avoid=(
            "A known problem with a known standard fix — running a full problem-solving "
            "process on it only slows down doing the fix. Also don't use it in place of root "
            "cause analysis when the cause itself is the unknown: problem solving assumes the "
            "problem can already be stated, root cause analysis is how you find why it's "
            "happening."
        ),
        steps=(
            "State the problem in terms everyone in the room would describe the same way, and "
            "confirm it's actually the problem — not a symptom, and not someone's preferred "
            "fix in disguise.",
            "Gather the facts and constraints that actually apply: what's fixed (budget, "
            "schedule, code) and what's flexible.",
            "Generate more than one candidate solution before evaluating any of them — "
            "pressure-testing the first idea too early kills the second, possibly better, one.",
            "Evaluate the candidates against the constraints and the problem statement, not "
            "against how politically comfortable each one is.",
            "Select a solution, and decide up front what would tell you it isn't working.",
            "Implement, then check against that signal — the process isn't done at 'we picked "
            "one,' it's done at 'we confirmed it worked.'",
        ),
        outputs=(
            "A documented decision: the problem, the options considered, the choice made, and "
            "the reasoning.",
            "An implemented fix with a defined signal for whether it worked.",
        ),
        pitfalls=(
            "Collapsing straight from 'problem' to 'solution' without stating the problem "
            "precisely, so the team solves what a stakeholder said rather than what's "
            "actually wrong.",
            "Generating only one candidate solution and calling that a decision.",
            "No defined signal for success, so a fix that didn't work isn't noticed until the "
            "problem recurs.",
        ),
        worked_example=(
            "Larch & Rowe crews keep running out of a specific fastener mid-job. The easy jump "
            "is 'order more.' Stated properly, the problem is 'the reorder point is set below "
            "what a typical job actually consumes.' Candidates considered: raise the reorder "
            "point, switch to a supplier with faster restock, or pre-kit fasteners per job. The "
            "team picks pre-kitting, since it also cuts loss on site, sets a check (zero "
            "mid-job runouts across the next five jobs), and confirms it a month later."
        ),
        further_reading=("PMBOK-6 §8.2",),
    ),
    "quality_improvement_methods": TechniqueContent(
        summary=(
            "Formal, repeatable programs that drive down defects or variation across many measured cycles over time."
        ),
        when_to_use=(
            "A recurring quality problem important enough, and stable enough in its pattern, "
            "to be worth measuring, addressing in a structured cycle, and re-measuring — "
            "chronic rework, repeat defects across projects, or a process whose output varies "
            "more than the client will tolerate."
        ),
        when_to_avoid=(
            "A single project's one-off defect — fix it and move on, that's problem solving or "
            "root cause analysis, not a program. Also avoid standing up Six Sigma-level rigor "
            "(belts, control charts, statistical process control) for a problem a one-week fix "
            "would resolve; the program overhead will exceed the problem and it will not get "
            "finished."
        ),
        steps=(
            "Pick the method that fits the problem's scale: PDCA for a lightweight, fast "
            "repeat-and-adjust cycle; DMAIC (Define-Measure-Analyze-Improve-Control) for a "
            "problem worth statistical rigor; Lean for waste or non-value-add steps in a "
            "workflow.",
            "Define the problem and measure a baseline before changing anything.",
            "Plan a specific, small change targeting the suspected driver.",
            "Run the change on a limited scope and measure the same metric again.",
            "Compare against the baseline; if it improved, standardize the change; if not, "
            "revert and try the next candidate.",
            "Repeat the cycle — these methods are iterative by design, not a single pass.",
            "Once a change sticks, document the new standard so it doesn't quietly drift "
            "back to the old way.",
        ),
        outputs=(
            "A measured before/after comparison against a defined baseline.",
            "A standardized process change, or a documented and rejected candidate.",
            "A repeatable cycle set up to run again.",
        ),
        pitfalls=(
            "Launching a full DMAIC-weight program for a problem a single fix would have "
            "resolved — the program itself becomes the overhead.",
            "Skipping the baseline measurement, so 'improvement' can't actually be shown.",
            "Treating one PDCA cycle as finished rather than as one loop in an ongoing process.",
        ),
        worked_example=(
            "Larch & Rowe sees drywall finish rework on roughly one in six jobs. Rather than a "
            "company-wide quality initiative, the ops lead runs a lightweight PDCA cycle: "
            "Plan — require a moisture check before mudding on the next ten jobs; Do — run it; "
            "Check — rework drops to one in fifteen; Act — make the moisture check standard "
            "practice on every job and retire the old sign-off sheet that didn't include it."
        ),
        further_reading=("PMBOK-6 §8.2",),
    ),
    "test_and_inspection_planning": TechniqueContent(
        summary=(
            "Deciding, while quality is still being planned, what will be checked, how, and when."
        ),
        when_to_use=(
            "Any deliverable with acceptance criteria worth verifying before handoff — "
            "essentially always, with the plan's weight scaled to the deliverable's risk."
        ),
        when_to_avoid=(
            "Building an elaborate test and inspection plan for a trivial, low-risk "
            "deliverable where a quick visual check is proportionate — the planning overhead "
            "should stay smaller than what it's protecting."
        ),
        steps=(
            "List the deliverables and, for each, the acceptance criteria it must meet.",
            "For each criterion, choose a verification method — 100% inspection, statistical "
            "sampling, functional test, or a professional/regulatory sign-off — matched to how "
            "costly a miss would be.",
            "Decide timing: inspect at the point a defect is cheapest to catch, such as before "
            "it's covered by the next trade, not only at final handoff.",
            "Assign who performs each check and who has authority to reject.",
            "Define pass/fail thresholds in writing up front, so acceptance isn't negotiated "
            "in the moment.",
            "Build the resulting checks into the schedule as real activities with duration and "
            "dependencies, not an afterthought tacked onto the end.",
        ),
        outputs=(
            "A test and inspection plan naming what gets checked, how, when, by whom, and "
            "against what threshold.",
            "Inspection points built into the project schedule.",
        ),
        pitfalls=(
            "Planning inspection only at final handoff, so a defect that could have been "
            "caught mid-process — and cheaply reworked — is instead discovered after it's "
            "buried under later work.",
            "Vague thresholds like 'looks good' decided in the moment rather than specified "
            "in advance, which turns acceptance into a negotiation.",
            "Planning tests for the deliverables that are easy to test rather than the ones "
            "that are actually risky.",
        ),
        worked_example=(
            "For a deck-building job, Larch & Rowe plans a footing-depth inspection before "
            "backfill (cheap to fix wrong now, impossible after), a racking check before "
            "decking goes down, and a final walkthrough against the client's written "
            "acceptance criteria — each with a named inspector and a documented pass "
            "threshold, built into the schedule as its own line rather than assumed to happen "
            "'at the end.'"
        ),
        further_reading=("PMBOK-6 §8.1",),
    ),
    "testing_product_evaluations": TechniqueContent(
        summary=(
            "Checking a finished product itself against its requirements, not the process that made it."
        ),
        when_to_use=(
            "Before handoff or release, whenever there's a deliverable with defined "
            "requirements and the cost of a defect reaching the client exceeds the cost of "
            "testing it first."
        ),
        when_to_avoid=(
            "As a substitute for process control on a high-volume repeat product — testing "
            "every unit after the fact is expensive insurance for problems a controlled "
            "process would have prevented earlier. Testing finds defects; it doesn't prevent "
            "them, so don't rely on it alone when the underlying process is known to be "
            "unstable."
        ),
        steps=(
            "Pull the requirement or acceptance criterion for the product under test, from "
            "test and inspection planning if that step already happened.",
            "Choose the evaluation method that actually verifies the criterion — functional "
            "test, dimensional check, load test, visual inspection, or a client walkthrough.",
            "Run the test under conditions representative of real use, not just ideal conditions.",
            "Record the actual result against the target, not just pass/fail — the margin "
            "matters for the next product.",
            "On a fail, route it back to the deliverable's owner with the specific criterion "
            "missed, not a general 'didn't pass.'",
            "On a pass, record the evaluation as part of the deliverable's acceptance record.",
        ),
        outputs=(
            "A documented pass/fail result per criterion, with actual values recorded.",
            "An acceptance record for the deliverable.",
        ),
        pitfalls=(
            "Confusing this with an audit: a passed product evaluation says nothing about "
            "whether the process that built the product was followed, and a clean audit says "
            "nothing about whether this particular unit meets spec — they answer different "
            "questions and neither substitutes for the other.",
            "Testing under ideal conditions that don't represent the client's actual use.",
            "Recording only pass/fail and losing the margin, so a product drifting toward the "
            "threshold isn't noticed until it fails outright.",
        ),
        worked_example=(
            "Larch & Rowe pours a set of custom concrete countertops. The testing/product "
            "evaluation is the 28-day compressive strength test on cured sample cylinders "
            "against the specified PSI — a check on this specific pour's product. It's "
            "separate from, and doesn't replace, an audit of whether the crew followed the "
            "documented curing and mixing procedure; the two would catch different failures "
            "if the strength test came back low."
        ),
        further_reading=("PMBOK-6 §8.3",),
    ),
}
