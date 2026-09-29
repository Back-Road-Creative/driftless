"""Technique explanations for the stakeholder family (tt.FAMILIES["stakeholder"]).

Two things live in this one family: the three techniques that are actually
about stakeholders (identifying and tracking them) and four group-decision /
data-gathering techniques (voting, autocratic decision making, weighted
criteria, focus groups) that PMBOK-6 files under stakeholder or planning
processes without giving them a family of their own. Both halves get equal
treatment below.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "stakeholder"

CONTENT: dict[str, TechniqueContent] = {
    "stakeholder_analysis": TechniqueContent(
        summary=(
            "Finding everyone with a stake in the project, and recording what each one wants and can affect."
        ),
        when_to_use=(
            "At project start, and again at every major phase change or scope shift. Use it "
            "whenever the cast of people who care about the project is bigger, or less "
            "obvious, than the org chart suggests."
        ),
        when_to_avoid=(
            "On a small, contained project with an obvious and stable set of stakeholders, a "
            "full analysis is overhead — a short list on a page does the same job. Avoid "
            "running it once at kickoff and calling it done: a register that is never "
            "revisited goes stale the moment the project's shape changes, and a stale "
            "register is worse than none because it looks authoritative."
        ),
        steps=(
            "List everyone with formal authority over the project first: sponsor, "
            "governance board, budget owner.",
            "Widen the net past the org chart: ask who has to approve, use, maintain, "
            "inspect, or live next to what the project produces.",
            "Deliberately look for people with no formal role who can still stop the work — "
            "a regulator, a union rep, an end user with informal veto power, a team that "
            "will quietly deprioritize your dependency.",
            "For each stakeholder, record interest (how much they care about the outcome) "
            "and influence (how much power they have over it).",
            "Group stakeholders by interest and influence and decide an engagement approach "
            "for each group, not each individual.",
            "Set a review cadence — tied to phase gates, not a fixed calendar date — and "
            "revisit the register at each one.",
        ),
        outputs=(
            "A stakeholder register listing each stakeholder with interest and influence recorded.",
            "An engagement approach per stakeholder group.",
            "A scheduled point to revisit the register as the project changes.",
        ),
        pitfalls=(
            "Only listing people already attending meetings, so the analysis just confirms "
            "who you already knew about.",
            "Treating the register as a one-time kickoff artifact and never updating it as "
            "the project's stakeholders change — a new vendor, a reorg, a regulator who "
            "shows up in month six all go unrecorded.",
            "Missing the informal stakeholder with no title but real power to delay or block "
            "the work, because the search stopped at the org chart.",
        ),
        worked_example=(
            "A team replacing a warehouse's inventory system lists the obvious stakeholders — "
            "sponsor, warehouse manager, IT — and stops there. A stakeholder analysis session "
            "surfaces two more: the third-shift forklift crew, who were never consulted and "
            "will refuse to use a system that slows down picking, and the fire marshal, whose "
            "sign-off on the new floor layout is required before go-live. Both get added to "
            "the register with high influence, and the rollout plan changes to include a "
            "shift-floor pilot and an early fire-code review."
        ),
        further_reading=("PMBOK-6 §13.1.2.3",),
    ),
    "stakeholder_engagement_assessment_matrix": TechniqueContent(
        summary=(
            "A table comparing a stakeholder's current involvement against the involvement a project actually needs from them."
        ),
        when_to_use=(
            "When a stakeholder register alone doesn't tell you what to do next: use this "
            "once you know who the stakeholders are and need a plan for closing the distance "
            "between where each one stands today and where the project needs them to stand."
        ),
        when_to_avoid=(
            "Don't run it before a basic stakeholder analysis exists — there's nothing to "
            "assess a gap against. And don't run it in driftless expecting to record the "
            "result: this product stores only interest and influence (each low, medium, or "
            "high) on the stakeholder record, with no current-versus-desired engagement "
            "field at all. A reader can work through the technique on paper, but there is "
            "nowhere here yet to capture what it produces."
        ),
        steps=(
            "For each stakeholder, mark their current engagement level: unaware, resistant, "
            "neutral, supportive, or leading.",
            "For each stakeholder, mark the desired engagement level needed for the project "
            "to succeed.",
            "Plot both on the same row and look at the gap, not just the current position.",
            "For each gap, decide a specific action to move the stakeholder toward the "
            "desired level, sized to how large the gap is.",
            "Prioritize action on the stakeholders whose gap is both large and high-influence.",
        ),
        outputs=(
            "A matrix of current versus desired engagement, one row per stakeholder.",
            "A prioritized list of engagement actions targeted at the largest, highest-"
            "influence gaps.",
        ),
        pitfalls=(
            "Recording the assessment once and never re-plotting it, so a stakeholder who "
            "has moved from resistant to neutral still gets treated as an active blocker.",
            "Spending equal engagement effort on every gap instead of weighting by influence, "
            "which burns time on stakeholders who were never going to affect the outcome.",
            "In this product specifically: doing the assessment out of band and having no "
            "field to record it in, so the result lives in a spreadsheet nobody else sees.",
        ),
        worked_example=(
            "On a hospital scheduling rollout, the head nurse starts out resistant — she "
            "wasn't consulted on the pilot design — while the project needs her leading, "
            "since staff will follow her lead over any memo from IT. The gap between "
            "resistant and leading is the largest on the matrix, so the team schedules a "
            "working session with her before anyone else, rather than sending the standard "
            "rollout email to the whole department."
        ),
        further_reading=("PMBOK-6 §13.4.2.3",),
    ),
    "ground_rules": TechniqueContent(
        summary=(
            "A team's written agreement on how it will behave, made before any real disagreement tests it."
        ),
        when_to_use=(
            "At team formation, when a new team is assembled from different departments or "
            "organizations with different norms, or whenever a recurring behavior problem "
            "(talking over people, side deals outside meetings, missed commitments) needs a "
            "shared standard to point back to."
        ),
        when_to_avoid=(
            "Skip a formal ground-rules session for a short-lived, low-stakes team where "
            "informal norms will do — the ceremony costs more than the problem it prevents. "
            "Also skip it if you can't commit to enforcing whatever gets agreed: ground rules "
            "that exist only on a slide are worse than none, because they set an expectation "
            "the team learns not to trust."
        ),
        steps=(
            "Gather the team and ask what has caused friction on past projects, not just "
            "what sounds virtuous in the abstract.",
            "Turn each answer into a specific, observable rule — 'raise disagreement in the "
            "room, not after' rather than 'be respectful'.",
            "Get explicit agreement from everyone in the room, not just silence.",
            "Write the rules down somewhere the team will actually see again.",
            "Name, in advance, what happens when a rule is broken and who raises it.",
            "Enforce the first violation visibly — this is what makes the rules real.",
        ),
        outputs=(
            "A short, specific, written list of agreed team behaviors.",
            "A named mechanism for raising and handling a violation.",
        ),
        pitfalls=(
            "Rules agreed in an enthusiastic kickoff session that nobody enforces the first "
            "time one is broken — after that, everyone knows they're decorative, and they're "
            "gone.",
            "Writing rules so generic ('communicate openly') that no one can point to a "
            "specific violation, so enforcement never has anything concrete to act on.",
            "One person setting the rules and presenting them for sign-off rather than "
            "drawing them out of the team, which produces compliance instead of buy-in.",
        ),
        worked_example=(
            "A cross-agency data-migration team, three organizations working together for "
            "the first time, agrees a ground rule that no scope decision made outside the "
            "weekly sync counts until it is reported back to the group. Six weeks in, one "
            "partner's lead tries to commit a schedule change in a side conversation. The "
            "project manager points to the rule in the next sync, the change is reopened for "
            "the full group, and the rule holds for the rest of the project because that "
            "first test was enforced rather than let slide."
        ),
        further_reading=("PMBOK-6 §13.3.2.4",),
    ),
    "voting": TechniqueContent(
        summary=(
            "A group decides by each member stating a preference, then applying an agreed rule to it."
        ),
        when_to_use=(
            "When a decision needs the group's buy-in and there's no single accountable "
            "decision-maker better positioned to just decide — choosing among a short, "
            "already-narrowed set of options."
        ),
        when_to_avoid=(
            "Don't vote on a decision that needs technical or safety expertise the group "
            "doesn't have — a popular answer isn't necessarily a correct one. And don't vote "
            "without first agreeing the rule: unanimity, majority, and plurality can each "
            "produce a different winner from the exact same set of individual preferences, "
            "so picking the rule after seeing informal sentiment is picking the outcome, not "
            "running a vote."
        ),
        steps=(
            "Narrow the decision to a short list of concrete options before voting opens.",
            "Choose and announce the voting rule before anyone votes: unanimity (everyone "
            "must agree), majority (more than half), or plurality (most votes among 3+ "
            "options, without needing half).",
            "Collect votes, in the open or by secret ballot depending on whether visible "
            "peer pressure would distort the result.",
            "Apply the announced rule and declare the outcome.",
            "If unanimity or majority fails to produce a decision, name the fallback (a "
            "re-vote on a narrowed list, or escalation) in advance rather than improvising "
            "one after the fact.",
        ),
        outputs=(
            "A decision selected under a stated, pre-agreed rule.",
            "A record of the vote, useful if the decision is challenged later.",
        ),
        pitfalls=(
            "Choosing the voting rule after an informal show of hands, so the 'real' vote "
            "just ratifies whichever rule produces the already-favored answer.",
            "Using plurality across many options and mistaking a 30% winner for a mandate, "
            "when 70% of the group preferred something else.",
            "Voting on a question the group doesn't actually have the standing or expertise "
            "to answer, then treating the result as settled.",
        ),
        worked_example=(
            "A steering committee of six is choosing among three vendor shortlist finalists. "
            "Under plurality, Vendor B wins with 3 of 6 votes split against 2 vendors that "
            "together took the other 3. The chair notices this before announcing the result, "
            "and instead runs a second round between B and the closer second-place finisher "
            "under a majority rule, which the group had agreed as the fallback in advance — "
            "avoiding a decision that a bare plurality would have made look more settled "
            "than it was."
        ),
        further_reading=("PMBOK-6 §5.2.2.4",),
    ),
    "autocratic_decision_making": TechniqueContent(
        summary=(
            "One person — usually the project manager or another accountable role — makes "
            "the decision alone, without a group vote or consensus process."
        ),
        when_to_use=(
            "Under real time pressure, where accountability for the outcome is clearly and "
            "solely held by one person, or where the decision is technical or narrow enough "
            "that consulting the wider group would be theatre rather than useful input. It "
            "is a legitimate, often correct, choice in those conditions — not a fallback to "
            "apologize for."
        ),
        when_to_avoid=(
            "Avoid it when the decision needs the group's buy-in to actually get "
            "implemented, or when the people affected have information the decision-maker "
            "doesn't have and hasn't asked for. Above all, never use it while pretending "
            "consultation happened — running a 'discussion' whose outcome was already "
            "decided costs more trust than deciding openly and saying so would have."
        ),
        steps=(
            "Confirm the decision genuinely sits with one accountable person — check this "
            "before acting, not after someone objects.",
            "Gather whatever input is fast to get and actually useful, without treating it "
            "as a vote.",
            "Make the decision.",
            "State plainly that this was a unilateral call and why — the time pressure, the "
            "accountability, the technical narrowness — rather than dressing it up as group "
            "consensus.",
            "Communicate the decision and the reasoning to everyone affected.",
        ),
        outputs=(
            "A decision made quickly, with a single named owner.",
            "A stated reason the decision was made this way, on the record.",
        ),
        pitfalls=(
            "Running a sham consultation — asking for input on a decision that's already "
            "made — which erodes trust further than an honest 'I decided this' would have.",
            "Reaching for it as a default when the real reason is avoiding a harder "
            "conversation, not genuine time pressure or clear accountability.",
            "Using it on a decision that needed the affected team's buy-in to actually be "
            "implementable, and then being surprised when implementation stalls.",
        ),
        worked_example=(
            "A production outage is degrading customer checkout. The engineering lead has "
            "fifteen minutes to choose between two rollback options, both with tradeoffs, "
            "and is the only person with the on-call context to weigh them properly. She "
            "decides alone, executes the rollback, and posts a two-line note afterward: 'I "
            "made this call unilaterally given the time window; here's why, and here's what "
            "I didn't have time to check.' The team accepts the decision because it was "
            "presented as what it was."
        ),
        further_reading=("PMBOK-6 §5.2.2.4",),
    ),
    "multicriteria_decision_analysis": TechniqueContent(
        summary=(
            "Scoring several options against stated, weighted criteria, so the choice is traceable rather than argued."
        ),
        when_to_use=(
            "When choosing among several viable options — vendors, designs, sites — on more "
            "than one dimension (cost, risk, capability, schedule) and you need the "
            "reasoning to survive being questioned later."
        ),
        when_to_avoid=(
            "Skip it for a decision with one obviously dominant option or one overriding "
            "constraint — the scoring exercise just launders a call that was already made. "
            "And treat with suspicion any use where the criteria and weights were set after "
            "the options were already known: weights chosen to fit a preferred answer are "
            "justification, not analysis, even though the resulting table looks identical "
            "to one honestly built."
        ),
        steps=(
            "Define the criteria that matter to the decision before looking closely at the "
            "specific options.",
            "Assign each criterion a weight reflecting its relative importance, and agree "
            "the weights with stakeholders before scoring begins.",
            "Score each option against each criterion using a consistent scale.",
            "Multiply each score by its criterion's weight and sum for a total per option.",
            "Sanity-check the ranking against intuition — if the top result feels wrong, "
            "check whether a criterion is missing or a weight is off, rather than silently "
            "overriding the score.",
        ),
        outputs=(
            "A weighted score for each option, with the weights and criteria on record.",
            "A ranked list of options traceable to stated priorities rather than to "
            "afterward-supplied reasoning.",
        ),
        pitfalls=(
            "Setting weights after seeing how the options score, to steer the total toward "
            "a preferred outcome — the table format makes this look like analysis even when "
            "it's the opposite.",
            "Choosing criteria that all correlate with each other, so one underlying factor "
            "gets counted three or four times under different names.",
            "Treating the weighted total as a decision rather than an input, and skipping "
            "the sanity check when the top-ranked option is surprising.",
        ),
        worked_example=(
            "A city is choosing a paving contractor. The procurement team sets criteria — "
            "price (40%), prior public-project experience (30%), crew availability in the "
            "required window (20%), local references (10%) — and publishes the weights "
            "before opening bids. The lowest-price bidder scores second overall once "
            "availability and experience are weighted in, and the award goes to the "
            "higher-priced bidder with the paper trail to defend it when the losing bidder "
            "asks why."
        ),
        further_reading=("PMBOK-6 §5.2.2.4",),
    ),
    "focus_groups": TechniqueContent(
        summary=(
            "A guided discussion where a small group's interaction, not just each answer, is what gets studied."
        ),
        when_to_use=(
            "When you want to see how people react to an idea, product, or requirement in "
            "conversation with each other, surfacing disagreement and unstated assumptions "
            "that a one-on-one interview wouldn't produce."
        ),
        when_to_avoid=(
            "Don't use a focus group when you need a working session that produces a "
            "decision or artifact — that's a workshop, a different technique. And don't use "
            "one when you need each person's honest individual view without social pressure "
            "— that's an interview. A focus group's biggest risk is a dominant participant "
            "steering the room toward a consensus that doesn't actually exist once people "
            "are asked alone; if that risk is high for this group, run interviews instead."
        ),
        steps=(
            "Recruit a small, relevant group — enough to generate real interaction, small "
            "enough that everyone gets airtime.",
            "Prepare an open-ended discussion guide rather than a closed questionnaire.",
            "Have a moderator run the session whose job is to draw out quieter participants "
            "and interrupt anyone dominating the discussion.",
            "Record or take detailed notes on both what is said and where the group agrees "
            "or splits.",
            "Afterward, check any apparent consensus against what individuals said "
            "one-on-one, if that's available, before treating it as settled.",
        ),
        outputs=(
            "Qualitative findings on how the group reacts to and discusses the topic.",
            "Identified points of agreement and disagreement within the group.",
        ),
        pitfalls=(
            "Letting one confident participant dominate, producing an apparent consensus "
            "that vanishes the moment quieter participants are asked individually.",
            "Recruiting a group that's really a set of individual interviews conducted in "
            "the same room, losing the interaction that makes the technique worth running.",
            "Treating a single focus group's findings as representative of the whole "
            "stakeholder population, rather than as one data point to weigh against others.",
        ),
        worked_example=(
            "A team redesigning a benefits enrollment form runs a focus group of eight "
            "employees. Discussion converges quickly on the group liking a single-page "
            "layout, led by one particularly vocal participant. The moderator notices two "
            "others nodding along but not speaking, and follows up with them individually "
            "afterward — both admit they preferred the multi-page version but didn't want "
            "to disagree in the room. The team runs the single-page design past a short "
            "individual survey before committing, rather than treating the group session "
            "alone as the answer."
        ),
        further_reading=("PMBOK-6 §5.2.2.2",),
    ),
}
