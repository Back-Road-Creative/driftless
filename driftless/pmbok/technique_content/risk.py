"""Technique explanations for the risk family (tt.FAMILIES["risk"]).

A note on scope, because this family is the one most tempted to overclaim:
Driftless's ``Risk`` record (``driftless.models.records.Risk``) stores a
description, a probability (0-1), an impact, a response drawn from
``RISK_RESPONSES``, an owner and a status, and derives exposure as
``probability * impact``. There is no risk category or breakdown structure, no
configurable probability-impact matrix, and no stored distributions. Several
entries below describe techniques whose output has nowhere to land in the
product yet, and say so rather than imply otherwise. Likewise, the only Monte
Carlo in this codebase (in ``driftless.calc.forecast``) is a bootstrap over
sprint velocity for schedule forecasting; it is not a risk simulation and
nothing here runs one.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "risk"

CONTENT: dict[str, TechniqueContent] = {
    "risk_categorization": TechniqueContent(
        summary=(
            "Grouping identified risks by source or area so patterns become visible instead of staying a flat list."
        ),
        when_to_use=(
            "Once the register has enough entries that scrolling through it no longer "
            "shows you anything: a dozen or more risks, or a project with several distinct "
            "workstreams. Categorizing surfaces concentration you would otherwise miss, "
            "such as half your open risks tracing back to one vendor or one unproven "
            "technology choice."
        ),
        when_to_avoid=(
            "On a short list of risks a person can hold in their head at once — the "
            "categories add bookkeeping without adding insight. Also avoid inventing a "
            "deep, formal risk breakdown structure before you have enough risks to "
            "populate more than a couple of its branches; an elaborate taxonomy with three "
            "risks in it is effort spent on the wrong thing."
        ),
        steps=(
            "List every open risk currently in the register.",
            "Pick a small set of categories that matches how your team actually thinks "
            "about the project — by source (technical, external, organizational, "
            "project management) or by affected area (a specific workstream, vendor, or "
            "deliverable).",
            "Tag each risk with one primary category; note a second if it genuinely spans two.",
            "Count and total exposure by category.",
            "Look for concentration: one category carrying most of the exposure, or "
            "most of the count, is the signal you were looking for.",
            "Feed that concentration back into planning — a shared root cause across "
            "several risks is often cheaper to address once than risk by risk.",
        ),
        outputs=(
            "Risks grouped into a small number of named categories.",
            "A per-category count and exposure total.",
            "A short written note on where the concentration is and why it matters.",
        ),
        pitfalls=(
            "Choosing categories that sound thorough (a full PMBOK-style RBS) but that "
            "the team never actually uses when a new risk shows up, so tagging drifts to "
            "'other' and the structure stops meaning anything.",
            "Treating the category count as the finding instead of using it to ask why "
            "one category dominates.",
            "Recreating this by hand every time instead of noticing Driftless has no "
            "category field on the risk record — there is nowhere to store the tag "
            "itself yet, so this stays a spreadsheet or notebook exercise layered on top "
            "of the register, not something the tool tracks for you.",
        ),
        worked_example=(
            "A mid-size warehouse automation project has nineteen open risks. Sorted by "
            "source, eight trace back to the conveyor vendor's late deliveries, three to "
            "unfamiliar sensor firmware, and the rest are scattered. The PM stops treating "
            "the eight vendor risks as independent items and instead escalates one "
            "conversation with the vendor's account manager about their delivery "
            "schedule — addressing the root cause instead of eight symptoms."
        ),
        further_reading=("PMBOK-6 §11.3.2.5",),
    ),
    "risk_probability_and_impact_assessment": TechniqueContent(
        summary=(
            "Rating each risk's likelihood and effect on agreed scales so risks can be fairly compared."
        ),
        when_to_use=(
            "For every risk entering the register, as a standard step right after it's "
            "identified — you need probability and impact figures before you can compute "
            "exposure or decide what deserves a response plan."
        ),
        when_to_avoid=(
            "Don't build an elaborate 5x5 probability-impact matrix for a project where "
            "three people already agree, informally and correctly, on what matters most. "
            "The matrix earns its keep on a project big enough, or political enough, that "
            "'high' and 'low' mean different things to different people until you write "
            "the scale down."
        ),
        steps=(
            "Before scoring any risk, define what each probability band means in "
            "concrete terms — 'low' might be 'has not happened on the last three similar "
            "projects,' not just a number between 0 and 1.",
            "Define each impact level the same way, in terms your organization can "
            "actually judge: schedule days, cost, or a scope/quality description — "
            "not just 'severe' or 'minor.'",
            "Score each risk's probability against the defined bands, not against your "
            "impression of the risk overall.",
            "Score impact the same way, independently of the probability score.",
            "Record both numbers on the risk (Driftless stores probability as 0-1 and "
            "impact as a number; exposure is derived automatically as their product).",
            "Revisit scores when new information arrives — a probability assessed at "
            "project start is a snapshot, not a fact.",
        ),
        outputs=(
            "A probability and an impact value on every scored risk.",
            "A derived exposure figure per risk, usable to rank and compare.",
            "Written scale definitions the next risk gets scored against consistently.",
        ),
        pitfalls=(
            "Multiplying two ordinal ratings (a 1-5 'how likely' and a 1-5 'how bad') and "
            "presenting the product as if it were a real number. Ordinal scales aren't "
            "arithmetic — a 4 isn't twice a 2 — so a computed '16' out of a 5x5 grid looks "
            "precise and isn't; it only orders risks correctly if the scale steps happen "
            "to be roughly even, which nobody checks.",
            "Skipping the step of writing down what each band means, so two people "
            "scoring the same risk land on different numbers and neither is wrong by the "
            "(nonexistent) definition.",
            "Letting probability scores creep toward whatever makes exposure look "
            "acceptable, especially near a status report deadline.",
            "Treating impact as cost alone when a risk's real consequence is schedule "
            "slip, reputational damage, or scope compromise that doesn't fit a dollar "
            "figure.",
        ),
        worked_example=(
            "A hospital records-migration project defines probability bands up front: "
            "low = 'no precedent in our last four migrations,' medium = 'happened once,' "
            "high = 'happened on more than one.' Two different leads independently score "
            "the risk 'legacy export tool corrupts date fields' as medium probability "
            "because it happened once, on a similar system, eighteen months ago — because "
            "the band was written down, they agree without a meeting."
        ),
        further_reading=("PMBOK-6 §11.3.2.3",),
    ),
    "representations_of_uncertainty": TechniqueContent(
        summary=(
            "Describing an uncertain amount as a range instead of one falsely precise number."
        ),
        when_to_use=(
            "Whenever a single-point estimate for cost, duration, or probability is being "
            "presented as if it were exact, and it isn't — which is most estimates. Useful "
            "input wherever a technique downstream (sensitivity analysis, decision tree "
            "analysis) needs a range rather than a point to work with."
        ),
        when_to_avoid=(
            "When the extra precision of a full distribution (shape, spread, tails) buys "
            "nothing over a plain three-point range, because nobody downstream is going to "
            "do anything with the difference. Also avoid dressing up a genuine guess in "
            "distribution language — a triangular distribution built from three numbers "
            "someone made up in a meeting is still three numbers someone made up in a "
            "meeting."
        ),
        steps=(
            "For the quantity in question, gather optimistic, most likely, and "
            "pessimistic estimates from whoever is closest to the work.",
            "Choose a shape that matches how the uncertainty actually behaves — "
            "triangular for a simple three-point estimate, a wider or skewed shape if "
            "you have reason to think bad outcomes are more likely than good ones by a "
            "large margin.",
            "Write the range and shape down next to the estimate, not just the single "
            "number that would otherwise get quoted in a status report.",
            "Use the range as the actual input wherever the estimate feeds a decision — "
            "don't collapse it back to a midpoint the moment it leaves the estimator's "
            "hands.",
        ),
        outputs=(
            "An optimistic/most-likely/pessimistic range (or a described distribution "
            "shape) for the quantity, instead of one number.",
            "A record of who supplied the estimate and on what basis, so it can be revisited.",
        ),
        pitfalls=(
            "Reporting the range once, then reverting to quoting only the most-likely "
            "figure everywhere else because it's simpler to write down.",
            "Confusing a wide range with a careful one — width should reflect genuine "
            "uncertainty, not a padding reflex applied to look cautious.",
            "Building a distribution nobody actually samples from. Driftless has no field "
            "for a distribution on a risk or estimate today; if you need this to feed an "
            "actual simulation, that simulation has to happen outside the tool — the only "
            "Monte Carlo Driftless runs is a schedule forecast over past sprint velocity, "
            "unrelated to any risk range you define here.",
        ),
        worked_example=(
            "An engineering team estimating a custom sensor housing gives one number, "
            "'6 weeks,' in the first plan. Pushed for a range, the lead engineer gives "
            "4 weeks optimistic (parts arrive on time, first print works), 6 most "
            "likely, and 11 pessimistic (a redesign is needed after the first fit test). "
            "The 11-week tail, not the 6-week midpoint, is what changes the delivery "
            "commitment the PM makes to the client."
        ),
        further_reading=("PMBOK-6 §11.4.2.4",),
    ),
    "strategies_for_threats": TechniqueContent(
        summary=(
            "Choosing a deliberate response to a risk that would hurt the project if it happened."
        ),
        when_to_use=(
            "For every threat (a risk with a negative effect on the project) once it's "
            "scored highly enough to warrant a response beyond just watching it. This is "
            "the mirror image of strategies for opportunities, below — same decision "
            "structure, aimed at downside instead of upside."
        ),
        when_to_avoid=(
            "Don't force a formal strategy choice onto a risk so low in exposure that "
            "'accept, revisit later' is obviously correct and would only be dressed up by "
            "a longer discussion. Also don't default every threat to 'mitigate' without "
            "considering avoid or transfer — mitigate is the comfortable middle choice and "
            "it's easy to reach for out of habit rather than fit."
        ),
        steps=(
            "For the threat, ask whether the triggering activity can be eliminated "
            "entirely — that's avoid, and it's the strongest response when it's on the "
            "table.",
            "If it can't be eliminated, ask whether its probability or impact can be "
            "reduced — that's mitigate, the most common response and the one Driftless "
            "defaults a new risk to.",
            "Ask whether the consequence can be shifted to someone better placed to bear "
            "it — insurance, a contract clause, a fixed-price subcontract — that's "
            "transfer.",
            "If none of the above is worth its cost relative to the exposure, choose "
            "accept, and decide whether that's passive (do nothing, absorb it if it "
            "happens) or active (set aside contingency, define a fallback).",
            "Record the chosen response and the owner responsible for carrying it out.",
        ),
        outputs=(
            "One response strategy recorded per threat (matches the four "
            "``RISK_RESPONSES`` values Driftless stores: avoid, mitigate, transfer, "
            "accept).",
            "An owner assigned to carry the response out.",
            "For an actively accepted threat, a contingency reserve or fallback plan — "
            "which is where contingent response strategies pick up.",
        ),
        pitfalls=(
            "Choosing 'mitigate' reflexively because it feels like the responsible middle "
            "ground, when avoid or transfer would remove the exposure entirely for "
            "similar cost.",
            "Recording 'accept' without distinguishing passive from active acceptance, so "
            "a risk everyone assumed had a contingency plan turns out to have none.",
            "Picking a strategy once at register creation and never revisiting it as the "
            "risk's probability or impact changes over the project.",
        ),
        worked_example=(
            "A single-source component supplier is the sole vendor for a custom "
            "connector on a robotics build. The PM can't avoid the dependency (no second "
            "supplier exists) but negotiates a penalty clause for late delivery "
            "(transfer) and, separately, qualifies a slower backup part that could "
            "substitute if the primary slips more than three weeks (an active-acceptance "
            "fallback)."
        ),
        further_reading=("PMBOK-6 §11.5.2.4",),
    ),
    "strategies_for_opportunities": TechniqueContent(
        summary=(
            "Choosing a deliberate response to a risk that would help the project if it happened."
        ),
        when_to_use=(
            "For any identified risk with a positive effect: a chance to finish early, "
            "spend less, or exceed a requirement. Use it in the same pass as threat "
            "response planning, not as an afterthought — a risk register that only ever "
            "lists things that could go wrong is only doing half the job."
        ),
        when_to_avoid=(
            "This is the strategy set most teams skip entirely, not because it's wrong "
            "for their project but because nobody asked the question. If you genuinely "
            "have no upside risks — every identified risk in the register is a pure "
            "threat — don't force one in to look complete. But check that assumption "
            "before accepting it; opportunities are systematically under-reported "
            "because 'this might go well' doesn't feel urgent enough to write down."
        ),
        steps=(
            "For the opportunity, ask whether you can make the favorable outcome "
            "certain — that's exploit, the upside mirror of avoid, and the strongest "
            "response when you can pull it off (e.g., assigning your best resource to "
            "guarantee an early finish rather than hoping for one).",
            "If it can't be made certain, ask whether its probability or positive impact "
            "can be increased — that's enhance, the mirror of mitigate.",
            "Ask whether a third party is better placed to capture the upside and "
            "share the benefit — that's share, the mirror of transfer (a teaming "
            "arrangement or joint venture is the classic form).",
            "If none of the above is worth pursuing actively, accept — take the upside "
            "if it happens, without spending effort chasing it.",
            "Record the chosen strategy and the owner responsible for pursuing it, the "
            "same way a threat response is recorded.",
        ),
        outputs=(
            "One response strategy recorded per opportunity — Driftless has no separate "
            "opportunity-response vocabulary; the four ``RISK_RESPONSES`` values (avoid, "
            "mitigate, transfer, accept) are threat-shaped and don't literally spell "
            "exploit/enhance/share/accept, so record the opportunity strategy in the "
            "risk's description or notes rather than expecting a dedicated field.",
            "An owner assigned to pursue the opportunity.",
        ),
        pitfalls=(
            "Never identifying opportunities in the first place — the single most common "
            "failure mode for this technique, and the reason it's worth a deliberate "
            "prompt during identification rather than assuming they'll surface on their "
            "own.",
            "Treating 'accept' as the default for an opportunity the way it's often the "
            "safe default for a threat, when a modest investment in exploit or enhance "
            "might have captured real value.",
            "Trying to force the opportunity's response into a field literally named for "
            "threat responses and getting confused when 'exploit' doesn't fit — see the "
            "outputs note above.",
        ),
        worked_example=(
            "On the same robotics build, the team notices that if the connector "
            "qualification finishes early, a full week opens up before the next hardware "
            "milestone. Rather than leaving that as a passive hope, the PM enhances the "
            "opportunity by front-loading the connector team with an extra engineer for "
            "the first week, raising the odds of finishing early enough to use the slack "
            "on integration testing instead."
        ),
        further_reading=("PMBOK-6 §11.5.2.5",),
    ),
    "contingent_response_strategies": TechniqueContent(
        summary=(
            "A backup plan held in reserve and used only if a specific, named event actually happens."
        ),
        when_to_use=(
            "For a risk you've chosen to actively accept: you're not spending money now "
            "to reduce it, but you want a plan ready to go if it does happen, so the "
            "response isn't improvised under pressure."
        ),
        when_to_avoid=(
            "When the response would be the same whether or not the trigger is watched "
            "for — if the team would do the obvious thing regardless, writing it down as "
            "a formal contingent plan adds process without adding readiness. Also avoid "
            "this for a risk important enough to warrant real mitigation now; a "
            "contingency plan is not a substitute for reducing the risk in the first "
            "place."
        ),
        steps=(
            "Pick the risk being actively accepted, and confirm a mitigate-now response "
            "genuinely isn't the better choice.",
            "Define the trigger precisely — an observable, checkable condition, not a "
            "feeling. 'Vendor delivery slips more than 10 business days past the "
            "contracted date' is a trigger; 'if things start looking bad' is not.",
            "Write the response that activates once the trigger fires — what happens, "
            "who does it, and with what resources.",
            "Assign someone to actually watch for the trigger; a trigger nobody is "
            "watching for never fires on time.",
            "Hold the contingency reserve (budget, schedule slack, or people) the "
            "response will need, so it exists when the trigger does occur.",
        ),
        outputs=(
            "A written trigger condition, precise enough that two people would agree "
            "whether it has occurred.",
            "A predefined response tied to that trigger.",
            "An assigned watcher and a reserved contingency (time, budget, or capacity) "
            "the response can draw on.",
        ),
        pitfalls=(
            "Writing a contingency plan with no defined trigger condition at all — the "
            "single most common failure of this technique. Without a trigger, the plan is "
            "a document sitting in the register, not a response: nobody knows when to act "
            "on it, so in practice nobody does, and the 'accept' the team thought was "
            "active turns out to have been passive all along.",
            "Setting a trigger so vague ('if the schedule looks tight') that it's really "
            "a judgment call dressed up as a trigger, which defeats the purpose of "
            "defining one in advance.",
            "Reserving the contingency budget on paper but letting it get absorbed into "
            "general spend before the trigger ever fires.",
        ),
        worked_example=(
            "A software team accepts the risk that a third-party payments API might "
            "deprecate an endpoint mid-project, judging the probability too low to justify "
            "rework now. The contingent plan: trigger is 'the vendor posts a deprecation "
            "notice with a sunset date inside the project's remaining timeline'; response "
            "is 'the two engineers already familiar with the integration switch to the "
            "documented replacement endpoint within the sunset window'; the reserve is "
            "one week of those two engineers' time, held out of the schedule rather than "
            "committed to other work."
        ),
        further_reading=("PMBOK-6 §11.5.2.6",),
    ),
    "strategies_for_overall_project_risk": TechniqueContent(
        summary=("Responding to a project's risk as one combined whole, not just risk by risk."),
        when_to_use=(
            "At key decision points (major milestones, gate reviews, before committing to "
            "a firm deadline or price) when the question isn't 'what do we do about risk "
            "#14' but 'given everything we know is uncertain, how exposed is this project, "
            "and should we change course.'"
        ),
        when_to_avoid=(
            "As a substitute for individual risk response — a project-level judgment that "
            "'overall risk is moderate' doesn't tell anyone what to do about the specific "
            "vendor risk or the specific technical risk sitting in the register. Use both; "
            "neither replaces the other."
        ),
        steps=(
            "Step back from the individual register entries and ask what could most "
            "affect the project's overall cost, schedule, or objectives if several "
            "things went wrong together, not just one risk in isolation.",
            "Consider whether the project's overall risk exposure warrants a strategy at "
            "the project level: avoid (change the approach to remove a whole class of "
            "risk), exploit (restructure to capture a project-wide opportunity), "
            "transfer/share (restructure the commercial arrangement), or accept (proceed "
            "as planned, eyes open).",
            "Where the answer is to change course, make that change at the plan level — "
            "re-baseline, renegotiate scope, change the delivery approach — not by adding "
            "one more line to the risk register.",
            "Communicate the overall risk posture to sponsors and stakeholders "
            "separately from the register detail; they usually need the summary "
            "judgment, not the itemized list.",
        ),
        outputs=(
            "A stated judgment of overall project risk exposure at a point in time.",
            "A decision on whether the project's approach itself needs to change in "
            "response, distinct from any individual risk's response plan.",
            "A summary suitable for a sponsor conversation, separate from the detailed register.",
        ),
        pitfalls=(
            "Confusing this with 'sum up the register's exposure column and report the "
            "total' — that's an aggregate of individual risks, not an assessment of the "
            "project's overall risk, which includes effects (schedule compression, "
            "morale, dependency chains) that don't show up as line items at all. "
            "Driftless has no field or rollup that computes this for you; it stays a "
            "judgment call the PM makes and writes down.",
            "Making the overall-risk judgment once at kickoff and never revisiting it as "
            "the register itself changes shape over the project.",
            "Presenting the overall judgment as more rigorous than it is — it is a "
            "considered opinion, not a calculation, and should be labeled as such.",
        ),
        worked_example=(
            "A construction PM reviews a register with eleven individually 'medium' "
            "risks and no single 'high' one, and could report the project as broadly "
            "healthy. Stepping back, four of those eleven risks share a dependency on the "
            "same crane subcontractor's schedule; if that subcontractor slips, four "
            "risks fire together. The PM reports overall project risk as elevated despite "
            "no individual entry crossing the 'high' threshold, and pulls forward a "
            "conversation about a backup crane arrangement."
        ),
        further_reading=("PMBOK-6 §11.5.2.7",),
    ),
    "simulation": TechniqueContent(
        summary=(
            "Running a risk model many times with varying inputs to see the range of likely outcomes."
        ),
        when_to_use=(
            "When you need a probabilistic answer to 'how likely are we to finish by "
            "date X or under budget Y' — one that accounts for many uncertain inputs "
            "combining, including correlations between them (two tasks sharing the same "
            "delayed vendor, for instance) that a simple sum of point estimates can't "
            "represent."
        ),
        when_to_avoid=(
            "When you don't actually have distributions for the inputs — a simulation "
            "run on made-up ranges produces a precise-looking output from imprecise "
            "input, which is worse than an honest three-point estimate that admits it's "
            "rough. Also skip it when the answer doesn't need to be probabilistic at all; "
            "a straightforward reserve calculation is often enough."
        ),
        steps=(
            "Build a model of the project's cost or schedule logic — the tasks, "
            "dependencies, and cost items the simulation will vary.",
            "Assign a probability distribution to each uncertain input (see "
            "representations of uncertainty) rather than a single point estimate.",
            "Identify and encode correlations between inputs where they exist — inputs "
            "that move together (shared vendor, shared team) will understate risk if "
            "treated as independent.",
            "Choose an iteration count large enough for the output distribution to "
            "stabilize, and run the simulation.",
            "Read the output as a distribution — a P50, P80, P90 completion date or "
            "cost — not as a single answer, and decide what confidence level the "
            "commitment you make should be pinned to.",
        ),
        outputs=(
            "A probability distribution of possible project outcomes (cost, duration, "
            "or another modeled quantity), summarized as percentile figures such as "
            "P50/P80/P90.",
            "A defensible basis for setting a contingency reserve or a committed date at "
            "a stated confidence level rather than a guess.",
        ),
        pitfalls=(
            "Running the simulation on fabricated distributions and reporting the "
            "output with the same confidence you'd give a result built on real "
            "historical data — the output is only as honest as the inputs.",
            "Ignoring correlation between inputs, which systematically understates the "
            "tails of the outcome distribution.",
            "Confusing this with what Driftless actually has today: the schedule "
            "forecaster in ``driftless.calc.forecast`` runs a bootstrap simulation over "
            "past sprint velocity to forecast a completion date band. "
            "That is a real Monte Carlo method, but it samples historical velocity, not a "
            "risk model with cost/schedule distributions and correlations across the "
            "register. Driftless does not run a risk simulation of the kind described "
            "here, and there is no risk-model input (distributions, correlations, "
            "iteration count) anywhere in the product to run one from. A reader who wants "
            "this technique needs a separate quantitative risk analysis tool; this entry "
            "explains what the technique is and requires, not something you can launch "
            "from here.",
        ),
        worked_example=(
            "A construction estimator builds a cost model with twelve line items, each "
            "given a triangular distribution instead of a single figure, with steel and "
            "concrete costs correlated because both depend on the same regional supply "
            "conditions. Ten thousand iterations produce a cost distribution whose P80 "
            "figure — not the P50 — becomes the number the client contract is priced "
            "against, because the client wants 80% confidence of not exceeding the price."
        ),
        further_reading=("PMBOK-6 §11.4.2.5",),
    ),
    "sensitivity_analysis": TechniqueContent(
        summary=(
            "Changing one uncertain input at a time to see which ones actually move the outcome."
        ),
        when_to_use=(
            "When the risk register or cost model has more uncertain inputs than you "
            "have time or budget to manage carefully, and you need to know where the "
            "limited attention should go — usually before committing to a detailed "
            "response plan for every item."
        ),
        when_to_avoid=(
            "When the inputs interact strongly (varying one only makes sense in "
            "combination with another) — sensitivity analysis holds everything else "
            "fixed, which can mislead when the real risk is in how two or three factors "
            "move together. That's the case for a full simulation, not this technique."
        ),
        steps=(
            "List the uncertain inputs feeding the outcome you care about (cost, "
            "schedule, or another project objective).",
            "For each input in turn, vary it across its plausible range while holding "
            "every other input at its baseline value.",
            "Record how much the outcome moves for each input's swing.",
            "Rank the inputs by how much outcome movement they cause — this is usually "
            "displayed as a tornado diagram, widest bar at top.",
            "Direct further analysis, monitoring, and response planning at the handful "
            "of inputs at the top of that ranking, not evenly across all of them.",
        ),
        outputs=(
            "A ranked list of which uncertain inputs most affect the outcome — usually "
            "presented as a tornado diagram.",
            "A justified basis for concentrating monitoring and response effort on a "
            "small subset of the risks or estimates in play.",
        ),
        pitfalls=(
            "Treating the register's sheer size or the loudest risk as a proxy for which "
            "risks matter most, when a proper sensitivity pass usually shows the set that "
            "actually moves the outcome is much smaller than the register suggests — and "
            "isn't always the same set as the highest-exposure entries.",
            "Varying inputs one at a time and stopping there, when the biggest real "
            "exposure sometimes only appears when two inputs move together — the case "
            "this technique deliberately doesn't cover.",
            "Doing the analysis once early in the project and never repeating it as "
            "estimates firm up and the ranking shifts.",
        ),
        worked_example=(
            "A software rewrite has nine uncertain cost inputs. Varying each alone shows "
            "that swings in 'third-party licensing renewal cost' and 'senior engineer "
            "availability' each move the total project cost by more than 15%, while the "
            "other seven inputs — including the one the team spent the most meeting time "
            "debating — each move it by under 3%. The PM redirects the risk owner's "
            "attention to the two inputs that matter and stops tracking weekly updates on "
            "the rest."
        ),
        further_reading=("PMBOK-6 §11.4.2.5",),
    ),
    "decision_tree_analysis": TechniqueContent(
        summary=(
            "Mapping an uncertain decision as branching choices and chances, then weighing each branch's likely value."
        ),
        when_to_use=(
            "For a discrete decision with a small number of real alternatives, where at "
            "least one branch involves a chance event with an estimable probability and "
            "payoff — build in-house versus buy a component with an uncertain defect "
            "rate, for instance, or invest in a fix now versus risk a penalty later."
        ),
        when_to_avoid=(
            "When the decision has continuous or many interacting uncertain factors "
            "rather than a handful of discrete branches — the tree gets unreadable, and "
            "simulation is the better tool. Also avoid it when the probabilities plugged "
            "into the tree are pure guesses dressed up as numbers; the arithmetic looks "
            "rigorous regardless of input quality, which can mislead a decision-maker "
            "into more confidence than the numbers deserve."
        ),
        steps=(
            "Draw the decision as a tree: a decision node for each choice available, a "
            "chance node for each uncertain event, and an end value for each resulting "
            "outcome.",
            "Assign a probability to each branch out of a chance node; they must sum to "
            "1 at each node.",
            "Assign a monetary value (cost or payoff) to each end-of-branch outcome.",
            "Working from the tree's ends back toward its root, compute the expected "
            "monetary value (EMV) at each chance node: sum of (probability x outcome "
            "value) across its branches.",
            "At each decision node, choose the branch with the better EMV — the tree "
            "makes that comparison explicit instead of leaving it to intuition.",
            "Report the chosen path and its EMV, along with the tree itself so the "
            "reasoning is checkable by someone else.",
        ),
        outputs=(
            "A decision tree diagram showing the choices, chance events, probabilities, "
            "and payoffs.",
            "An expected monetary value for each option under consideration.",
            "A recommended choice, with the reasoning behind it laid out rather than asserted.",
        ),
        pitfalls=(
            "Presenting EMV as a guaranteed outcome rather than an average across many "
            "hypothetical repeats of the same decision — a project only happens once, so "
            "the EMV-best choice can still lose on this particular run, and a "
            "risk-averse stakeholder may reasonably prefer the lower-EMV, lower-variance "
            "option.",
            "Assigning probabilities without a stated basis, so the EMV inherits false "
            "precision from numbers nobody could defend under questioning.",
            "Omitting a real alternative from the tree because it complicates the "
            "diagram, which quietly biases the analysis toward whichever options were "
            "easiest to draw.",
        ),
        worked_example=(
            "A manufacturer deciding whether to tool a part in-house or outsource it "
            "draws a tree: tooling in-house costs $80,000 up front, with a 20% chance of "
            "a $40,000 rework if the first run fails tolerance (EMV = 80,000 + "
            "0.2 x 40,000 = $88,000). Outsourcing costs a flat $95,000 with no rework "
            "risk. The tree makes the comparison explicit: $88,000 expected versus "
            "$95,000 certain, and the PM chooses in-house, accepting the wider possible "
            "range in exchange for the better average."
        ),
        further_reading=("PMBOK-6 §11.4.2.5",),
    ),
    "influence_diagrams": TechniqueContent(
        summary=(
            "A network diagram showing how decisions, uncertain events, and outcomes affect one another."
        ),
        when_to_use=(
            "When a decision involves several interacting uncertain factors that would "
            "make a decision tree's branches multiply out of hand, and you want a single "
            "diagram that shows what depends on what without enumerating every "
            "combination explicitly."
        ),
        when_to_avoid=(
            "For a decision simple enough that a decision tree already communicates it "
            "clearly — an influence diagram trades the tree's readable branch-by-branch "
            "payoffs for compactness, and that trade isn't worth it when there's nothing "
            "to compress. It's also a weaker tool than a tree for actually walking a "
            "stakeholder through why a specific choice wins."
        ),
        steps=(
            "Identify the decision points, uncertain (chance) factors, and final "
            "outcome measures relevant to the situation.",
            "Draw a node for each: typically a rectangle for a decision, an oval for an "
            "uncertain factor, and a diamond or rounded shape for an outcome value.",
            "Draw an arrow between any two nodes where one directly influences the "
            "other — this is the diagram's main content, and getting it right requires "
            "genuinely understanding the causal structure, not just listing everything "
            "you know about.",
            "Check the diagram for cycles; a decision-support diagram should resolve in "
            "one direction, decisions and chance factors flowing toward the outcome.",
            "Use the diagram to identify which factors most directly drive the outcome, "
            "and to check whether a proposed decision addresses a real influence or a "
            "coincidental one.",
        ),
        outputs=(
            "A network diagram of decisions, uncertain factors, and outcomes with "
            "directional influence relationships marked.",
            "A shared, checkable picture of what the team believes drives the outcome — "
            "useful for spotting a disagreement about causation before it becomes a "
            "disagreement about the decision.",
        ),
        pitfalls=(
            "Drawing every factor anyone mentions instead of only the ones with a real "
            "influence relationship, which produces a diagram too tangled to read — the "
            "opposite of what it's for.",
            "Treating the arrows as proven causation when they're really the team's "
            "working assumption; the diagram is only as good as the shared understanding "
            "behind it.",
            "Using this in place of a decision tree when a stakeholder actually needs to "
            "see the specific expected-value comparison between two named choices — the "
            "diagram doesn't compute a number the way a tree's EMV rollup does.",
        ),
        worked_example=(
            "A product launch decision involves three interacting uncertainties: "
            "competitor timing, manufacturing yield, and a regulatory approval date. "
            "Rather than drawing eight separate decision-tree branches for every "
            "combination, the team draws one influence diagram: an arrow from "
            "'regulatory approval date' to 'launch window,' one from 'manufacturing "
            "yield' to 'units available at launch,' and one from 'competitor timing' to "
            "'pricing decision.' The diagram makes visible that pricing and launch "
            "timing are influenced by different, independent factors — a fact the team "
            "had been implicitly treating as one combined risk."
        ),
        further_reading=("PMBOK-6 §11.4.2.5",),
    ),
    "prompt_lists": TechniqueContent(
        summary=(
            "Working through a predetermined list of risk categories to surface risks a free-form discussion would miss."
        ),
        when_to_use=(
            "During Identify Risks, after the team's own brainstorming and "
            "interviews have run dry — a prompt list (a category framework "
            "like PESTLE, or a project-specific risk breakdown structure) "
            "forces a pass through categories nobody happened to think of on "
            "their own."
        ),
        when_to_avoid=(
            "As the only identification technique, or as a checkbox exercise "
            "run without engaging with what each category actually implies "
            "for this project. A prompt list surfaces categories to think "
            "about; it doesn't do the thinking."
        ),
        steps=(
            "Choose a category framework that fits the project (a generic "
            "list like PESTLE, or a risk breakdown structure built for this "
            "kind of work).",
            "Walk the team through each category and ask what could go "
            "wrong in that area on this specific project.",
            "Record anything genuinely new the category surfaces in the "
            "risk register; skip a category that plainly does not apply.",
        ),
        outputs=("Risk register entries surfaced by a category the team had not yet considered.",),
        pitfalls=(
            "Running the list as a box-ticking exercise, recording nothing "
            "specific to the project under most categories.",
            "Treating it as a complete identification technique instead of a "
            "supplement to brainstorming and interviews.",
        ),
        worked_example=(
            "Having exhausted the team's own ideas, the PM runs the "
            "retrofit through a construction-specific prompt list. The "
            "'permitting' category surfaces a risk nobody had raised: the "
            "historic district's design review board could require a "
            "resubmission if the exterior finish changes."
        ),
        further_reading=("PMBOK-6 §11.2.2.5",),
    ),
}
