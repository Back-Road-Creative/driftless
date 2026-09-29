"""Technique explanations for the general family (tt.FAMILIES["general"]).

These twelve are PMBOK-6's cross-cutting families: umbrella headings that
cover many named methods (data gathering, data analysis, data
representation, decision making, interpersonal and team skills), a
default that shows up in nearly every process (expert judgment), and a
set of communication concepts that are easy to blur together
(methods/models/skills/technology). The umbrella entries name the
methods they cover and say how to pick between them rather than
duplicating guides that belong to those methods' own catalog entries.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "general"

CONTENT: dict[str, TechniqueContent] = {
    "expert_judgment": TechniqueContent(
        summary=(
            "Asking someone experienced for a judgment call instead of working the answer out from scratch yourself."
        ),
        when_to_use=(
            "The question needs judgment a specialist has built up (an estimator's feel "
            "for a task, a lawyer's read on a clause, a senior engineer's sense of where a "
            "design will break) and getting a data-backed answer instead would cost more "
            "time or money than the decision is worth."
        ),
        when_to_avoid=(
            "When the evidence already exists and asking someone is just faster than "
            "looking it up — you'll get an opinion where a fact was available, and it will "
            "read as more authoritative than it is. Also avoid it when only one expert is "
            "reachable on a decision with real consequences: a single unchallenged opinion "
            "presented as 'expert judgment' is how a guess becomes policy. If the same "
            "person is asked the same kind of question every time with no record of what "
            "they were told, you've built an oracle nobody can audit."
        ),
        steps=(
            "Write down the specific question before contacting anyone — a vague ask "
            "produces a vague, unreviewable answer.",
            "Identify who actually has standing on this question (role, past experience, "
            "certification) rather than who is easiest to reach.",
            "Give them the same background material and constraints you'd give a second "
            "opinion, so their answer is comparable to one.",
            "For a consequential call, get more than one opinion and note where they agree "
            "and where they diverge.",
            "Record the question, who answered, what they were told, and their answer — "
            "not just the conclusion.",
            "Fold the judgment into the deliverable it informs (an estimate, a risk rating, "
            "a design decision) and keep the record attached to it.",
        ),
        outputs=(
            "A documented judgment: the question asked, who answered it and on what basis, "
            "and how it fed the deliverable it informed.",
        ),
        pitfalls=(
            "Asking only one person and treating the answer as settled fact.",
            "Not recording who was asked or what they were told, so a later reader can't "
            "tell whether the input was informed or offhand.",
            "Reaching for an expert because gathering real data felt like more work, when "
            "the data was gatherable.",
            "Letting seniority stand in for relevance — the most senior person in the room "
            "is not automatically the right expert for this question.",
            "Anchoring: showing the expert your own guess before asking theirs.",
        ),
        worked_example=(
            "A PM planning a warehouse retrofit needs a rough duration for re-routing "
            "overhead conduit around a new mezzanine. No historical data exists for this "
            "exact configuration. She writes the specific question, sends the drawings and "
            "constraints to two electricians who've done similar retrofits, and asks each "
            "independently. One says three days, the other four, both citing the same "
            "conduit run as the risk. She logs both answers with their reasoning, uses four "
            "days with a note on why, and attaches the log to the estimate."
        ),
        further_reading=(),
    ),
    "data_gathering": TechniqueContent(
        summary=(
            "The general term for methods that collect information a project does not already have."
        ),
        when_to_use=(
            "A process step needs input you don't have on hand and picking the right "
            "collection method for the audience and the question matters more than "
            "grabbing the first one that comes to mind."
        ),
        when_to_avoid=(
            "When the information already exists in project records, a prior report, or "
            "an expert's head and gathering it fresh would just duplicate work. Also avoid "
            "defaulting to the heaviest method (a formal survey) for a question a five-"
            "minute interview would answer just as well — the cost of the method should "
            "match the size of the decision."
        ),
        steps=(
            "State the specific question you need answered before choosing a method.",
            "Match the method to the audience and the question: brainstorming for "
            "generating options with a group, interviews for depth with a few people, "
            "surveys for breadth across many, focus groups for reaction to something "
            "concrete, checklists for verifying against a known list, benchmarking for "
            "comparing against an external reference, market research for external "
            "conditions you don't control.",
            "For a method with its own catalog entry — benchmarking, focus groups, or a "
            "structured interview — follow that entry's steps rather than improvising.",
            "Collect from enough sources that one outlier answer can't dominate the result.",
            "Record the raw responses before you summarize them, so the summary can be "
            "checked against what was actually said.",
        ),
        outputs=("A raw data set, with its source and collection method noted.",),
        pitfalls=(
            "Choosing a method because it's familiar rather than because it fits the "
            "question — running a survey when three interviews would have surfaced the "
            "same information faster.",
            "Collecting from a convenience sample (whoever answered email first) and "
            "presenting it as representative.",
            "Skipping straight to a summary and losing the raw responses, so a later "
            "disagreement about what was said can't be resolved.",
            "Re-gathering data that already existed in a prior deliverable.",
        ),
        worked_example=(
            "A team scoping a new intake form needs to know which fields caseworkers "
            "actually use versus which they skip. Rather than a survey, the analyst runs "
            "four short interviews with caseworkers who use the current form daily, asks "
            "each the same set of questions, and writes up the raw answers before drafting "
            "the recommended field list."
        ),
        further_reading=(),
    ),
    "data_analysis": TechniqueContent(
        summary=("The general term for methods that turn data you already have into a conclusion."),
        when_to_use=(
            "You have data in hand — status reports, cost records, a stack of documents, a "
            "set of candidate options — and need to turn it into a decision or a finding, "
            "and the choice of analysis method changes what conclusion you'll reach."
        ),
        when_to_avoid=(
            "When the data doesn't exist yet — that's data gathering, not analysis, and "
            "running an analysis method on a data set too thin to support it produces a "
            "confident-looking conclusion from noise. Also avoid an elaborate method "
            "(a full earned value analysis) when a simple one (a variance check against "
            "last period) answers the actual question."
        ),
        steps=(
            "Name the decision or finding the analysis needs to support before picking a method.",
            "Pick the method that matches the data shape and the question: alternatives "
            "analysis for choosing between options, cost-benefit for a go/no-go on spend, "
            "trend or variance analysis for tracking against a baseline, root cause "
            "analysis for why something went wrong, document analysis for extracting "
            "requirements or constraints from existing text.",
            "For a method with its own catalog entry — root cause analysis, earned value "
            "analysis — follow that entry's steps.",
            "Run the analysis against the full data set, not a hand-picked subset that "
            "supports the answer you expected.",
            "State the conclusion alongside the method used and the data it drew on, so "
            "the reasoning is checkable, not just the result.",
        ),
        outputs=(
            "A finding or recommendation, with the method used and the data it drew on "
            "stated alongside it.",
        ),
        pitfalls=(
            "Running an analysis on data too sparse to support it and presenting the "
            "result with unwarranted confidence.",
            "Cherry-picking the subset of data that confirms the answer you already wanted.",
            "Naming the analysis without stating the method — 'we analyzed the data' tells "
            "a reader nothing they can check.",
            "Confusing correlation surfaced by the analysis with a cause, especially in "
            "trend and variance work.",
        ),
        worked_example=(
            "A cost lead sees the retrofit project's monthly spend running above plan for "
            "the third month running. She runs a variance analysis comparing planned "
            "versus actual by cost category, finds the overrun is concentrated in "
            "electrical materials, and hands that finding — with the category breakdown "
            "attached — to the team lead rather than a generic 'we're over budget.'"
        ),
        further_reading=(),
    ),
    "data_representation": TechniqueContent(
        summary=(
            "The general term for turning analyzed data into a picture a reader can absorb quickly."
        ),
        when_to_use=(
            "You have a finding or a data set and the audience needs to see the "
            "relationships in it, not just read a description of them — grouping, "
            "hierarchy, cause-and-effect, or a two-axis comparison are each easier to "
            "absorb visually than as prose."
        ),
        when_to_avoid=(
            "When a plain sentence or a single number says everything the audience needs — "
            "building a matrix diagram for a decision with one clear answer is decoration, "
            "not communication. Also avoid picking a format for its polish rather than its "
            "fit: a mind map dressed up to look rigorous doesn't make a fuzzy idea rigorous."
        ),
        steps=(
            "Identify the relationship in the data that matters most — grouping, "
            "hierarchy, cause-and-effect, sequence, or a two-axis comparison.",
            "Pick the format built for that relationship: affinity diagrams for grouping "
            "loose ideas, cause-and-effect diagrams for tracing a problem to its sources, "
            "flowcharts for sequence and branching, hierarchical charts for structure, "
            "matrix diagrams or a probability-and-impact matrix for two-axis comparison, "
            "SWOT for a four-quadrant internal/external view.",
            "Build it from the data you already analyzed — don't let the act of drawing "
            "the diagram substitute for having done the analysis.",
            "Label every element; an unlabeled box or arrow forces the reader to guess what "
            "you meant.",
            "Check the diagram against the underlying data once more before it goes into a "
            "deliverable — a mislabeled node is easy to introduce while drawing.",
        ),
        outputs=("A diagram or chart that carries the finding, plus the data it was built from.",),
        pitfalls=(
            "Picking a format for how it looks rather than what relationship it's built to "
            "show — a fishbone diagram for data with no cause-and-effect structure.",
            "Skipping labels and leaving the reader to infer what a box or axis means.",
            "Treating the diagram as the analysis instead of a representation of analysis "
            "already done.",
            "Letting the diagram go stale after the underlying data changes.",
        ),
        worked_example=(
            "After the root cause analysis on late deliveries turns up five contributing "
            "factors, the quality lead builds a cause-and-effect diagram grouping them "
            "under supplier lead time, internal scheduling, and inspection delay, so the "
            "steering committee can see which branch to attack first instead of reading a "
            "five-item list."
        ),
        further_reading=(),
    ),
    "decision_making": TechniqueContent(
        summary=(
            "The general term for how a group turns its options into one chosen course of action."
        ),
        when_to_use=(
            "More than one viable option exists and how the choice gets made — who "
            "decides, and by what rule — will affect whether the group accepts the "
            "outcome, not just what the outcome is."
        ),
        when_to_avoid=(
            "When there's really only one workable option — running a formal decision "
            "method to bless a foregone conclusion wastes the group's time and teaches "
            "them the process is theater. Also avoid it when the decision needs a specific "
            "accountable owner and a group method (voting) would diffuse that "
            "accountability instead of assigning it."
        ),
        steps=(
            "Decide who has authority over this decision before picking a method for it.",
            "Pick the method that fits: voting when the group's buy-in matters and the "
            "options are few and clear, autocratic decision making when one accountable "
            "person needs to own the call and speed matters, multicriteria decision "
            "analysis when the options need to be scored against several weighted factors "
            "at once.",
            "For a method with its own catalog entry — voting, autocratic decision making, "
            "multicriteria decision analysis — follow that entry's steps.",
            "State the decision, who made it, and by which method, in the record.",
            "Communicate the decision and its rationale to everyone affected by it, even "
            "those who didn't participate in making it.",
        ),
        outputs=("A recorded decision: the choice, who made it, and the method used to make it.",),
        pitfalls=(
            "Running a vote to manufacture the appearance of consensus on a decision that "
            "was already made.",
            "Choosing multicriteria decision analysis for a call simple enough for a plain "
            "conversation, and burying the decision in scoring overhead.",
            "Not recording which method was used, so a later challenge to the decision has "
            "nothing to check it against.",
            "Letting the loudest voice in the room stand in for a method at all.",
        ),
        worked_example=(
            "Three vendors are shortlisted for the conduit installation. The choice affects "
            "cost, schedule risk, and safety record roughly equally, so the PM runs a "
            "multicriteria decision analysis scoring each vendor against those three "
            "factors with the client's stated weights, rather than picking the lowest bid "
            "outright."
        ),
        further_reading=(),
    ),
    "interpersonal_and_team_skills": TechniqueContent(
        summary=(
            "The general term for people-facing skills, like listening and influencing, a project manager uses directly."
        ),
        when_to_use=(
            "The process step depends on how people in the room behave, not just what "
            "data or document gets produced — running a workshop, resolving a "
            "disagreement, keeping a stakeholder engaged, or building a team's working "
            "relationship."
        ),
        when_to_avoid=(
            "When the situation is really a process or data problem dressed up as a people "
            "problem — 'facilitate better alignment' can be a euphemism for 'nobody wrote "
            "down the requirement,' and no amount of interpersonal skill fixes a missing "
            "artifact. Also avoid leaning on charisma or authority to push a decision "
            "through when the disagreement is substantive and needs to be resolved on the "
            "merits."
        ),
        steps=(
            "Identify which specific skill the situation calls for — several of these have "
            "their own catalog entries (conflict management, negotiation, influencing, "
            "team building) with concrete steps; use those rather than treating "
            "'interpersonal skills' as one undifferentiated activity.",
            "Read the room before acting: is this a conflict to manage, a stalled decision "
            "to facilitate, a disengaged stakeholder to re-engage, or a team that needs "
            "building?",
            "Apply the specific skill deliberately, not reactively — plan what you're going "
            "to do in the meeting or conversation before you're in it.",
            "Follow up afterward: confirm the conflict actually resolved, the decision "
            "actually stuck, the relationship actually improved, rather than assuming the "
            "interaction itself was the outcome.",
        ),
        outputs=(
            "A changed state in the people side of the project: a resolved disagreement, "
            "a facilitated decision, a re-engaged stakeholder, a team that works together "
            "more effectively.",
        ),
        pitfalls=(
            "Treating a structural or data gap as a people problem and trying to "
            "'facilitate' around it instead of fixing it.",
            "Applying the same default skill (usually negotiation, or authority) to every "
            "situation regardless of what it actually calls for.",
            "Mistaking a smooth meeting for a resolved issue — the tension resurfaces next "
            "week if it was managed rather than actually addressed.",
            "Using influence or authority to end a substantive disagreement without "
            "resolving the substance.",
        ),
        worked_example=(
            "Two leads on the retrofit disagree about sequencing the conduit and mezzanine "
            "work; the disagreement has stalled the schedule update for a week. The PM "
            "recognizes it as a conflict-management situation (not a scheduling one), "
            "pulls the two leads into a short session, has each state their concern, and "
            "gets them to a sequencing compromise neither had proposed alone."
        ),
        further_reading=(),
    ),
    "communication_methods": TechniqueContent(
        summary=(
            "Choosing how a message travels: a live back-and-forth, a message sent out, or one people retrieve on their own."
        ),
        when_to_use=(
            "Deciding, for a given message, whether it needs real-time exchange, "
            "confirmed delivery to specific people, or general availability for anyone "
            "who needs to look it up."
        ),
        when_to_avoid=(
            "Push method for anything urgent or ambiguous — a sent-but-unread status "
            "email is not the same as a confirmed handoff, and treating it as one is how "
            "urgent information sits unread. Pull method for anything time-sensitive that "
            "needs a specific person to act — nobody is obligated to go look."
        ),
        steps=(
            "Ask whether the message needs real-time back-and-forth (interactive), "
            "confirmed one-way delivery to named recipients (push), or general "
            "availability for self-service retrieval (pull).",
            "Match urgency and audience size to the method: interactive for small, urgent, "
            "or contentious exchanges; push for time-bound updates to a defined list; pull "
            "for reference material a broad or changing audience retrieves as needed.",
            "For push, confirm receipt for anything that requires action, not just delivery.",
            "For pull, make sure the audience actually knows the material exists and where "
            "to find it — a pull method nobody knows about is not a communication method, "
            "it's a filing exercise.",
        ),
        outputs=(
            "A stated method for each planned communication in the communications management plan.",
        ),
        pitfalls=(
            "Defaulting to push (email) for everything regardless of urgency or ambiguity, "
            "because it's the path of least resistance.",
            "Using pull for a decision that needed a specific person's timely action.",
            "Confusing 'I sent it' (push) with 'they received and understood it' — those "
            "are different claims.",
        ),
        worked_example=(
            "For the retrofit's weekly status, the PM uses push (a summary email) for the "
            "steering committee, pull (a shared dashboard) for the wider stakeholder list "
            "who check in occasionally, and reserves interactive (a call) for the one "
            "issue — the conduit delay — that needs real-time discussion that week."
        ),
        further_reading=("PMBOK-6 §10.1.2.5",),
    ),
    "communication_models": TechniqueContent(
        summary=(
            "Tracing how a message actually moves from one person's mind to another's, to see where it broke down."
        ),
        when_to_use=(
            "A message was sent and didn't have the intended effect, and you need to "
            "diagnose where it broke down — was it poorly encoded (jargon the receiver "
            "didn't share), lost to noise (sent during a reorg nobody was paying "
            "attention to), or delivered with no feedback loop to confirm it landed."
        ),
        when_to_avoid=(
            "As a substitute for actually sending the message — the model is a diagnostic "
            "tool for failures, not a communication method in its own right. Don't reach "
            "for it on routine, working communication that doesn't need diagnosing."
        ),
        steps=(
            "When a message failed to land, trace it through the chain: what did the "
            "sender mean, how was it encoded (words, format, jargon), what medium carried "
            "it, what noise competed with it, how did the receiver decode it, and did any "
            "feedback confirm the loop closed.",
            "Identify which link broke — often encoding (assuming shared vocabulary that "
            "wasn't shared) or the missing feedback loop.",
            "Fix that specific link for future messages of the same kind, rather than "
            "generically 'communicating more.'",
        ),
        outputs=(
            "A diagnosis of where a communication broke down, and a specific change to how "
            "future messages of that kind are sent.",
        ),
        pitfalls=(
            "Treating every miscommunication as a receiver problem ('they didn't read it') "
            "when the failure was in encoding or medium.",
            "Skipping the feedback step entirely and having no way to know a message "
            "landed until the resulting confusion shows up downstream.",
            "Using the model as an excuse rather than a diagnostic — naming 'noise' without "
            "identifying what the actual noise was.",
        ),
        worked_example=(
            "A subcontractor keeps missing a submittal deadline the PM is sure was "
            "communicated clearly. Walking it through the model, she finds the deadline "
            "was buried in paragraph four of a long email (encoding failure) sent the same "
            "week the sub was mobilizing a new crew (noise), with no reply requested "
            "(no feedback loop). She switches to a one-line subject-line deadline with a "
            "required acknowledgment."
        ),
        further_reading=("PMBOK-6 §10.1.2.4",),
    ),
    "communication_skills": TechniqueContent(
        summary=(
            "The personal abilities, like clarity, tone, and listening, that make a specific communication actually land."
        ),
        when_to_use=(
            "Preparing any message where getting it right matters — a stakeholder "
            "briefing, a difficult status update, a negotiation — and the risk is in how "
            "it's delivered, not just what channel carries it."
        ),
        when_to_avoid=(
            "As a catch-all fix for a problem that's actually structural — polishing the "
            "delivery of a message that contains bad or incomplete information doesn't fix "
            "the information. Don't over-invest skill-building effort in a channel that's "
            "wrong for the message regardless of how well it's delivered."
        ),
        steps=(
            "Identify the audience and what they need from the message — a decision, "
            "reassurance, a warning — before drafting it.",
            "Match tone and register to that audience: an executive summary reads "
            "differently from a field-crew briefing on the same fact.",
            "For live delivery, prepare for nonverbal cues (yours and theirs) as "
            "deliberately as you prepare the words.",
            "Practice active listening in the response — confirm what you heard back to "
            "the other party before reacting to it.",
            "After a high-stakes communication, check whether it landed as intended, not "
            "just whether it was delivered.",
        ),
        outputs=("A message delivered in a form and tone the intended audience can act on.",),
        pitfalls=(
            "Using the same register for every audience — a status update written for "
            "executives is unreadable to a field crew and vice versa.",
            "Listening to respond instead of listening to understand, especially in "
            "conflict-adjacent conversations.",
            "Treating skill in delivery as a substitute for substance in the message.",
        ),
        worked_example=(
            "The PM needs to tell both the client's executive sponsor and the site "
            "foreman about the two-week conduit delay. For the sponsor she leads with "
            "impact and recovery plan in three sentences; for the foreman she leads with "
            "the specific sequencing change that affects tomorrow's crew assignment. Same "
            "fact, different message."
        ),
        further_reading=("PMBOK-6 §10.2.2.3",),
    ),
    "communication_technology": TechniqueContent(
        summary=(
            "Choosing the medium a message travels over, based on urgency, privacy, audience size, and how much tone matters."
        ),
        when_to_use=(
            "Choosing, for a specific message, which physical or digital channel to use — "
            "distinct from communication methods (the traffic pattern: push, pull, "
            "interactive), which can each be carried over more than one technology."
        ),
        when_to_avoid=(
            "Defaulting to whichever tool is open on your screen rather than the one that "
            "fits the message — a sensitive conversation over chat because it was faster "
            "to type than to call loses the tone and nonverbal signal that made the "
            "difference. Also avoid a heavier or more formal technology than the message "
            "and audience actually need."
        ),
        steps=(
            "Assess the message's urgency, sensitivity, and how much it depends on tone or "
            "visual cues.",
            "Check what the audience can actually access — a video call assumes bandwidth "
            "and availability a field crew may not have.",
            "Pick the technology that matches: voice or video for anything sensitive or "
            "ambiguous, written for anything that needs a durable record, a shared "
            "document for anything collaborative and evolving.",
            "Confirm the audience actually has access to the chosen technology before "
            "relying on it for something time-critical.",
        ),
        outputs=("A stated channel for each planned communication, matched to its nature.",),
        pitfalls=(
            "Delivering a sensitive message over a low-bandwidth channel (chat, email) to "
            "avoid an uncomfortable conversation, and losing the tone that would have "
            "prevented a misunderstanding.",
            "Assuming universal access to a technology (video conferencing, a specific "
            "app) that part of the audience can't actually reach.",
            "Using a written channel for something that needed to be discussed, not just "
            "announced.",
        ),
        worked_example=(
            "Rather than emailing the two-week conduit delay to the client, the PM calls "
            "the sponsor directly — the news needs tone and room for questions a written "
            "note can't carry — then follows up in writing to make the revised date and "
            "recovery plan a durable record."
        ),
        further_reading=("PMBOK-6 §10.1.2.3",),
    ),
    "meetings": TechniqueContent(
        summary=(
            "A deliberately convened session where specific people decide something or share status together."
        ),
        when_to_use=(
            "The purpose genuinely needs synchronous, multi-party interaction — a "
            "decision that needs several people's input at once, a problem that needs "
            "real-time back-and-forth to work through, or status that needs discussion, "
            "not just reporting."
        ),
        when_to_avoid=(
            "When the purpose is pure information transfer that a written update would "
            "carry just as well — a status meeting with no decision on the agenda is a "
            "push communication wearing a meeting's clothes, and it costs every "
            "attendee's calendar to deliver what an email would have. Also avoid convening "
            "a meeting before you know what decision it needs to produce."
        ),
        steps=(
            "Set a specific purpose and a short agenda before sending the invite — 'sync "
            "up' is not a purpose.",
            "Invite only the people whose input or authority the purpose actually needs.",
            "Start by restating the purpose and what decision or output the meeting needs "
            "to leave with.",
            "Capture decisions and action items as they're made, not from memory afterward.",
            "End by confirming who owns each action item and by when.",
            "Send the notes and action items to attendees and anyone who needed the "
            "outcome but wasn't in the room.",
        ),
        outputs=("Meeting notes: decisions made, action items with owners and dates.",),
        pitfalls=(
            "Convening a meeting with no clear decision or output, and calling status "
            "reporting a substitute for one.",
            "Inviting everyone who might be interested instead of everyone whose input is "
            "needed, so the meeting can't actually decide anything without a follow-up.",
            "No agenda, so the group discovers the purpose live and burns the first ten "
            "minutes finding it.",
            "Decisions made verbally with nothing captured, so the same debate recurs next "
            "meeting.",
        ),
        worked_example=(
            "Instead of a recurring one-hour status call with the full project team, the "
            "PM cancels it and sends a written weekly update. She keeps a thirty-minute "
            "meeting with just the four leads whose sequencing decisions actually need "
            "real-time negotiation, with a one-line agenda: resolve the conduit-versus-"
            "mezzanine sequencing question."
        ),
        further_reading=("PMBOK-6 §10.2.2.7",),
    ),
    "project_management_information_system": TechniqueContent(
        summary=("The tools that hold a project's working data and make it usable by the team."),
        when_to_use=(
            "The project needs a durable, shared record of its data — schedule, cost, "
            "decisions, communications — that's queryable and consistent rather than "
            "scattered across individual inboxes and local files."
        ),
        when_to_avoid=(
            "Standing up or configuring more system than the project's size and team "
            "justify — a small team of four doesn't need the reporting depth a "
            "hundred-person program does, and the setup and maintenance cost is real. Also "
            "avoid treating the system as a substitute for the judgment calls (which "
            "technique to apply, how to interpret a variance) it's meant to record, not "
            "make."
        ),
        steps=(
            "Identify what the project actually needs recorded and retrieved: schedule "
            "state, cost data, decisions, communications, technique outputs.",
            "Use the system consistently — a PMIS with half the team logging elsewhere is "
            "not a single source of truth, it's two inconsistent ones.",
            "Keep entries attributable and dated so a later reader can tell what was known "
            "when a decision was made.",
            "Generate reports and dashboards from the system's own data rather than a "
            "manually reassembled copy of it, so the report and the record can't drift "
            "apart.",
        ),
        outputs=(
            "A queryable, shared project record — the schedule, cost data, decisions, and "
            "reports the rest of the project's work draws on.",
        ),
        pitfalls=(
            "Partial adoption — some data lives in the system, some in someone's personal "
            "notes, and nobody can tell which copy is current.",
            "Treating the system's output as automatically correct because it came from "
            "the system, rather than checking the inputs that produced it.",
            "Building manual reports alongside the system instead of generating them from "
            "it, so the two silently diverge over time.",
        ),
        worked_example=(
            "The retrofit team logs technique applications, decisions, and status directly "
            "in Driftless rather than in a parallel spreadsheet. When the sponsor asks for "
            "a status report mid-month, the PM generates it straight from the recorded "
            "data instead of reconstructing the month from memory and email."
        ),
        further_reading=(),
    ),
    "communication_requirements_analysis": TechniqueContent(
        summary=(
            "Working out who needs which information, in what form, and how often, before choosing a channel for any of it."
        ),
        when_to_use=(
            "At the start of planning communications, before picking any "
            "method or technology: for each stakeholder, determine what they "
            "need to know, why, and how often, from the stakeholder register "
            "and the project's organizational structure and reporting lines."
        ),
        when_to_avoid=(
            "Don't skip straight to a channel or a cadence 'because that's "
            "what the last project used' — a communications plan built "
            "without naming the actual information need behind each line "
            "tends to over-communicate to people who don't need it and "
            "under-communicate to the few who do."
        ),
        steps=(
            "List each stakeholder or group from the register with their "
            "role, interest, and influence.",
            "For each, name the specific information they need and why — a "
            "decision they make, a risk they own, or an approval only they "
            "can give.",
            "Feed the result — who needs what, and how often — into the "
            "communications management plan as the requirement the rest of "
            "the plan's methods and technology choices have to satisfy.",
        ),
        outputs=(
            "A stated information need per stakeholder or group, feeding the "
            "communications management plan.",
        ),
        pitfalls=(
            "Copying a prior project's stakeholder list instead of analyzing "
            "this project's own reporting lines and decision points.",
            "Naming a channel or frequency before naming the actual "
            "information need it is supposed to satisfy.",
        ),
        worked_example=(
            "For the retrofit, the site foreman needs daily sequencing "
            "detail, while the client sponsor needs only a weekly summary "
            "with a decision flagged when one is pending."
        ),
        further_reading=("PMBOK-6 §10.1.2.2",),
    ),
    "project_reporting": TechniqueContent(
        summary=(
            "Collecting and distributing project status and progress in the format each audience actually needs."
        ),
        when_to_use=(
            "Whenever work performance information has to reach an audience "
            "as a report: a status update, a dashboard, a forecast summary — "
            "anything that turns collected performance data into something a "
            "reader can act on without reassembling it themselves."
        ),
        when_to_avoid=(
            "As a substitute for a conversation a report can't carry — a "
            "report can state that a decision is needed, but the decision "
            "itself usually still needs a discussion. Don't bury the one "
            "figure or flag a reader needs inside a report so dense they "
            "have to hunt for it."
        ),
        steps=(
            "Pull current status and progress from the project's own "
            "recorded data rather than a manually reassembled copy.",
            "Match the report's format and depth to the audience identified "
            "in the communications management plan.",
            "State clearly what, if anything, needs a decision or action "
            "from the reader, rather than leaving them to infer it.",
        ),
        outputs=("A distributed status or progress report matched to its audience's needs.",),
        pitfalls=(
            "Manually reassembling a report from scattered sources instead "
            "of generating it from the project's own record.",
            "One report format for every audience, so executives wade "
            "through field-level detail and the field team gets none.",
        ),
        worked_example=(
            "The PM generates the retrofit's weekly report straight from "
            "the recorded schedule and cost data, trims it to the three "
            "lines the steering committee cares about, and flags the "
            "conduit delay as needing a go/no-go decision this week."
        ),
        further_reading=("PMBOK-6 §10.2.2.5",),
    ),
}
