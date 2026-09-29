"""Technique explanations for the scope family (tt.FAMILIES["scope"]).

These are the most hands-on techniques in the catalog: a reader should be
able to finish a technique's ``steps`` and go do the thing that afternoon.
``decomposition`` carries the most weight, since it is how a work breakdown
structure actually gets built and where scope work most often goes wrong.
"""

from __future__ import annotations

from driftless.pmbok.technique_content import TechniqueContent

FAMILY = "scope"

CONTENT: dict[str, TechniqueContent] = {
    "benchmarking": TechniqueContent(
        summary=(
            "Comparing your project against similar organizations or projects to find a useful target, a gap, or a practice worth copying."
        ),
        when_to_use=(
            "Use it early in requirements work when you need an external anchor: "
            "a competitor's feature set, an industry cycle-time norm, a peer "
            "team's staffing ratio. It is especially useful when stakeholders "
            "disagree about what 'good' looks like and an outside reference can "
            "settle the argument better than another round of opinions."
        ),
        when_to_avoid=(
            "Skip it when no genuinely comparable organization or project exists "
            "-- a forced comparison to a dissimilar peer produces a number that "
            "looks authoritative and is not. Also skip it as a substitute for "
            "talking to your own stakeholders: benchmarking tells you what others "
            "do, not what this project's sponsor actually needs. Treat it as one "
            "input to Collect Requirements, never the whole exercise."
        ),
        steps=(
            "Name the specific attribute you're benchmarking (cost per unit, "
            "cycle time, feature set, defect rate) -- not 'how are we doing', "
            "a single measurable thing.",
            "Pick two or three genuinely comparable organizations or projects; "
            "document why each is comparable so the comparison survives "
            "scrutiny later.",
            "Gather the comparison data from public sources, industry reports, "
            "or direct contacts -- note the collection date, since these "
            "numbers age.",
            "Line your own planned or current value up against each benchmark "
            "and note the gap in both directions (you may already beat some of "
            "them).",
            "Turn each meaningful gap into a candidate requirement or a target "
            "metric, and hand it to Collect Requirements or Define Scope for "
            "the stakeholders to accept, adjust, or reject.",
        ),
        outputs=(
            "A short comparison table (attribute, your value, each peer's value, gap).",
            "One or more candidate requirements or targets derived from the gaps.",
        ),
        pitfalls=(
            "Comparing against a peer that only looks similar (same industry "
            "label, wildly different scale or context) and treating the gap as "
            "meaningful.",
            "Using stale data without checking it -- a two-year-old industry "
            "figure quoted as current.",
            "Stopping at the comparison table and never converting a gap into "
            "an actual requirement someone owns.",
        ),
        worked_example=(
            "A mid-size clinic network is scoping a new patient portal. The PM "
            "benchmarks average appointment-booking time against two similarly "
            "sized clinic networks that publish their support metrics: 90 "
            "seconds and 110 seconds median, against the current 4 minutes on "
            "the clinic's existing phone-based process. That gap becomes a "
            "candidate requirement -- 'online booking completes in under 2 "
            "minutes for a returning patient' -- which goes into requirements "
            "collection for the sponsor to confirm."
        ),
        further_reading=("PMBOK-6 §5.2.2.2",),
    ),
    "context_diagram": TechniqueContent(
        summary=(
            "One picture of a system as a box, showing everything outside it that it touches."
        ),
        when_to_use=(
            "Draw one when 'what's in scope' has become an argument nobody can "
            "resolve in words -- a stakeholder keeps assuming an integration or "
            "a user group is included that another stakeholder assumed was out. "
            "It is also useful early, before requirements gathering starts, to "
            "give everyone in the room the same starting picture of the system's "
            "edges."
        ),
        when_to_avoid=(
            "Don't reach for it on a project with no external interfaces or "
            "actors worth drawing -- a single-team internal process change gets "
            "nothing from a box-and-arrows diagram that a sentence didn't "
            "already say. And don't let it substitute for detailed requirements: "
            "a context diagram fixes the boundary, not the behavior inside it."
        ),
        steps=(
            "Draw one box in the center labeled with the product or system "
            "under scope -- not a business unit, the thing being built.",
            "Around it, draw a box for every external actor (user role, "
            "external system, other internal system this one talks to) that "
            "sends or receives something from it.",
            "Draw one labeled arrow per interaction, naming what crosses the "
            "boundary (an order, a status update, a login credential) -- not "
            "just 'data'.",
            "Walk the diagram with the stakeholders who disagreed about scope "
            "and ask each one, out loud, to point at what's missing or what "
            "shouldn't be there.",
            "Revise until nobody in the room objects, then treat every box and "
            "arrow as something Define Scope has to explicitly include or "
            "exclude.",
        ),
        outputs=(
            "A one-page context diagram naming the system, its external actors, "
            "and every labeled interaction between them.",
            "An explicit, stakeholder-agreed scope boundary to carry into the scope statement.",
        ),
        pitfalls=(
            "Drawing the internal architecture instead of the boundary -- the "
            "diagram balloons into a design document nobody can review in a "
            "meeting.",
            "Leaving an interaction unlabeled ('data flows here') so the "
            "diagram settles nothing when the same argument comes back up.",
            "Building it alone and circulating it for sign-off instead of "
            "walking it live with the people who disagreed -- the value is in "
            "the room reaction, not the artifact.",
        ),
        worked_example=(
            "A logistics company is scoping a new dispatch system. Two "
            "stakeholders disagree over email about whether the driver mobile "
            "app is 'in' this project or a separate one. The PM draws a context "
            "diagram: dispatch system in the center, boxes for dispatcher, "
            "driver app, the existing billing system, and the customer "
            "notification service, with a labeled arrow from dispatch to driver "
            "app for 'assigned route'. Walking it in a 20-minute working "
            "session, both stakeholders agree the driver app is a consumer of "
            "this system's output but its own project -- settled in the room, "
            "not in another email thread."
        ),
        further_reading=("PMBOK-6 §5.2.2.7",),
    ),
    "decomposition": TechniqueContent(
        summary=(
            "Splitting project work into progressively smaller pieces until each is small enough to plan and track."
        ),
        when_to_use=(
            "Use it once scope is defined and you need to turn 'what we're "
            "delivering' into 'what work that requires' -- creating the WBS, "
            "or re-decomposing a deliverable that turned out to be too coarse "
            "to estimate or assign to one owner."
        ),
        when_to_avoid=(
            "Don't decompose past the point a work package can be usefully "
            "estimated and assigned -- decomposing every deliverable down to "
            "hour-level tasks up front produces a WBS nobody maintains and that "
            "goes stale the first week. For work far enough out that its detail "
            "genuinely isn't knowable yet, decompose only the near-term "
            "deliverables now and leave the rest as a single placeholder "
            "package to break down later (rolling wave), rather than guessing "
            "at detail you'll just rewrite."
        ),
        steps=(
            "Start from the accepted scope statement and the deliverables it "
            "names -- decomposition subdivides deliverables, not the "
            "org chart and not a task list you already have in your head.",
            "Identify the major deliverables (or, on a driftless-planned "
            "project without a WBS, the workstreams) and break each one into "
            "its component deliverables one level at a time.",
            "Keep going until a component deliverable is small enough that one "
            "task -- or a short, ownable set of tasks -- can produce it and one "
            "person can be accountable for it.",
            "Name each level by the deliverable it produces ('Payment "
            "integration tested', not 'Backend team'), and verify with the "
            "team that does the work that the lowest level is estimable.",
            "Since driftless has no dedicated WBS node today, record the "
            "decomposition as tasks nested under the workstream (or project) "
            "the deliverable belongs to, with the deliverable name as the "
            "workstream or task title -- the hierarchy the reader has is "
            "project / workstream / task, and decomposition's job is to make "
            "sure each task in it is a deliverable-sized piece of work, not an "
            "activity fragment.",
        ),
        outputs=(
            "A hierarchy of deliverables broken down to work-package level "
            "(in driftless: workstreams and tasks named after what they "
            "produce).",
            "A set of work packages each small enough for one owner to "
            "estimate and be accountable for.",
        ),
        pitfalls=(
            "Decomposing by organizational team ('Frontend team', 'DBA team') "
            "instead of by deliverable -- the breakdown mirrors the org chart, "
            "not the product, and two teams' work on the same deliverable ends "
            "up untracked as a single thing.",
            "Stopping a level too coarse to estimate ('Build the reporting "
            "module' as one task no one can size) or going a level too fine to "
            "manage (tracking fifty two-hour tasks that turn every status "
            "update into an audit).",
            "The classic error: decomposing into activities ('design', 'code', "
            "'test') instead of deliverables. A WBS is a hierarchy of things "
            "produced, not a hierarchy of verbs -- 'design the login screen' "
            "is an activity that belongs inside a task against the deliverable "
            "'Login screen', not a decomposition level of its own.",
        ),
        worked_example=(
            "A regional credit union is building a new online loan application. "
            "The scope statement names one deliverable: 'Online loan "
            "application, application through decision'. The PM decomposes it "
            "into component deliverables -- 'Applicant identity verification', "
            "'Document upload', 'Underwriting decision integration', 'Applicant "
            "status notifications' -- each sized so one engineer or a small pair "
            "can own it. In driftless, each becomes a workstream under the "
            "project, with tasks underneath named for what they produce "
            "('Document upload accepts PDF and JPEG', not 'Write upload code'). "
            "When 'Underwriting decision integration' turns out too big to "
            "estimate as one task, the PM decomposes it one more level into "
            "'Send application to underwriting API' and 'Receive and store "
            "decision result' rather than leaving it as one unestimable line."
        ),
        further_reading=("PMBOK-6 §5.4.2.2",),
    ),
    "inspection": TechniqueContent(
        summary=(
            "Checking a finished deliverable against its requirements before it is formally accepted."
        ),
        when_to_use=(
            "Use it on every deliverable before asking for formal acceptance. "
            "There is essentially no scope deliverable this doesn't apply to -- "
            "'when to avoid it' is close to never, because skipping inspection "
            "means accepting a deliverable on the producer's word alone."
        ),
        when_to_avoid=(
            "There isn't a real case for skipping it outright. The honest "
            "caution is about depth and rigor, not whether to do it at all: "
            "match the inspection's thoroughness to the deliverable's risk and "
            "cost of being wrong, and don't let time pressure turn it into a "
            "rubber stamp -- an inspection that only confirms the deliverable "
            "exists, rather than checking it against its actual acceptance "
            "criteria, isn't validating scope, it's skipping validation with "
            "extra steps."
        ),
        steps=(
            "Pull the acceptance criteria for the deliverable from the scope "
            "statement or requirements documentation -- inspecting against "
            "vague or missing criteria is why rubber-stamping happens.",
            "Decide the inspection method that fits the deliverable: a "
            "walkthrough for a document, a demo for a feature, a physical "
            "measurement for a built artifact, a test run for software.",
            "Have someone other than the person who produced the deliverable "
            "perform or lead the inspection -- self-inspection catches less "
            "and carries less weight with the customer.",
            "Check each criterion individually and record a pass, fail, or "
            "conditional result for it -- not one overall thumbs up.",
            "Route anything that fails back to the team producing the work as "
            "a defect or change, and only carry the deliverable to formal "
            "acceptance once every criterion is met.",
        ),
        outputs=(
            "A verified deliverable, checked criterion by criterion against "
            "its acceptance criteria.",
            "An inspection record documenting what was checked and the result "
            "-- the evidence formal acceptance rests on.",
            "A list of defects or gaps routed back for rework, if any.",
        ),
        pitfalls=(
            "Turning inspection into a rubber stamp -- confirming the "
            "deliverable exists or looks plausible rather than checking it "
            "against its actual, specific acceptance criteria.",
            "Letting the producer inspect their own work with no independent "
            "check, then presenting that as validation.",
            "Inspecting against criteria that were never written down, so the "
            "result is really just someone's opinion dressed up as a "
            "verification step.",
        ),
        worked_example=(
            "A city parks department has a deliverable: a redesigned "
            "playground, built to a signed-off design spec with named safety "
            "criteria (fall-zone surfacing depth, equipment spacing, "
            "accessibility clearances). Before the department accepts the "
            "playground from the contractor, the PM leads a walk-through "
            "inspection with the safety inspector and the original design "
            "lead -- not the contractor's own foreman -- checking each named "
            "criterion against the built result and recording pass/fail per "
            "item. Two clearances fail; the contractor reworks them and the "
            "inspection is repeated on just those items before the parks "
            "department signs formal acceptance."
        ),
        further_reading=("PMBOK-6 §5.5.2.1",),
    ),
    "product_analysis": TechniqueContent(
        summary=(
            "Turning a stated product idea into a defined, actionable set of requirements and deliverables."
        ),
        when_to_use=(
            "Use it during Define Scope when the product itself -- not just "
            "the project's process or timeline -- is under-specified: you have "
            "a product concept or a one-line description and need to work out "
            "its functions, components, and requirements before Create WBS can "
            "decompose anything."
        ),
        when_to_avoid=(
            "It applies to product deliverables, not to every project. A "
            "project that is entirely process, event, or service work with no "
            "product being built or modified has nothing for product analysis "
            "to analyze -- don't force a value-engineering pass onto a "
            "deliverable that's actually an activity or a service outcome."
        ),
        steps=(
            "Start from the stated product description or concept, however "
            "informal, and name its major functions -- what it has to do, not "
            "how.",
            "Break each function into the components or subsystems that "
            "deliver it (product breakdown) so the product's structure, not "
            "just its purpose, is visible.",
            "For each component, ask whether it earns its cost relative to the "
            "function it serves (value engineering/value analysis) -- flag "
            "anything that looks like it costs more than the function is "
            "worth.",
            "Turn each function and component into specific, testable "
            "requirements (requirements analysis) -- 'the checkout flow "
            "completes in under 5 steps', not 'checkout should be easy'.",
            "Validate the resulting requirement set with the people who stated "
            "the original product concept before it feeds Create WBS.",
        ),
        outputs=(
            "A structured breakdown of the product's functions and components.",
            "A set of specific, testable requirements derived from the product description.",
            "Flags on any component whose cost looks disproportionate to the function it serves.",
        ),
        pitfalls=(
            "Treating product analysis as an abstract exercise -- naming "
            "generic functions ('user management', 'reporting') without ever "
            "converting them into requirements someone can build or test "
            "against.",
            "Applying it to non-product deliverables (a training rollout, a "
            "process change) where there's no product structure to analyze, "
            "producing busywork instead of clarity.",
            "Skipping the value-engineering pass and accepting every stated "
            "component at face value, missing the chance to drop or simplify "
            "something that costs more than it delivers.",
        ),
        worked_example=(
            "A community college is told to build 'a student advising "
            "portal'. The PM runs product analysis: breaks the concept into "
            "functions (schedule an appointment, view degree progress, message "
            "an advisor), then components under each (a calendar service, a "
            "degree-audit data feed, a secure messaging channel). Value "
            "engineering flags the secure-messaging channel as expensive "
            "relative to its use -- advisors already use campus email -- so "
            "the PM proposes dropping it in favor of a mailto link, saving a "
            "build the sponsor agrees wasn't earning its cost. The remaining "
            "functions become specific requirements ('a student can book an "
            "advising slot at least 48 hours out, in under 3 clicks') that "
            "feed Create WBS."
        ),
        further_reading=("PMBOK-6 §5.3.2.5",),
    ),
    "prototypes": TechniqueContent(
        summary=(
            "Building a working model of a product early, so stakeholders can react to something real."
        ),
        when_to_use=(
            "Use it when stakeholders genuinely can't agree on, or can't "
            "articulate, what they want until they see or use something -- a "
            "new user interface, an unfamiliar workflow, a physical layout. A "
            "prototype settles arguments a spec review keeps circling on."
        ),
        when_to_avoid=(
            "Skip it when requirements are already well understood and "
            "well-precedented -- prototyping a form field that behaves exactly "
            "like every other form field in the system burns time on feedback "
            "nobody needs. Also watch the build cost: a prototype meant to be "
            "throwaway is only cheap if it's actually kept throwaway; don't "
            "commission one you can't afford to discard."
        ),
        steps=(
            "Pick the specific unresolved question the prototype needs to "
            "answer -- 'does this navigation pattern make sense to a first-time "
            "user', not 'build the app'.",
            "Build the minimum fidelity that answers that question -- paper "
            "sketches or clickable mockups for a workflow question, working "
            "code only if the question is about real behavior or performance.",
            "Put it in front of the actual stakeholders or users it's meant "
            "for, not just the project team, and capture their reaction as "
            "structured feedback, not just impressions.",
            "Revise and repeat progressive elaboration -- most prototyping is "
            "iterative -- until the specific question is answered.",
            "Convert what you learned into requirements or scope decisions, "
            "and explicitly decide and document whether the prototype itself "
            "is discarded or becomes a starting point for real development.",
        ),
        outputs=(
            "A tangible model (sketch, mockup, working sample) stakeholders have reacted to.",
            "Requirements or scope decisions sharpened by that reaction.",
            "An explicit decision on the prototype's fate -- discarded, or "
            "carried forward as a build starting point.",
        ),
        pitfalls=(
            "A throwaway prototype quietly becoming the product -- built "
            "quickly with shortcuts that were fine for a demo, then shipped "
            "under deadline pressure without anyone deciding to accept that "
            "debt.",
            "Building higher fidelity than the question needs, so the "
            "prototype takes as long as building the real thing and the "
            "'fast feedback' benefit disappears.",
            "Showing the prototype only to the project team instead of the "
            "actual users, so the feedback validates the builders' assumptions "
            "instead of testing them.",
        ),
        worked_example=(
            "A regional theater company wants a new seat-selection flow for "
            "online ticket sales but the marketing lead and the box-office "
            "manager keep disagreeing in meetings about what 'simple' means. "
            "The PM has a designer build a clickable prototype of three seat "
            "map interactions in an afternoon -- no real backend -- and runs it "
            "with five recent ticket buyers. Two of the three interactions "
            "confuse every tester; the third is clear. That settles the "
            "internal argument in one session, and the PM explicitly logs "
            "the prototype as throwaway -- development will build the chosen "
            "interaction against the real seat inventory system from scratch, "
            "not extend the demo code."
        ),
        further_reading=("PMBOK-6 §5.2.2.8",),
    ),
}
