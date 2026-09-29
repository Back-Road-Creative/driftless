"""Technique explanations for the cost family (tt.FAMILIES["cost"]).

``earned_value_analysis`` and ``to_complete_performance_index`` describe
numbers driftless actually computes today, in ``driftless.calc.evm``: BAC,
PV, EV, AC, CPI, SPI, EAC and VAC come out of ``earned_value_snapshot``, EAC
is the single formula ``BAC / CPI``, and ETC is derived as ``EAC - AC``. CV,
SV, the percent-variance forms, and TCPI are not computed anywhere in the
codebase; the entries below say so rather than describing a capability the
reader cannot actually reach here.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "cost"

CONTENT: dict[str, TechniqueContent] = {
    "cost_aggregation": TechniqueContent(
        summary=(
            "Adding up cost estimates from the smallest tasks up through the whole project into one traceable budget."
        ),
        when_to_use=(
            "Whenever you need a cost baseline that survives being questioned: every "
            "figure at every level should be recoverable by adding the level below it. "
            "Do it once the WBS is stable enough that work packages won't keep moving "
            "between control accounts."
        ),
        when_to_avoid=(
            "Don't re-aggregate from scratch every time one estimate changes — that's "
            "how a spreadsheet turns into an hour of clicking. If the WBS itself is "
            "still churning, aggregate loosely and re-baseline later rather than "
            "chasing a moving structure to the penny."
        ),
        steps=(
            "Confirm every work package has exactly one owning control account; a "
            "package counted in two accounts double-books the budget.",
            "Sum work package estimates up to each control account.",
            "Sum control accounts up to the project total (BAC).",
            "Add contingency reserve at the account or project level, not inside "
            "individual work package estimates, so it stays visible as reserve.",
            "Publish the rolled-up total as the cost baseline and record the date it was approved.",
        ),
        outputs=(
            "A cost baseline: one total, traceable down to every work package that makes it up.",
            "A control-account-by-control-account breakdown usable for later variance reporting.",
        ),
        pitfalls=(
            "A work package attached to two control accounts, silently doubling its "
            "cost in the rollup.",
            "Contingency buried inside individual estimates instead of held visibly "
            "at the account level, so nobody can later tell how much cushion is left.",
            "Aggregating before the WBS is stable, then re-aggregating every time a "
            "package moves, instead of waiting for a natural re-baseline point.",
        ),
        worked_example=(
            "A tenant-improvement build-out has three control accounts: Demolition, "
            "MEP rough-in, and Finishes. Demolition sums four work packages to "
            "$38,000; MEP rough-in sums seven to $164,500; Finishes sums nine to "
            "$97,200. The project total, before reserve, is $299,700. The team adds "
            "$18,000 of contingency reserve at the project level, giving a BAC of "
            "$317,700 that a stakeholder can trace back to any of the twenty work "
            "packages underneath it."
        ),
        further_reading=("PMBOK-6 §7.3.2.2",),
    ),
    "cost_of_quality": TechniqueContent(
        summary=(
            "Sorting quality spending into four buckets, to see if a project pays to prevent defects or fix them."
        ),
        when_to_use=(
            "When you're deciding how much to invest in preventing and catching "
            "defects, or when rework and warranty costs are climbing and you want to "
            "know whether more prevention spend would actually pay for itself. Also "
            "useful whenever quality-related costs need to be visible as a category, "
            "not buried inside general cost overruns."
        ),
        when_to_avoid=(
            "Don't build the four-bucket breakdown on a project too small or too "
            "short to have a meaningful quality cost signal — the categorization "
            "overhead will exceed anything it reveals. And don't treat a low failure "
            "cost as proof prevention spend is working; it might just mean nobody has "
            "found the defects yet."
        ),
        steps=(
            "Define the four categories for this project in concrete terms: what "
            "counts as prevention, appraisal, internal failure, external failure.",
            "Tag cost entries into one of the four categories as they're incurred, "
            "not retroactively from memory.",
            "Total each category on a recurring cadence (e.g. monthly).",
            "Compare prevention plus appraisal (cost of conformance) against internal "
            "plus external failure (cost of nonconformance).",
            "Where failure cost dominates, identify which failure category is driving "
            "it and evaluate whether targeted prevention or appraisal spend would "
            "reduce it.",
        ),
        outputs=(
            "A running total for each of the four cost-of-quality categories.",
            "A conformance-versus-nonconformance comparison that argues for or "
            "against more upfront quality investment.",
        ),
        pitfalls=(
            "Miscategorizing rework as a normal project cost instead of an internal "
            "failure cost, which hides the real signal.",
            "Only counting external failure costs that show up as an invoice (a "
            "warranty claim) and missing the ones that show up as reputation or lost "
            "repeat business.",
            "Treating a shrinking failure-cost total as success without checking "
            "whether defects are actually down or just being found later, off this "
            "project's books.",
        ),
        worked_example=(
            "A software team building a billing module tracks $12,000 in prevention "
            "(design reviews, static analysis setup), $9,000 in appraisal (QA testing "
            "cycles), $31,000 in internal failure (bugs caught and fixed before "
            "release), and $4,000 in external failure so far (a production billing "
            "error refunded to two customers). With failure costs at $35,000 against "
            "$21,000 of conformance spend, the team adds a second design review pass "
            "for the next module rather than continuing to absorb the rework."
        ),
        further_reading=("PMBOK-6 §8.1.2.3",),
    ),
    "earned_value_analysis": TechniqueContent(
        summary=(
            "Comparing planned, completed, and spent work at one point in time to judge cost and schedule performance."
        ),
        when_to_use=(
            "Any time you have a baselined cost and schedule and need a defensible "
            "answer to 'are we in trouble' that isn't just a gut feeling. It earns "
            "its keep most on projects long enough, and with enough spend, that a "
            "manager can't just eyeball progress against the budget."
        ),
        when_to_avoid=(
            "Don't run it against a baseline nobody actually approved, or against "
            "progress percentages nobody actually measured — a fabricated percent "
            "complete produces a CPI that looks precise and means nothing. And a "
            "single EAC formula (see below) is the wrong call on a project whose cost "
            "performance is actively recovering or deteriorating, not holding steady."
        ),
        steps=(
            "Establish BAC: the approved, aggregated cost baseline.",
            "For the as-of date, get PV — how much of the baseline should have "
            "accrued by now — from the baseline's planned windows.",
            "Get EV — percent complete per task, times that task's planned cost, "
            "summed — from the latest progress reports at or before the as-of date.",
            "Get AC — the money actually incurred at or before the as-of date.",
            "Compute CPI = EV / AC and SPI = EV / PV. Both are undefined (not zero) "
            "before there is spend or planned accrual to divide by.",
            "Read CPI and SPI together before reaching for a single-number verdict: "
            "a CPI below 1.0 means less value earned per dollar spent than planned; "
            "an SPI below 1.0 means less value earned per dollar of baseline that "
            "should have accrued by now.",
            "If you need a forecast, compute EAC from CPI and treat it as one "
            "scenario, not a fact — see the caveat below.",
        ),
        outputs=(
            "A single as-of snapshot: BAC, PV, EV, AC, CPI, SPI, EAC, ETC, VAC.",
            "A cost-performance read (via CPI) and a schedule-performance read (via "
            "SPI) that can be tracked over successive as-of dates to see a trend, not "
            "just a point.",
        ),
        pitfalls=(
            "Reading SPI as literal schedule days late or early — it's a value "
            "ratio, not a calendar figure, and can mislead badly near a project's "
            "end when there's little baseline left to under- or over-run.",
            "Treating a CPI of exactly 1.0 as 'fine' without checking whether it's "
            "an average masking a task that's badly over cost offset by one that's "
            "badly under-scoped.",
            "This product computes EAC one way — ``BAC / CPI`` — which assumes the "
            "cost performance seen so far will continue for the rest of the project. "
            "That's the assumption most likely to be wrong on a project recovering "
            "from a bad patch or sliding into one; read the resulting EAC as 'if "
            "nothing changes', not as the number you'll actually land on.",
            "Chasing CPI back to exactly 1.0 by re-baselining away real overruns "
            "instead of reporting them — a CPI that only ever improves because the "
            "baseline keeps moving isn't performance, it's bookkeeping.",
        ),
        worked_example=(
            "A community-center renovation has a BAC of $850,000. At the six-month "
            "as-of date, the baseline says $410,000 should have accrued (PV). "
            "Progress reports put earned value (EV) at $348,500, against $410,000 "
            "actually spent (AC) so far. CPI = 348,500 / 410,000 = 0.85 — the "
            "project is getting 85 cents of planned work for every dollar spent. "
            "SPI = 348,500 / 410,000 = 0.85 too, coincidentally the same figure here, "
            "meaning progress is also running behind the baseline's pace. The "
            "resulting EAC (BAC / CPI = 850,000 / 0.85 ≈ $1,000,000) says the job "
            "will cost roughly $150,000 more than planned if the last six months' "
            "cost performance holds — the project manager reports that as a "
            "conditional forecast, not a promise, and starts investigating which "
            "trade's overruns are driving the 0.85."
        ),
        further_reading=("PMBOK-6 §7.4.2.2",),
    ),
    "financing": TechniqueContent(
        summary=(
            "Arranging outside funding to cover project costs the owner's own cash cannot carry."
        ),
        when_to_use=(
            "When project spend will outpace the funding organization's on-hand "
            "cash at some point in the timeline, and that gap needs to be closed "
            "with borrowed or invested money arranged ahead of time, not discovered "
            "mid-project."
        ),
        when_to_avoid=(
            "Don't treat financing as a project-management technique when it's "
            "really a corporate finance decision above the project manager's "
            "authority — arranging it is often someone else's job, but the project "
            "manager still needs to know the terms and timing well enough to plan "
            "spend around them. Reaching for external financing to paper over a "
            "budget that was underestimated, rather than a genuine cash-timing gap, "
            "just moves the problem and adds interest to it."
        ),
        steps=(
            "Compare the project's planned spend curve against the funding "
            "organization's available cash curve to find where and how large the "
            "gap is.",
            "Identify financing sources appropriate to the gap's size and duration "
            "(short-term credit line versus long-term loan versus investor capital).",
            "Confirm the terms: interest or return expectations, repayment schedule, "
            "any covenants that constrain how project funds are drawn or spent.",
            "Time the financing's availability against the project's spend curve so "
            "money is in hand before it's needed, not after.",
            "Feed the cost of financing (interest, fees) back into the project's "
            "budget as a real project cost.",
        ),
        outputs=(
            "A financing arrangement with a known draw schedule, cost, and any "
            "constraints on project spend.",
            "A funded spend curve the project can actually execute against without a cash gap.",
        ),
        pitfalls=(
            "Treating financing costs (interest, fees) as outside the project "
            "budget instead of as real project cost, understating the true BAC.",
            "Financing terms (covenants, draw conditions) that constrain how or "
            "when money can be spent, discovered mid-project instead of during "
            "planning.",
            "Using financing to cover a shortfall caused by underestimation rather "
            "than genuine cash-flow timing, deferring a scope or budget "
            "conversation the project actually needs.",
        ),
        worked_example=(
            "A developer's mixed-use building has a $4.2 million construction "
            "budget but the owner's cash on hand covers only the first $1.5 million "
            "of spend before lease revenue and equity draws catch up in month nine. "
            "The project arranges a construction loan for the $2.7 million gap, "
            "drawn in scheduled tranches tied to completed phases, at a rate that "
            "adds roughly $95,000 in interest over the build. That $95,000 is added "
            "to the project's cost baseline rather than treated as a separate "
            "corporate expense."
        ),
        further_reading=(),
    ),
    "funding_limit_reconciliation": TechniqueContent(
        summary=(
            "Reshaping planned spending so it never asks for more money than is actually available each period."
        ),
        when_to_use=(
            "Whenever the funding organization releases money on a schedule — "
            "annual appropriations, quarterly capital releases, tranche-based "
            "investor draws — that doesn't automatically match the project's "
            "natural spend curve. Check it as soon as a period-by-period funding "
            "schedule exists, not after a period's spend has already been planned "
            "past its limit."
        ),
        when_to_avoid=(
            "Don't reconcile against funding limits that are still provisional or "
            "under negotiation — smoothing the schedule against a number that "
            "later changes wastes the exercise. And don't treat this as purely a "
            "cost problem: reshaping planned spend to fit a funding limit almost "
            "always reshapes the schedule too, since the work that generates that "
            "spend has to move with it."
        ),
        steps=(
            "Lay the planned spend curve (from the cost baseline) against the "
            "funding limits published for each period.",
            "Find every period where planned spend exceeds the available funding.",
            "Resequence or delay the work driving the excess into a period with "
            "headroom, rather than assuming the limit will flex.",
            "Re-check the schedule for any downstream effect the resequencing "
            "causes — a delayed activity can push dependents past their own dates.",
            "Republish the reconciled spend curve as the version the project will "
            "actually execute against.",
        ),
        outputs=(
            "A spend curve where planned cost in every period sits at or below "
            "that period's funding limit.",
            "A documented list of activities moved to fit funding, and the "
            "schedule impact each move caused.",
        ),
        pitfalls=(
            "Moving work to fit the funding limit without re-checking the schedule "
            "network — the delayed activity's dependents slip too, and that "
            "schedule impact goes unreported until it surfaces on its own.",
            "Treating the reconciled curve as a one-time fix instead of rechecking "
            "it every time funding limits or the spend forecast change.",
            "Smoothing spend into future periods so consistently that later "
            "periods quietly become overloaded, just moving the mismatch instead "
            "of resolving it.",
        ),
        worked_example=(
            "A public infrastructure project's total budget is fully approved at "
            "$6 million, but the funding authority releases it in three annual "
            "tranches of $2 million each. The baseline schedule, driven by "
            "construction sequencing, calls for $2.6 million of spend in year one. "
            "Reconciliation pushes $600,000 of year-one paving work (which had "
            "slack) into year two, bringing year one to $2.0 million exactly — but "
            "the paving activity's downstream dependent, landscaping, now can't "
            "start until three months later than originally planned, which the "
            "team flags and re-baselines the schedule to reflect."
        ),
        further_reading=(),
    ),
    "historical_information_review": TechniqueContent(
        summary=(
            "Pulling actual cost, schedule, and estimating data from comparable "
            "past projects to sanity-check or ground a current estimate, instead of "
            "estimating from a blank page."
        ),
        when_to_use=(
            "At the start of estimating, when comparable past-project data exists "
            "and is trustworthy enough to compare against — most useful for an "
            "organization that has done similar work before and kept its actuals."
        ),
        when_to_avoid=(
            "Don't lean on historical data from a project that isn't actually "
            "comparable in scope, market conditions, or team, just because it's the "
            "data on hand — a plausible-looking number from the wrong reference "
            "project is worse than an honest estimate built from scratch. And don't "
            "use it as the sole basis for an estimate when the current project has "
            "no genuine precedent."
        ),
        steps=(
            "Identify past projects genuinely comparable in scope, scale, and "
            "conditions — not just the same general category of work.",
            "Pull their actual costs, durations, and any documented estimate-versus"
            "-actual variance, not just their original estimates.",
            "Adjust for known differences: inflation, site conditions, team "
            "experience, scope delta between the past project and this one.",
            "Use the adjusted figures to check the current estimate, not to replace "
            "the estimating process entirely.",
            "Record which historical projects were used and what adjustments were "
            "made, so the reasoning is auditable later.",
        ),
        outputs=(
            "A sanity-checked or adjusted estimate, with its historical basis and "
            "adjustments documented.",
            "A short list of comparable past projects usable again for future estimates.",
        ),
        pitfalls=(
            "Using a past project as a reference because its data is convenient to "
            "find, not because it's actually comparable.",
            "Carrying forward a past project's own estimating error because only "
            "its original estimate was reviewed, not its actual outcome.",
            "Skipping the adjustment step and applying historical figures "
            "unchanged to a project with materially different conditions.",
        ),
        worked_example=(
            "A contractor estimating a 40-unit apartment renovation pulls actuals "
            "from a comparable 36-unit renovation completed eighteen months earlier: "
            "$1.42 million actual against a $1.30 million original estimate, a 9% "
            "overrun traced mostly to unforeseen electrical work. Scaling for unit "
            "count and adjusting for a documented 4% material cost increase since "
            "then, the estimator lands on $1.68 million for the new project and adds "
            "explicit electrical contingency, rather than repeating the prior "
            "project's underestimate."
        ),
        further_reading=("PMBOK-6 §7.3.2.4",),
    ),
    "reserve_analysis": TechniqueContent(
        summary=(
            "Setting aside one budget cushion inside the cost baseline for known risks, and "
            "another outside the baseline for the unknown."
        ),
        when_to_use=(
            "During cost baselining, using the project's risk register to size "
            "contingency reserve against identified risks, and using organizational "
            "policy or judgment about overall project uncertainty to size management "
            "reserve. Revisit both any time the risk register or the project's "
            "uncertainty picture changes materially."
        ),
        when_to_avoid=(
            "Don't collapse the two reserves into one undifferentiated cushion — "
            "that's the single most common way this technique gets misapplied, and "
            "it destroys the thing that makes reserve analysis useful: knowing "
            "which reserve an overrun should draw from and being able to report "
            "that draw-down honestly instead of quietly absorbing it into the "
            "baseline."
        ),
        steps=(
            "Walk the risk register and estimate a cost impact and probability for "
            "each identified cost risk.",
            "Size contingency reserve from that impact-and-probability analysis "
            "(e.g. expected monetary value, or a simulation) and add it inside the "
            "cost baseline, kept visible as its own line rather than folded into "
            "work package estimates.",
            "Size management reserve separately, as a percentage or judgment call "
            "against overall project uncertainty, and hold it outside the baseline "
            "and outside the project manager's unilateral authority to spend.",
            "When a risk in the register materializes and its cost impact is "
            "realized, draw against contingency reserve and report the draw-down "
            "explicitly — don't just let the actual absorb it silently.",
            "When an unforeseen cost outside the risk register hits, escalate a "
            "management reserve request through whatever authority controls it, "
            "rather than treating it as routine.",
        ),
        outputs=(
            "A contingency reserve figure, inside the baseline, tied to specific identified risks.",
            "A management reserve figure, outside the baseline, for the unknown.",
            "A running record of what's been drawn from each reserve and why.",
        ),
        pitfalls=(
            "Merging contingency and management reserve into one number, so an "
            "overrun's source — an identified risk that materialized versus a "
            "genuine surprise — can't be told apart later.",
            "Drawing down contingency reserve without reporting it, so the reserve "
            "looks intact right up until a status report shows it's gone.",
            "Sizing contingency reserve as an arbitrary percentage of the estimate "
            "instead of from the actual risk register, so it bears no relationship "
            "to what the project's real risk exposure is.",
            "Treating management reserve as routinely accessible to the project "
            "manager rather than as a genuinely separate authority to draw against.",
        ),
        worked_example=(
            "A data-center fit-out has a $2.1 million baseline before reserve. The "
            "risk register identifies a $60,000 cost impact if a specific HVAC "
            "vendor's lead time slips (35% probability) and a $25,000 impact if a "
            "permitting delay pushes work into a higher-cost season (20% "
            "probability); expected monetary value sizes contingency reserve at "
            "$26,000, added inside the baseline for a BAC of $2.126 million. "
            "Separately, the organization holds a 5% management reserve — "
            "$106,300 — outside the baseline for genuine unknowns. When the HVAC "
            "vendor's lead time does slip and the cost impact lands at $58,000, the "
            "project draws it from contingency and reports the reserve as $32,000 "
            "of the original $60,000 risk-linked amount still remaining, rather than "
            "letting the actual cost simply rise unremarked."
        ),
        further_reading=(),
    ),
    "to_complete_performance_index": TechniqueContent(
        summary=("The cost efficiency remaining work must hit to land on a realistic target cost."),
        when_to_use=(
            "Any time CPI is off 1.0 and someone's asking whether the project can "
            "still hit its original budget. Use TCPI against BAC — (BAC − EV) / "
            "(BAC − AC) — to answer 'can we still make the original number', and "
            "TCPI against a revised EAC — (BAC − EV) / (EAC − AC) — to check whether "
            "even that revised, more forgiving forecast is achievable at the "
            "efficiency the team has actually been running at."
        ),
        when_to_avoid=(
            "Don't present a TCPI-against-BAC figure as a plan without comparing it "
            "against the CPI the project has actually been achieving — a TCPI far "
            "above current CPI isn't a target, it's a number nobody has a "
            "believable way to hit, and presenting it as achievable is arithmetic "
            "fiction dressed up as a forecast."
        ),
        steps=(
            "Get current EV, AC, and BAC (or a revised EAC, if one exists and is trusted).",
            "Decide which denominator answers the question being asked: BAC if the "
            "question is 'can the original budget still be hit', EAC if the "
            "question is 'is even the revised forecast realistic'.",
            "Compute TCPI = (BAC − EV) / (BAC − AC), or (BAC − EV) / (EAC − AC) for the EAC form.",
            "Compare the result against the CPI the project has actually achieved to date.",
            "If TCPI sits well above achieved CPI, treat that gap as the finding — "
            "it means the remaining work needs to run meaningfully more efficiently "
            "than the work already done, and say so explicitly rather than "
            "presenting the target alone.",
        ),
        outputs=(
            "A required-efficiency figure (TCPI) for the remaining work, against "
            "either BAC or a revised EAC.",
            "An explicit comparison of that required efficiency against what the "
            "project has actually been achieving.",
        ),
        pitfalls=(
            "Reporting TCPI against BAC without ever computing or checking it "
            "against achieved CPI — the gap between the two is the entire point.",
            "Continuing to use the BAC form after everyone has effectively accepted "
            "a revised EAC, so the TCPI reported no longer answers a question "
            "anyone is actually asking.",
            "Treating a TCPI just modestly above current CPI as fine, without "
            "asking what specifically will change about how the remaining work is "
            "run to close even a small gap.",
        ),
        worked_example=(
            "On the same community-center renovation (BAC $850,000, EV $348,500, "
            "AC $410,000, CPI 0.85), TCPI against BAC is (850,000 − 348,500) / "
            "(850,000 − 410,000) = 501,500 / 440,000 ≈ 1.14 — the remaining work "
            "would need to run at 1.14 efficiency, well above the 0.85 the project "
            "has actually delivered so far, to still hit the original $850,000. "
            "Against the earlier EAC of $1,000,000 instead, TCPI = (850,000 − "
            "348,500) / (1,000,000 − 410,000) = 501,500 / 590,000 ≈ 0.85 — exactly "
            "the efficiency already being achieved, meaning the revised forecast is "
            "the believable one and the original budget, at this point, is not."
        ),
        further_reading=("PMBOK-6 §7.4.2.2",),
    ),
}
