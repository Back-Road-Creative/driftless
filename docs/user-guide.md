# Using driftless

Every figure here is computed — nothing on a screen was typed by anybody. **Each fenced block
below is opened by `tests/test_docs_user_guide.py`** as a signed-in browser against a real store,
so a screen or label that stops being true fails there. `$USER_PASSWORD` is your own password.

## 1. Signing in

Ask for any page without a session and you land on `/login`. Type the two things:

<!-- driftless:run signin status=200 -->
```text
Username: dana
Password: $USER_PASSWORD
```
<!-- driftless:run text -->
```text
Needs attention
```

You land on the dashboard, signed in for 12 hours. Every refusal reads the same whichever half was
wrong, and 5 failures in 15 minutes buys a wait. **Sign out ends the session on every
device** — your account is revoked, not one cookie. `admin` and `contributor` read and write;
`viewer` reads every page and meets *"That is a read-only account"* on any change.

## 2. Orientation — the method, the map, and how a project proves itself

Before the screens: what driftless is actually built out of, in one walk, so the rest of
this guide reads as detail rather than surprise.

**The map opens on the processes and expands from there.** It starts with every PMBOK
process driftless knows, in lifecycle order, joined by the lines for who feeds whom. Open
any one and the map redraws around it: that process, every technique and artifact kind it
touches, and only the ties between them. A line above says how much of the whole you are
seeing; `?view=all` draws everything at once, and the lists underneath name every process,
technique, artifact and tie whichever reading is on screen:

<!-- driftless:run page status=200 -->
```text
/map?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
The method map
```

Narrowing the map with the filter chips, the search box or flow-only updates the address
bar to match, so a filtered view is a link you can bookmark, reload or hand to someone else.

Nothing about that picture depends on any one project — it is the method itself. What a
project *has done* against it lives on the process map instead (`/process-map` whole-business,
`/projects/{id}/process-map` per project), and on the **wizard**, which is where a project's
own path through the method turns into the next thing to do. Each process map links back
to this washed method map and to the PMBOK reference, so a reader can move between "what the
method calls for" and "what a project (or the whole business) has done against it" without
retyping a URL.

**A wizard step is a workspace, not a bare form.** Ask it what the next incomplete process
is and it hands back a plain-language explanation of why that process matters, which of its
inputs the project already has, how to produce the ones it does not, and what running it
would leave behind — never a form field with no context around it:

<!-- driftless:run page status=200 -->
```text
/projects/1/wizard?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Get formal sign-off that the project exists and names who is running it.
```

**"How you do it" names a support tier for every technique, in four plain words.** A
technique the wizard can only explain reads *"Guide only —"* plus the one reason it stops
there. One that can fill in a whole page of five-or-so techniques at once (product analysis,
a context diagram, benchmarking) is a **worksheet**. One that runs a single formula off the
project's own numbers (earned value, to-complete performance) is a **calculator**. A fourth
tier, **modeler**, is reserved in the same vocabulary for a page that would run a full
what-if simulation rather than one formula or one worksheet — nothing has reached that tier
yet, so every technique today reads guide, worksheet or calculator, honestly, never a promise
of a fifth kind of page that does not exist.

**A Scrum, Kanban or operations project satisfies the same controls two different ways.**
First, a **crosswalk**: where a predictive project's evidence for a control is a stored
document, an agile project's may be a backlog item, a release or a sprint's own
retrospective notes instead — read from the project's own rows, never typed a second time.

<!-- driftless:run page status=200 -->
```text
/methods/scrum
```
<!-- driftless:run text -->
```text
Scrum
```

Second, **tailoring**: whether a Monitoring & Controlling process reads against the one
approved plan or against the team's current commitment is set once, project-wide, by the
project's delivery mode, and every process map names which:

<!-- driftless:run page status=200 -->
```text
/projects/1/process-map?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Tailoring — Predictive
```

`/org/configuration` lists all three modes — predictive, agile, hybrid — side by side, each
with its own plain-language reason.

**Whichever mode a project runs, the plan itself only ever changes one way.** A what-if
stays a what-if — the earned-value calculator's cost scenarios, the procurement worksheet's
bid comparisons — until somebody raises a **change request**, and only its approval produces
a new baseline version. There is no second path to a new plan, and an approved baseline
cannot be edited underneath the change that produced it.

**Where the proof lives.** Nothing above is asserted in prose alone. The technique and
artifact catalogs are held to *totality* — every member is either supported and says how, or
unsupported and says why, walked as a whole set rather than sampled (`tests/test_technique_totality.py`,
`tests/test_artifact_totality.py`, `tests/test_launcher_totality.py`) — and a change to a
project is checked against every family that is supposed to see it
(`tests/test_propagation_manifest.py`). `driftless pmbok support` prints that same coverage
as a store-wide count, and `driftless pmbok proof` — the same answer as a page at
`/pmbok/proof` — states whether anything at all is left unaccounted for, so "how much of this
does the product actually help with" is a command you can run rather than a claim you have
to take on faith.

## 3. The dashboard — is the whole business on track?

<!-- driftless:run page status=200 -->
```text
/?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Cost S-curve — whole business
```

Ten tiles: budget, actual spend, percent complete, share of projects on track, open high risks,
open threats, process completeness, work in progress, throughput per week, median cycle time.
Then the whole-business cost curve, a treemap whose rectangle
*areas* are portfolio budgets, and the rollup table — business to project, each row with its RAG,
budget, actual, percent complete, open high risks, a burn sparkline and the date it last filed a
status (`never` if it never has). Names link: portfolio and program to their rollup, project to its hub.

**Every page takes `?as_of=YYYY-MM-DD`.** Leave it off for today; set it to see the business
exactly as it stood that day. No page reads the clock for anything else.

## 4. Needs attention, and the threat board

The dashboard's right-hand rail ranks everything wanting a decision: assessed threats plus three
data gaps — never filed a status, last status over 14 days old, completeness under 25%. Every red
threat outranks every gap whatever the score. A gap links its fix page; a threat carries sign-off.

<!-- driftless:run page status=200 -->
```text
/threats?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Top threats
```

`/threats` is that ranking in full, 15 cards a page, grouped under the project they belong to and
listing the PMBOK actions the assessment attached. Signing one off — accept, resolved, defer,
reject — records who signed and suppresses it: a decision on the record, not a delete. Both mark
the week-over-week move (▲ worse, ▼ better, – flat, or `new`), the number always beside the arrow.

## 5. The project hub — one project at a glance

<!-- driftless:run page status=200 -->
```text
/projects/1/hub?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Live threats
```

Process completeness overall and per knowledge area, the earned-value line (EV, CPI, SPI, EAC,
budget), this project's live threats, open risks/issues/change requests, and milestones with a
`slipped` badge on any past its target. The header links process map, wizard, schedule, board and
weekly status. The **wizard** is a workspace for the next incomplete step, not a bare form: the
process's own plain-language explanation; "What you need" — each input, present or missing, linked
to its own artifact page and, when missing, to the process(es) that produce it; "How you do it" —
each technique with its support tier in words ("Runnable here", or "Guide only — " and why) and a
link to run or read it; "What you get" — each output naming the form on this page or, for one the
wizard cannot produce, why it is read instead; "In your method" — the Scrum or Kanban practices
that crosswalk to this step, read from `?method=scrum` or `?method=kanban` on the address, since a
project carries no method of its own yet; and a "See it on the map" link to the same process,
focused, on the method map. The **Scorecard strategy** section repeats active objective links with their
perspective, direct/supporting contribution type, derived metric statuses, and evidence coverage.
A project with no linked objective gets an explicit unknown state rather than an empty space. A
project with no approved cost baseline says so rather than showing zeros:

<!-- driftless:run page status=200 -->
```text
/projects/3/hub?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
No cost baseline yet — earned value has nothing to measure
```

## 5a. The earned-value calculator

<!-- driftless:run page status=200 -->
```text
/projects/1/assist/earned-value?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
How it is worked out
```

Every figure the hub shows, with its formula spelled out in words and one plain sentence on
what it means — never a second computation, the same snapshot the hub reads. Also works out
the to-complete performance index (TCPI): how efficiently the *remaining* work must run to
still land on budget, and the same question against today's forecast instead. A what-if box
lets you try a different remaining cost and see the estimate at completion it implies; nothing
you type there is saved.

## 5b. The scope worksheet

<!-- driftless:run page status=200 -->
```text
/projects/1/assist/scope?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Product analysis
```

Five techniques that have no number to compute, on one page: **product analysis** (four
plain-words lenses on the project's own scope statement), a **context diagram** (the project's
stakeholders drawn as actors around it), a **prototype checklist** (tied to whether requirements
documentation is filed), a **benchmarking table** you fill by hand with `?against=Name` — nothing
typed there is saved — and an **inspection** walkthrough of the project's milestones with their
status. Every section links the technique's own page in the library; a blank narrative answer is
filled in through the wizard, not here.
## 5c. Procurement and closeout

`/projects/{id}/assist/procurement` lists the project's signed agreements and a closure
checklist read off their own status, beside three no-write what-ifs: a make-or-buy break-even
volume, a weighted bid score with its ranking's sensitivity to each weight, and contract-type
guidance (fixed-price, cost-reimbursable or time-and-materials). `/projects/{id}/assist/closeout`
shows deliverable acceptance from milestone status, the lessons learned register — one dated,
categorised row per lesson raised, never a single body of prose — and a final-report summary
drawn from the figures the hub already computes.
## 5d. The risk-response planner

<!-- driftless:run page status=200 -->
```text
/projects/1/assist/risk-responses?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Total residual exposure
```

The open register, each risk's kind (threat or opportunity) and its latest filed response, if
any — a risk with none reads **no response planned** and outranks an equal-severity risk that
has one on the threat board. Filing a response — strategy, owner, trigger, planned action, the
residual probability/impact it leaves behind, its cost and schedule impact — is the one write
this page allows; residual exposure across the open register is the figure the project hub's
risk reserve line and the gantt page's schedule note both read.

## 5da. The decision-tree calculator

`/projects/{id}/assist/decision-tree` is a no-write what-if: type options with their
probability/value outcomes and it computes EMV per option, marking the best one.
## 5db. Probability × impact scoring

`/projects/{id}/assist/risk-pi` places every open risk on the standard 5×5 matrix, ranked by score.

## 5e. The requirements/WBS worksheet

<!-- driftless:run page status=200 -->
```text
/projects/1/assist/requirements?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Traceability matrix
```

The traceability matrix (each requirement against the deliverable, task or backlog item it
traces to), the untraced requirements and the deliverables no requirement traces to — both
named in words rather than left implicit — the WBS as an indented list plus a plain-text
twin, and the acceptance ledger. Filing a requirement, filing a trace and recording an
acceptance are the three writes this page allows; acceptance only ever appends, so a later
verification pass never rewrites an earlier one.

## 5f. The team assist page

<!-- driftless:run page status=200 -->
```text
/projects/1/assist/team?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
RACI matrix
```

The RBS as an indented list plus a plain-text twin, the RACI matrix (who holds which role
against which deliverable or task), who lacks what (open acquisitions and people with no
training on record), the team-assessment trend and open conflicts with their follow-up
actions. Filing an assignment, recording an assessment and logging a conflict or its action
are the writes this page allows; a team assessment only ever appends, so a later reading
never rewrites an earlier one.

`?preview_person_id=<id>&preview_task_id=<id>` previews the resource-clash a proposed
assignment would cause — the person's own weekly hours now, and with the task's hours
added, read off the same heatmap grid `/org/heatmap` draws — without filing anything or
levelling the plan.

## 5g. The flow calculator

<!-- driftless:run page status=200 -->
```text
/projects/1/flow?as_of=2026-07-01
```

Work in progress, throughput over the trailing week, cycle and lead time, the release
forecast band, and — for a sprint whose window contains the as-of — burndown and burnup
as charts, plus cumulative flow as a table. The same figures a project's hub page shows
in its Flow tile, read from one adapter so the two can never disagree.

## 5h. Decisions and meetings

<!-- driftless:run page status=200 -->
```text
/projects/1/assist/decisions?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Decisions and meetings
```

Try a vote against unanimity, majority or plurality; rank options by weighted criteria and see
which one decides the outcome; preview an autocratic decider-plus-rationale record; or get a
fixed, plain-steps agenda for a brainstorm, nominal-group session, focus group, interview or
workshop. All four are no-write what-ifs — nothing typed there is saved. The one write this page
allows is meeting evidence: record a meeting's purpose, attendees, decisions and owned
follow-up actions, and it is filed and shown in the list above the form, the same append-only
ledger every technique run leaves.

## 5i. The cost workbench

<!-- driftless:run page status=200 -->
```text
/projects/1/assist/cost?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Cost workbench
```

Ten techniques on one page, every one a no-write what-if: cost **aggregation** rolled up
from this project's own budget lines, **reserve analysis** (a contingency reserve on top of
the work packages, a management reserve on top of that), the **cash-flow S-curve** — the same
accrual the earned-value calculator's planned value reads — with **funding limit
reconciliation** against it, **financing** cost (simple or compounding), **run rate** off
recorded spend, **cost of quality** (conformance versus non-conformance), other projects'
actual spend as a real **historical** reference figure, and the four **estimating
techniques** (analogous, parametric, three-point/PERT, bottom-up), each returning its own
plain-words basis. Nothing typed into the what-if forms is saved — except through the one
write the page allows: **file this estimate**, which stores the last what-if computed as an
estimate scenario (technique, value, range, basis, who filed it) and lists it back under
**Stored estimate scenarios** as of the date. The budget itself still only changes one way,
through a change request — the link at the foot of the page.

## 5j. The quality workbench

<!-- driftless:run page status=200 -->
```text
/projects/1/assist/quality?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Control charts
```

A control chart per metric with two or more dated readings, drawn with its mean and ±3σ
limits and the rule-of-seven signal in words; a Pareto of out-of-tolerance readings ranked by
metric with the "vital few" named; a no-write statistical-sampling what-if; a fishbone/five-whys
worksheet you trace over one issue from the RAID log; a no-write cost-of-quality what-if (the
budget's own cost categories carry no conformance/non-conformance split, so this is typed by
hand); and an audit checklist read straight off the project's quality management plan, one line
per sentence. Nothing typed into any of the what-ifs is saved.

## 5k. The schedule-network calculator

<!-- driftless:run page status=200 -->
```text
/projects/1/assist/schedule?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Schedule network
```

The network drawn straight off the newest approved baseline: which tasks are on the
critical path, and how much float everything else carries. `?crash=<task>:<days>` and
`?fast_track=<predecessor>:<successor>` each preview one scenario — shortening a task, or
overlapping one dependency — without changing anything stored, shown beside the current
plan's own finish, critical path, total cost and EAC (at today's cost-performance index)
for a side-by-side what-if. A critical-chain view sits
below it, clearly labelled as a Driftless extension rather than a PMBOK-6 technique. The
one write on the page proposes whichever preview is showing as a draft baseline and a
change request; approving it and promoting the draft to the live plan is a separate step,
through the same `PATCH` endpoints every other baseline approval goes through.

## 6. Filing the weekly status

<!-- driftless:run page status=200 -->
```text
/projects/1/status?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
stamped from the tasks
```

Pick a RAG — green, amber or red — write a note, save. That is the whole form: **you never type a
percentage.** Completion is computed from the tasks (earned value over budget) and stamped onto the
snapshot, so it can never claim progress the work does not show; each save appends a row, and that append-only series IS the trend line above.

## 7. Reading the numbers

- **RAG** is worst-child-wins: a portfolio is not green while a project under it is red. A fourth
  state, shown as **no data**, means nothing to assess — no baseline, no milestones, no status ever
  filed. It is not a mild amber; it is an empty project.
- **EV** (earned value) is budget × how far the work actually got, at the as-of date.
- **CPI** = EV ÷ actual cost: above 1.0 the work cost less than planned, below 1.0 more.
- **SPI** = EV ÷ planned value: above 1.0 ahead of plan, below 1.0 behind.
- **EAC** = budget ÷ CPI — the likely total cost at this efficiency. Three other EAC
  formulas are on the earned-value calculator, each naming when to use it instead.
- **CV** (cost variance) = EV − actual cost, **SV** (schedule variance) = EV − planned
  value: positive is under budget / ahead of plan, negative the opposite. CV%/SV%
  divide each by EV/PV, so a small project's variance and a large one's compare.
- **`n/a` is never 0.** CPI has no meaning before the first spend, SPI before the baseline
  starts accruing, EAC while CPI is undefined. They read `n/a`, never a flattering zero.
- **Process completeness** is the share of a project's applicable PMBOK processes produced or signed
  off; waived and not-applicable ones are excluded, so an area with nothing to assess reads `n/a`.

## 8. The other screens

<!-- driftless:run page status=200 -->
```text
/projects/1/board
```
<!-- driftless:run page status=200 -->
```text
/projects/1/gantt?as_of=2026-07-01
```
<!-- driftless:run page status=200 -->
```text
/projects/1/schedule-health?as_of=2026-07-01
```
<!-- driftless:run page status=200 -->
```text
/projects/1/flow?as_of=2026-07-01
```
<!-- driftless:run page status=200 -->
```text
/org/heatmap?as_of=2026-07-01&weeks=13
```
<!-- driftless:run page status=200 -->
```text
/org/departments
```
<!-- driftless:run page status=200 -->
```text
/org/configuration
```
<!-- driftless:run page status=200 -->
```text
/method
```
<!-- driftless:run page status=200 -->
```text
/projects/1/assist/stakeholders?as_of=2026-07-01
```
<!-- driftless:run page status=200 -->
```text
/search?q=Fleet
```
<!-- driftless:run text -->
```text
Fleet Modernization
```

**Organization configuration** makes the operating model visible before a delivery dashboard is meaningful: live counts for businesses, portfolios, programs, projects, departments, people, quality metrics, strategic objectives, metric definitions, observations, and project contributions. Its **Balanced operating readiness** table marks missing layers as **Needs setup**, links to the existing Scorecard and department surfaces, and names the validated API path that establishes each layer; it never creates a second configuration store. **Board** files every task into a column named by its own status — todo, in_progress, blocked, done —
each card carrying workstream, assignee, percent, estimate and, when it is not zero, how many
tasks it waits for, the status printed as a word so "blocked" reads as blocked in greyscale.
**Schedule** draws the approved baseline's planned windows and the milestone diamonds against the
as-of as "today", every bar repeated as a table row, with the project's dependency network listed
beside it — which task depends on which, its type and any lag or lead in days — and a note naming
the project's own working-day calendar when it has one.
**Capacity** is people × weeks of allocated hours against each person's weekly capacity — 6 weeks
by default, 1 to 26 with `?weeks=`; hours with no approved window land in *Unplaced* rather than
being dropped. Each cell prints the share of that week it takes as well as the hours, and draws a
bar at the same length, so where the pressure is reads off the picture rather than off the digits;
the share is text, so greyscale, a colour-blind reader and high-contrast mode all keep it. Person
and Capacity stay pinned to the left as the week columns scroll sideways, and the key under the
grid is generated from the very thresholds the cells are judged by. **Departments** is headcount and capacity per department; drilling into one also
lists its own operating records in plain words — services, the work queue, recurring work,
service levels, controls, incidents and improvements. From there, the **department workspace**
adds objectives its accountable projects contribute to, an operating plan, a RACI matrix built
from real rows (a service's owner, the department itself, stakeholder-proxy project roles and
work-request requesters — never a typed-in role column), demand versus capacity classified the
same way the capacity heatmap washes its own grid, service levels measured by a plain average
cycle time over done work requests, the department's own budget lines beside the run rate of
spend on its projects, and the vendor agreements and stakeholders touching its own projects.
**Search** matches portfolios, programs, projects, workstreams, tasks, risks and issues by name, 10 hits per kind.
**Stakeholder assist** (linked from the project hub) is the first CALCULATOR-mode page: the
power/interest grid (who to manage closely, keep satisfied, keep informed or only monitor),
a current-versus-desired engagement matrix with a per-stakeholder what-if and the gap action
it opens, and a communications matrix — who, what, how often and over which channel, derived
straight from each stakeholder's own record rather than typed in a second time.

**Method** is the way in to all of the reference material that follows: one card per surface
— the process reference, the technique library, the method profiles, the artifact catalog,
the glossary, process status and the map — each saying what it is for, when you would open
it and how much it holds, counted off the registry behind it.
**The Method pages below are theory, reachable in one click from the primary nav (PMBOK,
Techniques, Methods, Artifacts, Glossary, Process map, Map) — never only through a project.**
Each is one address, on its own, unrelated to any one project's history. Several of them answer
the SAME address a second way: add `?project={id}` (and, where the page also takes an as-of,
`&as_of=YYYY-MM-DD`) and the page adds that one project's own live reading alongside the theory
— its computed state, its recorded runs, its assessment — without leaving the address or
changing what the page is about. Leave the parameter off and the page is the frozen catalog,
identical on every request. **Wizard** walks a project's processes in lifecycle order, one at a time: most steps
are a form for the output the wizard can write, but a process whose output is
worked out from data already in the store (not typed anywhere) or that the wizard
does not track at all is shown just as honestly — what it produces, which of its
inputs the project already has, and which earlier step's link to follow for the
ones it does not — rather than being silently skipped as if it did not exist.

## 8a. PMBOK reference

<!-- driftless:run page status=200 -->
```text
/pmbok
```

The 49 PMBOK processes as a stateless knowledge-area × process-group grid, computed from the
frozen catalog rather than any project's history — reachable as theory, not only through a
project. Every cell also names, in plain words, how much help this product gives that step
today: "You can fill this in here" once the wizard can produce one of its outputs, "We can judge
this step" when the store can at least assess it without that, or "Read-only for now" otherwise, and links to its own process page.
A legend under the grid explains those three words, and a "How to read this page" block
defines ITTO, predictive, knowledge area and process group before the grid leans on them.
Theory is not a dead end here: the page links each project's own process map, for reading
the same grid against real progress, and carries a strip to the rest of the method
reference — techniques, artifacts, methods, the method map and the business process map.

## 8b. A process page

<!-- driftless:run page status=200 -->
```text
/pmbok/4.1
```

Every process's own page opens with a plain-language line — one sentence, no jargon — under the
title, the terms of art in it linked to the glossary, then why it matters, what "done" looks
like, and a tip for the first time you run it; the
Inputs, Tools & Techniques and Outputs lists below are headed "What you need", "How you do it"
and "What you get", with the PMBOK terms kept alongside in parentheses. Where it exists yet, a
worked example and a pitfalls list follow, then "How driftless helps": which techniques it can
already run and which outputs the wizard can already produce, derived from the same registries
those pages link to, never retyped. A **Related** block at the foot links the processes it feeds
and is fed by, its knowledge-area and process-group siblings, its techniques and artifacts, and
the Scrum or Kanban practices that cover it. Without `?project=` this
is the stateless reference it has always been. With `?project={id}` (and `&as_of=`, carrying the
pinned date through the hop) it is the REST of a process-map drill rather than a dead end: this
project's live artifacts, its computed state for the process, and its knowledge area's assessment
with the threats and actions attached. Reached that way, its own links carry the project and the
as-of onward rather than dropping the reader back into theory — the one at the foot goes back to
the map they came from, instead of to the theory grid; an unknown process id 404s rather than
500s.

## 8c. The totality proof

<!-- driftless:run page status=200 -->
```text
/pmbok/proof
```

`driftless pmbok support` prints the store-wide coverage count over the whole catalog, rather
than one technique or process at a time. `driftless pmbok proof` (also `/pmbok/proof`) goes one
step further and states, in plain words, whether anything is left unaccounted for at all. It
reads `driftless.pmbok.proof.build_proof()`, which counts four gap shapes — always the
counter-example, never a tally of what is fine — plus one fact that rides beside them:

- **Orphan** — a catalog member (technique, artifact kind or method practice) no process, and no
  honest exemption, ever names.
- **Unexplained** — a registry member (process, technique or artifact kind) with no plain-language
  summary.
- **Unlaunchable** — a technique or artifact kind with neither a launcher nor a documented reason
  it cannot have one.
- **Uncrosswalked** — a Scrum/Kanban practice, an agile model, or a Monitoring & Controlling
  process a tailoring profile leaves unmapped, with no PMBOK reading and no reason it lacks one.
- **Skipped processes** — every process the wizard would pass over entirely rather than ever
  offering as a next step.

Every one of the five is asserted empty by its own totality test; the page and the `driftless
pmbok proof` command both report the live count, plain-worded, plus the offending members for any
that is not zero — the same answer, whether you ask it as a page or as a command. The page spells
each row out further: what that check looked at, and what finding anything there would mean.

`driftless pmbok proof` also carries a checkable subcommand for each of the wedge claims — no
vendor claims these, so the point is to let an outsider run the check rather than take driftless's
word for it. Every one exits 0 when the claim holds and non-zero with the offending rows when it
does not:

- `driftless pmbok proof no-typed-status` — a portfolio, program or project's status and percent
  complete are computed by `driftless.calc.rollup.roll_up`, never a stored column a rollup could
  disagree with. Needs no database: it reads the model schema alone.
- `driftless pmbok proof baseline-immutable PROJECT [--db-url URL]` — attempts a write on the
  project's newest approved baseline and shows the refusal (a plan change is a new version, never
  an edit to the version of record).
- `driftless pmbok proof forecast PROJECT [--seed N] [--as-of DATE] [--db-url URL]` — runs the
  seeded Monte Carlo completion forecast twice and checks the percentiles come back
  byte-identical.
- `driftless pmbok proof process-state PROJECT [--as-of DATE] [--db-url URL]` — prints every
  catalog process with its computed state and the output artifacts that satisfy it, then checks
  no process claims produced or in-progress with nothing behind it.
- `driftless pmbok proof reproduce PATH` — reads a saved markdown report or HTML page off disk
  and verifies its reproducibility receipt, detecting the format from the content rather than the
  file extension. Needs no database.

A leaf `Task.percent_complete` is not part of this claim — someone has to report it, since there
is nothing under a leaf to roll up from; `no-typed-status` checks only the rollup levels above it.

## 8d. Technique library

<!-- driftless:run page status=200 -->
```text
/techniques
```
<!-- driftless:run page status=200 -->
```text
/techniques/earned-value-analysis
```
<!-- driftless:run page status=200 -->
```text
/techniques/earned-value-analysis?project=1&as_of=2026-07-01
```

**Technique library** explains every tool
and technique those processes name — grouped by family with a one-line summary each, and one
page per technique giving when to use it, when not to, the steps in order, what it produces,
what usually goes wrong, a worked example and — where the edition defines one — the PMBOK-6
clause it comes from. The index itself says what each family is for, in a line under its
heading, and gives every technique a "how much help" column: *Runnable here* where an
assistant can be opened and run for it, *Worksheet* where a printable worksheet is the
honest shape instead, and otherwise the one sentence recorded beside that technique
saying why this product explains it rather than running it. A key above the tables names
the three and says how many techniques sit in each, counted from the registries rather
than typed, and a "How to read this page" note explains the grouping. A handful of
techniques carry no clause, and the page says why that one has none rather than leaving a
reader to guess: PMBOK-6 treats some in narrative rather than at a numbered clause, names
others only as an umbrella group whose members carry the numbers, and there are further
reasons besides. Which reason applies to which technique is recorded one by one, beside
the technique, in `driftless/pmbok/reasons.py:UNCITED_EXEMPTIONS`, and the page prints
that sentence as recorded. The one reason it holds back is one that quotes the clause
number that was found and ruled out: a page for a technique with no citation never prints
a clause number, so those keep the general sentence alone. A citation we could not confirm is
left blank on purpose — a made-up clause number
is worse than a missing one, because a reader cannot tell it from a real one. Every technique's own page
also says its support tier in plain words: "Runnable here" once it has a launchable assistant, or
"Guide only — " and the one sentence recorded for it in
`driftless/pmbok/reasons.py:GUIDE_ONLY_REASONS` otherwise. When a project is in scope, "Runnable
here" is itself the link to that assistant, so the page does not tell you help exists and leave you
to find it; with no project in scope there is no address to send you to, so the words stay plain
rather than pointing at one that does not exist. With `/techniques/{slug}?project={id}`
(and `&as_of=`) the page adds a "Runs on this project" list — every run recorded for that
technique on that project, by date and actor, against the process it was run for; leave
`?project=` off and the page is the frozen catalog entry alone, on every request. A
`?project=` naming a project that does not exist 404s, the same way `/pmbok/{process_id}`
already rejects an unknown project, rather than rendering as an empty run list.
Each technique page ends with a **Related** panel — the processes that use the technique,
the rest of its family, the artifacts those processes produce, and any Scrum or Kanban
practice that crosswalks to it — worked out from the registries rather than written by
hand, so even a technique no process names still offers its place on the map.

## 8e. Methods

<!-- driftless:run page status=200 -->
```text
/methods
```

**Method profiles** describes Scrum and Kanban the same way, in Driftless's own words: one page per
method, its practices grouped by kind, each crosswalked to the PMBOK-6 processes or
techniques it most nearly resembles, or the one sentence saying why none does
(`/methods/{key}` — see `/methods/scrum` in section 2 above). The index page explains what
"crosswalked" and "guide-only" mean, with "crosswalked" linked to its
[glossary entry](/glossary#crosswalk), so the coverage count above the list is never left to
guesswork. Each profile also carries its own working material — a sprint-planning agenda and a
Definition of Done checklist for Scrum, a board-policy template for Kanban — and Kanban's page
links `?project=`'s own board when a project is in scope; Scrum has no matching view of its own
yet, so its page never fabricates one. A process page's Tools & Techniques list links straight
into it, and so does every recommendation the assessment makes — on the threat board, on a
process drill-down, in `driftless assess` and in the Assessment Report — so applying a technique
lands on the explanation rather than on the name. That holds for every technique in the catalog,
including any Driftless added itself, which no PMBOK-6 process names. Neither page reads a
clock: both method pages are the frozen registry, and the optional project link is a plain query
parameter, never a store read.

## 8f. Artifact catalog

<!-- driftless:run page status=200 -->
```text
/artifacts
```
<!-- driftless:run page status=200 -->
```text
/artifacts/project-charter
```
<!-- driftless:run page status=200 -->
```text
/artifacts/project-charter?project=1&as_of=2026-07-01
```

**Artifact catalog** does the same for every kind of plan, baseline, document, performance
record, procurement record, deliverable, change or environment factor a process's ITTO table
can name — grouped by family, and one page per kind saying what it is, why it matters, what it
looks like on this product, which processes make it and which read it, and whether this
product's store tracks it. A process page's Inputs and Outputs lists link straight into it, the
same way its Tools & Techniques list links into the technique library. A management plan's
page also prints a blank **template** of the document — its sections, the fields each one
holds, one line of guidance per field, and the record a filled-in copy is read back from —
which needs no scripting and prints on paper. With
`/artifacts/{slug}?project={id}` (and `&as_of=`, the pinned date carried through the same as
`/pmbok/{id}?project=`) the page adds what THIS project's store answers for this one kind —
present and healthy, present and at risk, absent, or not tracked — narrowed to the one kind the
page is about rather than a whole process's ITTO table, and its "Made by"/"Used by" process links
and its link back to this project's process map carry that same project and as-of forward rather
than dropping the reader back into theory mode. A kind the store does not track says why, in the
same plain sentence the catalog index already gives it.

## 8g. Glossary

<!-- driftless:run page status=200 -->
```text
/glossary
```

**Glossary** defines the PMBOK terms of art those pages use in passing — baseline, float,
critical path, EVM, WBS, RAG and the rest — in plain words first, one sentence before any
further detail. Every term carries an id its own entry is addressed by, so `/glossary#float`
opens the page scrolled straight to that entry — the same address the `gloss` filter's own
links and every deep link elsewhere in the product resolve to. A technique page's summary,
when-to-use and when-to-avoid prose link each term's first mention to its entry via that same
filter, and later mentions in the same run of prose stay plain so a paragraph does not turn
into a wall of links; a term already linked once in a passage is never linked again beside it.
Where a term has one obvious home elsewhere in the product, its entry also carries a "Where
you meet it" line linking straight there — never invented, never every entry.

## 8h. Business process map

<!-- driftless:run page status=200 -->
```text
/process-map?as_of=2026-07-01
```

**Business process map** is the 49
PMBOK processes as knowledge area × process group, whole-business — click a cell (or add
`?process={id}` to the address directly) for the roster of every project against that one
process, filtered to the same applicable pairs the grid's own completeness share pools.

## 8i. Project process map

The same 49-process grid, once per project (`/projects/{id}/process-map?as_of=` — see
`/projects/1/process-map` in section 2 above), now carrying that project's own computed state per
cell, a sign-off picker naming each process the grid drew, and per-knowledge-area completeness
rings.

### Which rules apply to my project

**Process map** also answers a question the grid alone cannot: for each of the twelve
Monitoring & Controlling processes, does *this* project read it against a fixed plan, the
team's own current commitment, or the department's own standing service cadence? That is set
once, project-wide, by the project's delivery mode — **Predictive** reads every control
against the one approved baseline; **Agile** reads most controls against the team's current
sprint or backlog, not a fixed number; **Hybrid** keeps cost, resourcing, communications and
procurement on the baseline while letting scope, schedule, quality, risk and stakeholder
engagement follow the team's own cadence; **Operations** reads every control against the
department's own service levels, incidents and recurring work instead — a project a
department runs as standing service work, rather than a one-off delivery effort. This is not
just a label: a project's evidence is read through whichever mode its control names, so the
SAME sprint or service-level rows read a control PRODUCED under one mode and not another.
Whichever mode a project runs, the plan itself only ever changes one way: raising a change
request, which on approval produces a new baseline version — never a second approval path.
**Organization configuration** lists all four modes side by side, in plain words, with how
many controls each keeps on a baseline versus a commitment.

## 8j. Method map

**Map** draws the whole
method as one picture — square processes, round techniques, diamond artifacts, joined by a line
wherever one reads, produces, is used by or feeds another; click any shape for its own page. Add
`?project=` to wash a project's own progress onto its processes, or follow a "See it on the map"
link to highlight one shape and everything tied to it — the same ties are spelled out in words
below the drawing, for no mouse and no screen reader alike. With JavaScript on, hovering over or
tabbing to a shape lights its ties and opens a panel with its summary; pressing Space on the shape
you have tabbed to keeps that panel up while you look elsewhere; and chips for kind, process group,
knowledge area, technique family, plus a search box, narrow what shows.

### Reading the map

Three shapes, never a fourth: a square is a **process** — a step the method names; a circle is a
**technique** — a way of doing one; a diamond is an **artifact** — a document or record a process
reads or produces. Whatever else changes on the picture, the shape always tells you which of the
three you are looking at.

A line between two shapes is a **tie** — one process reads an artifact, produces one, uses a
technique, feeds another process the thing it just produced, or is part of a larger piece of
work. Hover or open either end for the plain-English sentence the line stands for.

The **dashes** carry which kind of tie it is, on purpose, so the picture still reads with the
colour turned off or the page printed in black and white. Every kind the map can draw has its
own pattern, and no two share one:

- an unbroken **solid** line **reads** what it points to;
- **long, even dashes** **produces** it;
- **fine, even dots** — it **is used by** what it points to;
- a **dash-dot** line **feeds into** it;
- **tight dots with wide gaps** — it **is part of** it.

Never guess a tie's kind from where it sits on the page — the dash pattern is the only thing
that says so. The legend below the filters names every one of these, plus what the tie means
in plain words.

A tie drawn with its own **short, tight dashes on top** — regardless of kind — is **optional**: it
rests on an artifact its source process is not guaranteed to produce, so that particular
connection may not exist for every project. A tie with no such overlay is certain.

Add `?project={id}` to the address to wash every process shape with that one project's own
progress, the same reading its own process map shows; leave it off to see the method itself, with
no project's history on it. Add `?focus=` — or follow a "See it on the map" link from a process or
technique page — to highlight one shape and everything directly tied to it, dimming the rest so
one relationship stands out of the whole picture.

Clicking a shape opens its own page, and Ctrl/Cmd-click, Shift-click or a middle click open it
in a new tab or window, exactly as they would anywhere else on the web.

The drawing scales to fit your screen by default — **Fit**. **100%** shows it at its own drawn
size, and **+**/**−** step in and out from there; the picture never shrinks past the point its
labels stop being legible.

Below the drawing, a collapsed list per shape spells out every tie in the same plain sentences the
drawing's hovers use — the same reading with no mouse, no screen reader and the page printed on
paper alike.

## 8k. Breadcrumbs and the theory-to-project hop

Every page carries one breadcrumb trail, ending on the page itself, unlinked. A project
sub-page reads Dashboard > that project's name > the page; a Method reference page reads
Dashboard > Method > its own index (PMBOK, Techniques, Methods, Artifacts) > the page — a
technique or artifact page adds one more crumb for its family, between the index and the page.

A process or artifact page switches which trail it shows depending on how you opened it. Reached
theory-first — from the primary nav, `/method`, or the map with no project — it keeps the Method
trail and shows only the frozen catalog. Followed instead from a project (its process map, or the
map washed with `?project={id}`), the SAME address carries `?project={id}` and, where the page
also reads the store by date, `&as_of=YYYY-MM-DD` — `/pmbok/{id}` and `/artifacts/{slug}` both
take the pair — and the breadcrumb switches to that project's own trail; the page adds this
project's live reading (its computed state, its recorded runs) beside the theory, and a
"&larr; back" link near the top returns you to that project's process map. A technique page
(`/techniques/{slug}`) also accepts `?project=` and lists that project's recorded runs of it, but
keeps the Method breadcrumb either way — a technique belongs to the library regardless of which
project's use of it you are reading.

## 9. Taking the data with you

Any list address answers `?format=csv` and downloads as a file — the same fields, in the same order:

<!-- driftless:run page status=200 -->
```text
/projects?format=csv
```
<!-- driftless:run text -->
```text
name,portfolio_id,delivery_mode,status_note,program_id,responsible_department_id,id
```

A list hands back at most 500 rows at a time, JSON or CSV. `?limit=` and `?offset=` walk a
longer one a window at a time, and a `?limit=` above 2000 is trimmed to 2000 rather than
refused. Every answer carries its `X-Total-Count`, `X-Limit` and `X-Offset`, so a windowed
list cannot be read as the whole of one. A list also narrows to a parent id or a `status` before
that window is applied — `X-Total-Count` reports the narrowed count — and a query parameter it
does not recognise is refused rather than silently ignored.

Dates travel too: `/calendar.ics` subscribes your calendar to every milestone and sprint in the
store, `/projects/{id}/calendar.ics` to one project's — a rename then updates that entry, never duplicates it.

## 10. When a number looks wrong

1. **Check the as-of** — an unexpected figure is usually a page still pinned to a date in its
   address. Drop `?as_of=` to see today.
2. **`n/a` and *no data* are answers, not bugs**; the empty state names what to add.
3. **A stale RAG is a stale status.** The rollup's *Last status* column dates every project's
   most recent snapshot; anything over 14 days old is flagged on the rail.
4. **Percent complete disagrees with the team?** It comes from task progress — fix the percentages
   on the board, never the status form.
5. **Refused?** *"That is a read-only account"* means your role is `viewer`; *"That form expired"*
   means the page sat open too long — reload and resubmit.
6. Still wrong: every write is recorded with its author, so your administrator can trace any figure
   back to the row and the person behind it (`docs/admin-guide.md`).
