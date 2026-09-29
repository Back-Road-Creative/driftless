"""Technique explanations for the procurement family (tt.FAMILIES["procurement"]).

A note on scope before the entries themselves: Driftless's procurement support
starts at signature. The only record this app keeps is ``ProcurementAgreement``
(``driftless/models/procurement.py``) — vendor, description, amount, status and
a start/end window on one signed contract. There is no make-or-buy record, no
statement of work, no solicitation, no stored bid or proposal, and no closeout
workflow. Several of the techniques below describe work that happens entirely
before a ``ProcurementAgreement`` row would exist, or that this app has nowhere
to record the result of; each entry says so rather than implying a module that
is not there.

Procurement guidance is also frequently written for public-sector formal
tendering and then applied unmodified to a two-person engagement, which makes
it wrong at both ends of the scale. Each entry below says what size of
purchase it actually fits.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "procurement"

CONTENT: dict[str, TechniqueContent] = {
    "make_or_buy_analysis": TechniqueContent(
        summary=(
            "Comparing doing work yourself against buying it from an outside vendor before deciding."
        ),
        when_to_use=(
            "Any time a capability gap shows up on the project and there is a real choice "
            "between building it internally and contracting it out — a new deliverable, a "
            "specialised skill nobody on the team has, a piece of equipment needed for one "
            "phase. Do it before you talk to a single vendor, not after, so the comparison "
            "isn't anchored by whatever quote arrived first."
        ),
        when_to_avoid=(
            "Skip it when there genuinely is no internal option — you have no one who could do "
            "the work even given time and budget, so there is nothing to compare against. Also "
            "skip a full write-up for trivial purchases (a software license, a rented van): the "
            "analysis costs more than the decision is worth. Running it for a $400 rental is "
            "wasted effort, and skipping it for a decision to build in-house capability that "
            "will outlast this one project is the same mistake in the other direction."
        ),
        steps=(
            "Write down the capability gap in one sentence: what has to get done, and by when.",
            "Price the build option fully: not just wages, but training time, tools or "
            "equipment you would have to acquire, and the ongoing cost of maintaining the "
            "capability after this project ends.",
            "Price the buy option fully: not just the vendor's quote, but the cost of writing "
            "the contract, managing the vendor day to day, and the risk of the vendor failing "
            "or leaving mid-project.",
            "Ask what happens to the capability when the contract or the project ends — a "
            "bought capability disappears with the vendor; a built one stays with you, for "
            "better or worse.",
            "Ask whether this is a capability you should be able to do yourself as a matter of "
            "strategy, independent of which option is cheaper this time.",
            "Decide, and write the reason down alongside the number — the number without the "
            "reason is unreadable in six months.",
        ),
        outputs=(
            "A short written comparison with a decision and its reasoning",
            "A decision on whether to proceed to a purchase at all",
        ),
        pitfalls=(
            "Comparing only the sticker prices — the vendor's quote against the loaded cost of "
            "an employee's day rate — while ignoring vendor management overhead and the strategic "
            "cost of never building the capability yourself.",
            "Treating the analysis as a formality that follows a decision already made, rather "
            "than something that could actually change the answer.",
            "Running a full multi-page analysis for a purchase too small to justify the time it "
            "takes to write.",
            "Never revisiting the decision — a make-or-buy call made once at kickoff can go "
            "stale by the time the work is actually needed.",
        ),
        worked_example=(
            "A small architecture firm needs a project scheduling tool integrated with its "
            "billing system. Buying an off-the-shelf integration from a vendor quotes at "
            "$3,000, versus an estimated $4,500 in staff time to build it in-house. Price alone "
            "says buy. But the firm's billing system is custom and central to every project it "
            "runs, and the vendor's fee is a one-time integration only — every future billing "
            "system change will need the vendor's paid involvement again, indefinitely. The firm "
            "decides to build it in-house at the higher upfront cost, because the alternative is "
            "years of recurring vendor dependency on a system core to the business."
        ),
        further_reading=("PMBOK-6 §12.1.2",),
    ),
    "source_selection_analysis": TechniqueContent(
        summary=("Choosing how you will pick a vendor before you start looking for one."),
        when_to_use=(
            "Any time you are about to seek more than one vendor for a purchase of real "
            "consequence — enough money or enough risk that the method of choosing matters. "
            "Decide the method before requesting proposals, so the criteria aren't quietly "
            "reshaped by whoever happens to respond first."
        ),
        when_to_avoid=(
            "For a small, low-risk purchase, naming a formal selection method is theatre — pick "
            "a vendor you trust and move on. It is also the wrong technique to reach for once "
            "proposals are already in hand: at that point you are evaluating, not selecting a "
            "method, and pretending otherwise lets the method get reverse-engineered to fit "
            "whichever proposal you already like."
        ),
        steps=(
            "Identify what actually varies across likely vendors for this purchase: price only, "
            "qualifications, quality, or some mix.",
            "Pick the method that fits: lowest cost for a commodity purchase where quality is "
            "uniform; qualifications-only when the work is too specialised to price-compare "
            "sensibly; quality-and-cost-based when both matter and you can weigh them; sole "
            "source when only one vendor can plausibly do the work and a competition would be "
            "theatre, not diligence.",
            "Record the chosen method and the reason for it before any vendor is contacted.",
            "Use that method to shape what you ask vendors for — a quality-and-cost method needs "
            "a proposal, a lowest-cost method just needs a price.",
        ),
        outputs=("A named selection method and the reason it fits this purchase",),
        pitfalls=(
            "Choosing 'lowest cost' for work where quality varies enormously between vendors, "
            "then being surprised when the cheapest bidder delivers the least.",
            "Declaring sole source out of convenience rather than because only one vendor can "
            "actually do the work — sole source is a finding, not a shortcut.",
            "Picking the method after seeing who is available, so the method is really just a "
            "justification for a vendor already chosen informally.",
        ),
        worked_example=(
            "A nonprofit needs a video producer for a single fundraising event. Because the "
            "creative quality of the final video matters more than shaving a few hundred dollars "
            "off the price, the project lead selects a quality-and-cost-based method before "
            "reaching out to anyone, rather than defaulting to lowest cost, which would optimise "
            "for the wrong thing."
        ),
        further_reading=("PMBOK-6 §12.1.2",),
    ),
    "bidder_conferences": TechniqueContent(
        summary=(
            "A meeting where every prospective vendor asks questions before proposals are due, so everyone hears the same answers."
        ),
        when_to_use=(
            "When you are asking more than one vendor to bid on the same substantial piece of "
            "work and the requirements are complex enough that vendors will have real questions "
            "— a construction bid, a multi-vendor RFP for a significant system. It only earns "
            "its cost when there is enough at stake, and enough vendors, to make fairness worth "
            "formalising."
        ),
        when_to_avoid=(
            "For a small engagement — one or two vendors, a modest budget, straightforward "
            "requirements — a bidder conference is disproportionate: it costs everyone's time to "
            "formalise a conversation that a phone call would settle. Answer questions directly "
            "instead, and document the answer if more than one vendor is in play."
        ),
        steps=(
            "Set a single date and invite every prospective bidder, making clear attendance is "
            "the only way to get direct answers to their questions.",
            "Collect and answer every substantive question in the room, not in side channels.",
            "Write up the questions and answers and send the same document to every attendee, "
            "whether or not they asked anything themselves.",
            "Treat that written record, not the meeting itself, as the binding clarification of "
            "requirements.",
        ),
        outputs=("A written question-and-answer record distributed identically to every bidder",),
        pitfalls=(
            "Answering a question by phone or email to one bidder afterward without sending the "
            "same answer to everyone else — a single side conversation defeats the entire point "
            "of holding the conference.",
            "Treating verbal answers given in the room as final without writing them down, so "
            "bidders leave with different memories of what was said.",
            "Running one for a purchase small enough that the formality outweighs any benefit.",
        ),
        worked_example=(
            "A city library district puts a new HVAC system out to bid among five contractors. "
            "At the mandatory pre-bid conference, one contractor asks whether asbestos abatement "
            "is included in scope. The facilities manager answers in the room and later emails "
            "the same answer, verbatim, to all five contractors — not just the one who asked — "
            "so every bid is priced against the same understanding of scope."
        ),
        further_reading=("PMBOK-6 §12.2.2",),
    ),
    "advertising": TechniqueContent(
        summary=(
            "Publishing a notice that a project is seeking vendors, so the field of respondents "
            "isn't limited to whoever the buyer already happens to know."
        ),
        when_to_use=(
            "When the purchase is significant enough, or specialised enough, that casting a "
            "wider net than your existing contacts is likely to turn up a better or cheaper "
            "vendor — a public-sector contract where advertising may also be a legal "
            "requirement, or a large private purchase where the usual short list isn't enough."
        ),
        when_to_avoid=(
            "For most small-project purchases, advertising is overkill: you already know two or "
            "three vendors capable of the work, and running a public notice adds delay and "
            "response volume without adding a real candidate. Go straight to the vendors you "
            "know instead."
        ),
        steps=(
            "Decide the purchase is large or specialised enough that unknown vendors are worth "
            "surfacing.",
            "Write a notice that describes the work clearly enough for a qualified vendor to "
            "self-select, without disclosing so much detail that it advantages whoever wrote it.",
            "Publish through channels the relevant vendor market actually watches — a trade "
            "journal, an industry board, a government procurement portal — not just a general "
            "website.",
            "Set a clear response deadline and a single point of contact for questions.",
        ),
        outputs=("A published notice and a resulting list of vendors who responded to it",),
        pitfalls=(
            "Advertising broadly for a purchase small enough that the response volume becomes "
            "its own burden to sort through.",
            "Writing the notice so vaguely that unqualified vendors respond in bulk, or so "
            "narrowly that it reads as written for one vendor already chosen.",
        ),
        worked_example=(
            "A regional transit authority needs a specialised bridge inspection contractor and "
            "has no existing relationship with one. It publishes a notice in a civil engineering "
            "trade journal rather than relying on the two firms its staff happen to have worked "
            "with before, and receives bids from four qualified firms it had never contacted."
        ),
        further_reading=("PMBOK-6 §12.2.2",),
    ),
    "proposal_evaluation": TechniqueContent(
        summary=(
            "Scoring the proposals actually received against a set of criteria to compare them fairly."
        ),
        when_to_use=(
            "Whenever more than one vendor has submitted a real proposal and you need a "
            "defensible way to compare them — especially when a quality-and-cost-based selection "
            "method was chosen and more than price is on the table."
        ),
        when_to_avoid=(
            "Don't build formal weighted scoring for a purchase where lowest cost was already "
            "the chosen method, or where only one vendor responded — there is nothing to "
            "compare. And never let the criteria or their weights get set after proposals are "
            "already in hand: weights chosen after seeing the submissions aren't evaluation, "
            "they're justification for an answer already picked."
        ),
        steps=(
            "Set the evaluation criteria and their weights before opening a single proposal — "
            "write them down and date them.",
            "Score each proposal against the same criteria, by the same people, using the same "
            "scale.",
            "Total the scores and rank the proposals; note any large disagreement between "
            "evaluators as a signal to discuss, not to average away silently.",
            "Document the result, including proposals that scored poorly and why — a rejected "
            "vendor's file is as important as the winner's.",
        ),
        outputs=("A scored, ranked comparison of the proposals received against fixed criteria",),
        pitfalls=(
            "Setting or adjusting the weighting after the proposals are read, so the scoring "
            "quietly reverse-engineers a decision that was really made on gut feel.",
            "Scoring criteria that sound objective but are really proxies for 'the vendor we "
            "already like' — years in business, or a familiar company name.",
            "Letting one evaluator's score dominate without anyone else's input being recorded "
            "or reconciled.",
        ),
        worked_example=(
            "A small manufacturer requests proposals from three packaging vendors and sets "
            "weighted criteria in advance — 40% price, 40% sample quality, 20% lead time. After "
            "opening the proposals, the evaluator notices the incumbent vendor scores lowest on "
            "price but is the personal favourite of the buying committee, and floats reweighting "
            "toward relationship history. The evaluation lead rejects the change: the criteria "
            "were fixed before proposals were opened, and changing them now would be scoring "
            "backward from a preference, not forward from evidence."
        ),
        further_reading=("PMBOK-6 §12.2.2",),
    ),
    "claims_administration": TechniqueContent(
        summary=(
            "Handling a disputed change to a contract by following the contract's own rules for settling disagreements."
        ),
        when_to_use=(
            "As soon as a change to a signed agreement is disputed — a vendor believes extra "
            "work was requested outside the original scope, or a buyer believes work billed for "
            "was never properly authorised. Open the claim process the moment the disagreement "
            "is identified, not after weeks of arguing informally have already hardened both "
            "sides' positions."
        ),
        when_to_avoid=(
            "It is not for routine change requests both sides agree on — that's a normal "
            "contract amendment, not a claim. Reaching for formal claims administration over "
            "every minor scope tweak turns a working relationship adversarial faster than it "
            "needs to."
        ),
        steps=(
            "Identify the disputed change precisely: what was done, who directed it, and what is "
            "being asked for as a result.",
            "Check what the contract itself says about how disputes are resolved — negotiation, "
            "mediation, arbitration, or litigation — and follow that route rather than an "
            "informal one, however reasonable the informal one feels.",
            "Document the change and the dispute in writing, even if it started as a verbal "
            "instruction — especially if it started as a verbal instruction.",
            "Track the claim to resolution and record the outcome against the agreement, so the "
            "final record reflects what was actually agreed, not just what was originally "
            "signed.",
        ),
        outputs=(
            "A documented, resolved claim and, if it changes the agreement's terms, an updated "
            "record of the agreement",
        ),
        pitfalls=(
            "Performing disputed work on a verbal instruction and arguing about payment for it "
            "only after the fact — by then there is no record of what was actually asked for, "
            "and the dispute becomes about memory instead of fact.",
            "Skipping the contract's own dispute-resolution process because one side is "
            "confident they're right — being right does not substitute for following the route "
            "the contract specifies, and skipping it can itself weaken your position later.",
            "Letting an unresolved claim sit undocumented while work continues, so the eventual "
            "dispute is larger and harder to untangle than it needed to be.",
        ),
        worked_example=(
            "A vendor renovating a retail space is told by the site manager, over the phone, to "
            "add reinforced shelving not in the original scope. The vendor does the work and "
            "invoices for it; the buyer refuses to pay, saying the site manager had no authority "
            "to approve extra spend. Because neither side confirmed the instruction in writing "
            "at the time, resolving it now requires reconstructing a phone call from memory. The "
            "contract specifies mediation before either party can pursue further action, and "
            "both sides are contractually bound to try that route first, whatever they believe "
            "about who is at fault."
        ),
        further_reading=("PMBOK-6 §12.3.2",),
    ),
    "inspections_and_audits": TechniqueContent(
        summary=(
            "Checking a vendor's finished work and its working process against what the contract requires."
        ),
        when_to_use=(
            "On any active agreement where the buyer needs assurance beyond the vendor's own "
            "word before payment or acceptance — physical deliverables that can be inspected, or "
            "compliance obligations (safety, security, regulatory) that need periodic auditing. "
            "Scale the frequency and formality to the contract's value and risk."
        ),
        when_to_avoid=(
            "For a low-value, low-risk agreement — a short engagement with an established, "
            "trusted vendor — formal scheduled inspections and audits cost more in vendor "
            "relationship friction and admin time than the risk they're guarding against "
            "justifies. A simple deliverable review at completion is enough."
        ),
        steps=(
            "Decide, at the time the agreement is signed, what will be inspected or audited and "
            "on what schedule — deciding this after the fact invites disputes about fairness.",
            "Inspect deliverables against the contract's stated requirements, not against an "
            "informal expectation that was never written down.",
            "Audit process or compliance items separately from deliverable inspection — a "
            "deliverable can pass inspection while the process that produced it violates the "
            "contract.",
            "Record findings against the agreement and follow up on anything that fails, through "
            "the agreement's own remedy or dispute process rather than an ad hoc one.",
        ),
        outputs=(
            "A record of inspection or audit findings tied to the agreement, including any "
            "failures and how they were followed up",
        ),
        pitfalls=(
            "Only ever inspecting the final deliverable, missing a process failure early enough "
            "to have been correctable — an audit is what catches that, not another inspection.",
            "Treating a passed inspection as proof the whole engagement is healthy, when the "
            "underlying process an audit would have caught is quietly non-compliant.",
            "Scheduling inspections so infrequently, relative to the contract's risk, that "
            "problems are only found once they're expensive to fix.",
        ),
        worked_example=(
            "A hospital contracts a vendor to sterilise and deliver surgical instrument trays "
            "weekly. Inspecting each delivered tray confirms the instruments themselves are "
            "clean and complete, but a quarterly process audit of the vendor's sterilisation log "
            "is what catches that one autoclave has been running below the required temperature "
            "for two weeks — a defect no visual inspection of the finished trays would have "
            "revealed."
        ),
        further_reading=("PMBOK-6 §12.3.2",),
    ),
    "procurement_performance_reviews": TechniqueContent(
        summary=(
            "Checking, at regular intervals, how a live contract is actually performing against its terms."
        ),
        when_to_use=(
            "On any agreement that runs long enough to have a meaningful trajectory: multi-month "
            "retainers, phased deliverables, or any contract where cost or schedule performance "
            "could drift gradually rather than fail all at once. Reviewing at fixed intervals "
            "catches drift a single end-of-contract check would miss."
        ),
        when_to_avoid=(
            "For a short, single-deliverable engagement there usually isn't enough runway for a "
            "periodic review to add anything a straightforward acceptance check at completion "
            "wouldn't already catch — don't build a review cadence around a contract that will "
            "be finished before the second review would happen."
        ),
        steps=(
            "Set the review interval when the agreement starts, matched to how long the "
            "agreement runs — monthly for a year-long retainer, not for a six-week project.",
            "At each review, compare actual cost, schedule, and delivered scope against the "
            "agreement's terms — not against a general sense of how things are going.",
            "Flag drift while it's still small: a vendor running consistently late or "
            "consistently over budget is a pattern worth raising at the second occurrence, not "
            "the fifth.",
            "Record the review outcome against the agreement so a pattern across reviews is "
            "visible, not just each review's isolated snapshot.",
        ),
        outputs=(
            "A dated record of the agreement's cost, schedule and scope performance at each "
            "review point",
        ),
        pitfalls=(
            "Only reviewing at the contract's natural milestones, which are often exactly when "
            "the vendor has something to show — missing the drift that happens between them.",
            "Treating a single bad review as decisive, or a single good one as clearing every "
            "earlier concern, instead of reading the trend across several reviews.",
            "Running a heavy review process on a short contract that will be over before a "
            "second data point exists.",
        ),
        worked_example=(
            "A twelve-month IT support retainer is reviewed monthly against its service-level "
            "terms. The first two reviews look fine individually, but by the third, response "
            "times have crept from the contracted four hours to just over six each month — a "
            "trend invisible from any single review, but obvious once the three are read "
            "together, prompting a conversation with the vendor well before the pattern became a "
            "contractual breach."
        ),
        further_reading=("PMBOK-6 §12.3.2",),
    ),
}
