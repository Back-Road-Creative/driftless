# Temporal model decision record

**Status:** accepted (2026-08-13)

## Decision

Every document and page Driftless renders takes an `as_of` date as an
explicit argument, never the wall clock. Two different reproducibility
properties follow from that, and only one of them holds today.

**Deterministic from an unchanged store.** For a fixed `as_of`, rendering the
same document twice against a store whose rows have not moved between the
two runs produces byte-identical output. This already holds and is pinned:
`tests/test_report_cli.py`'s `test_report_all_is_byte_identical_across_runs`
runs `driftless report all` twice against the same seeded database and diffs
every file it wrote; `tests/test_report_risk_register.py`'s
`test_risk_register_is_deterministic` is the document-level sibling, rendering
the risk register twice from the same session and asserting equality. Nothing
below changes this — the gap that follows is a second, harder property, not a
crack in this one.

**Historically reproducible after later changes.** For a fixed `as_of`,
rendering the same document produces the same bytes whether it runs today or
after a later change to the store, as long as nothing that mattered *as of
that date* moved. This does not hold in full yet: the selector that decides
what "the threshold" was on a given date still does not ask the date. The one
that decides what "the plan" was now does, everywhere it is read.

## Reproducibility boundary — one break closed, one open

**Baseline selection — closed, function and surfaces both.**
`driftless/assess/adapters.py`'s `plan_baseline()` returned its project's
newest baseline with `status == "approved"` — a `max(version)` over the
approved rows, with no `as_of` parameter at all. Approving baseline v3 today
therefore changed what every report for every past date said the plan was,
including reports for dates before v3 existed.

It now takes `as_of` and drops any approved version whose `approved_at` falls
after it, the rule `driftless/pmbok/mapping.py`'s `_approved_baseline()`
already applied — so the two implementations of that one rule stopped saying two
different things. `as_of=None` remains as a second, deliberately permissive
reading: newest approved regardless of when approval was recorded, which is
the *live* view the re-baseline write guard needs, because refusing a second
approved baseline must see every approval right now or a stale `as_of` sneaks
one past the 409.

That default is the remaining risk, and it is policed rather than trusted:
`tests/test_baseline_selection.py` walks the package for every call passing no
`as_of` and compares them as an exact set against written reasons, so a new
caller cannot join silently and a reason that stops applying fails just as
loudly. That set now holds exactly one entry: the re-baseline write guard in
`driftless/web/wizard_pages.py`, which is meant to read live and says so. The four
report surfaces that once sat beside it — two in `driftless/report/gather.py`,
one in `driftless/web/home.py`, one in `driftless/web/views.py` — each pass
their own date, so the pages see the as-of the function does.

Threading the swept S-curves needed more than an argument. `gather.snapshot_sweep`
hoisted one plan selection out of its per-date loop, which is what made a
dashboard render cost tasks + samples instead of tasks × samples. Once the plan
depends on the date, that hoist quietly flattened a whole curve onto one
version. It now adapts once per *distinct baseline* the sampled span crosses
rather than once per span or once per sample — an approval landing mid-window
costs one extra adaptation, not one per point. The pins in
`tests/test_gather_sampling.py` that hold the sweep byte-equal to the canonical
per-date adapter were themselves blind to this until then: every fixture in
that file left `approved_at` unset, so no sample date could ever resolve to a
different plan, and the pins passed for a reason unrelated to the one they
exist for. They now carry a mid-span approval.

**Scorecard thresholds — closed.** `ScorecardMetricDefinition` used to store its
thresholds, `direction` and `cadence_days` as plain mutable columns, read live
when grading — so editing a threshold regraded every past observation, a metric
green in March reading red in August because someone tightened the band in July.
The row is now a **versioned definition**: `effective_from` joins
`(objective_id, name)` on its identity, and a PATCH of any grading input is
*refused* rather than silently dropped, so a change is a new dated row, never an
edit to one a report has already rendered from.
`assess.adapters.metric_definition_as_of` picks the version in force —
`plan_baseline`'s structural twin, and like it, `as_of` picks the standard for
the whole render rather than one per datum.

Two call sites cannot go through `plan_baseline()` at all: they choose in SQL,
over rows nobody has loaded. `driftless/web/gantt.py`'s schedule route builds a
`func.max(Baseline.version)` scalar subquery over approved rows;
`driftless/web/heatmap.py` folded a subquery by ascending version so the last
row seen per task wins, and kept it at module level, built at import — where no
`as_of` exists to consult. Neither inherited the fix above, so both are gated
instead on `adapters.approved_as_of()`, one predicate expressing the same
approval-date rule for the query side, beside the selector that expresses it
for the loaded side. Two bindings of one rule, not two rules: the heatmap's
subquery became a function of `as_of` to reach it.

That predicate compares instants — `approved_at` strictly before midnight
ending `as_of` — rather than truncating the column to a day. The two are the
same answer for the naive timestamps this column stores, and the plain compare
is the same answer in *every* SQL dialect, which matters because the test suite
runs on SQLite and a deployment runs Postgres, and the one CI job that speaks
Postgres runs the migration tests and no application query. It also leaves the
column bare, so an index on it stays usable.

## Effective time boundary

Two kinds of date live in this schema. **Effective (business) time** is when
something became true in the world the project describes: `CostEntry.incurred_on`,
`StatusSnapshot.taken_on`, `Issue.raised_on`, `ChangeRequest.raised_on`,
`QualityMeasurement.measured_on`, `Baseline.approved_at`, `SignOff.as_of`,
`TechniqueRun.as_of`, `Impediment.raised_on`/`resolved_on`,
`WorkRequest.raised_on`/`started_on`/`done_on`,
`RecurringWork.last_completed_on`/`next_due_on`, `Incident.raised_on`/`resolved_on`,
`EstimateScenario.as_of`.
**Recorded (system) time** is when Driftless's own database learned about it:
`ChangeLog.changed_at` and `SignOff.signed_at`, and `TechniqueRun.run_at`.

**Decision:** as-of reporting filters on effective time only. Recorded time
answers "who wrote this row and when", the question an audit trail exists
for; it never answers "what was true as of this date", the question a report
exists for. Conflating them was the bug in baseline selection above — a bare
`max(version)` implicitly asks "which version has been created" instead of
"which version was approved by this date", which is why the fix filters on
`approved_at`, an effective-time column, and not on when the row was written.

**Decision:** domain rows do not get their own `created_at` column.
`driftless/db/changelog.py`'s `ChangeLog` is append-only and already records
every insert, update and delete with a `changed_at` timestamp and an `actor`
— its module docstring states "nothing here updates or deletes a ChangeLog
row." A second timestamp on the domain row would duplicate that fact in a
place a bug could edit it independently, and nothing would say which of the
two disagreeing values was the true one.

## Record classification boundary

Three kinds of record answer "does as-of apply, and how":

- **Events**, append-only and immutable once written. Metric observations,
  sign-offs and approved baselines already work this way: `driftless/api/app.py`
  registers `/metric-observations` and `/sign-offs` with a create and a read
  route only, no patch or delete, and refuses any write to a baseline once its
  `status` is `"approved"` or its `approved_at` is set. Status snapshots,
  quality measurements and cost entries are decided into this category too and
  are registered the same way — create and read, no patch, no delete.
  `TechniqueRun` is the same shape again: `driftless.services.technique_runs
  .record_run` is its only writer, and there is no update or delete path. A
  correction to one of them is a new row, never an edit to the row a report
  has already been rendered from. For `CostEntry`, that row takes a specific
  form: a reversing row carrying the wrong amount negated, plus a new row
  carrying the correct one — standard ledger practice, not a fresh invention
  per correction. `amount` is therefore not `>= 0` (see
  `driftless.models.records.COST_ENTRY_AMOUNT_BOUND`, a symmetric sanity
  range in its place); an as-of sum over `incurred_on <= as_of` then lands on
  the corrected figure at every date on or after both rows, with no flag a
  reader could forget to filter on. `StatusSnapshot` takes a different form
  again, because it does not sum: a wrong reading is a wrong single number for
  that day, not an amount to reverse. `uq_status_snapshot_project_date` used
  to make a second row for an already-snapshotted date an `IntegrityError`,
  leaving an append-only table no way to correct one at all. **Decision:** a
  second snapshot for an already-snapshotted date is now accepted, and the
  most recently RECORDED one — the higher `id`, not `taken_on` order, which
  two same-date rows now share — answers every "latest reading" read, with no
  backward link naming the row a correction supersedes (`ChangeLog` already
  records who filed which row and when). Two same-date rows CAN disagree now,
  so every reader of the *series*, not just a single "latest" pick —
  `driftless.web.views.trend_series` — must resolve the tie the same
  deterministic way, rather than let query return order decide.
- **Versioned definitions**, a sequence of dated, superseding rows, each the
  plan of record for the dates it covers. Baselines are already this, keyed
  on `Baseline.version`. Metric definitions and their thresholds are this too,
  keyed on `effective_from` — a threshold that mutated in place was exactly
  the second break named above.
- **Current state**, mutable and not as-of tracked, because nothing records
  what it looked like on an earlier date. Hierarchy, tasks and risks are this
  today, and so are users. `ProjectRole`, `Release`,
  `DefinitionOfDoneItem` and `Impediment` join them, and so do the department
  operations records: `DepartmentService`, `WorkRequest`, `RecurringWork`,
  `ServiceLevel`, `OperatingControl`, `Incident` and `Improvement`, and the
  schedule records: `TaskDependency`, `ProjectCalendar`, `CalendarException`
  and `EstimateScenario` — a later estimate does not correct an earlier one,
  it is simply a second row, but nothing here answers "what did this
  network/estimate look like as of an earlier date" the way a baseline does.
- **Current state carrying its own effective-time dates.** `BacklogItem` is mutable
  like the rows above, but stores the three dates every flow metric reads —
  `created_on`, `started_on`, `done_on`. `pmbok.flow_facts` used to derive them from
  `ChangeLog.changed_at`, which is system time, so a store seeded, imported or restored
  today and read at an earlier `as_of` had nothing to replay and reported zero throughput
  and zero durations. That replay is still the fallback for a row whose `created_on` is
  null, so an existing store reads as it always did.

## Baseline visibility boundary

An approved baseline whose `approved_at` is `NULL` is visible at every
`as_of`, never filtered out — `driftless/pmbok/mapping.py`'s
`_approved_baseline()` already treats it that way, its
`approved_at is None or approved_at.date() <= as_of` filter reading a null
`approved_at` as "always in view", not "never in view." Affirming it here
matters because the rule is now written in three places — that filter,
`adapters.plan_baseline()` and `adapters.approved_as_of()` — and they must
answer alike on a null; unifying them further must not silently change it.

`mapping.py`'s copy stays a copy, and that is now a decision rather than a
backlog item. Folding it onto `plan_baseline()` was tried and measured: it
reintroduces the per-project query `mapping.prefetched`'s batched read exists to
prevent, because `plan_baseline()` reads `project.baselines` — a relationship
that is lazy on every walk loading projects without `eager_project()` — and
`business_process_cells` went to 27 statements against a recorded ceiling of 19.
What folded is the RULE, not the read: the same `max(version)` pick, and
`tests/test_process_state.py` now holds the two to the same answer across a
draft/approved/dated/undated mix on both sides of the approval date. The copy
that cannot go away cannot drift either. Whether a baseline may reach "approved"
with no `approved_at` at all is a separate question, deliberately not answered by
this record.

## Hierarchy boundary

Moving a project between portfolios or programs rewrites every historical
rollup that project fed, because `driftless/models/hierarchy.py`'s
`Portfolio`, `Program` and `Project` carry a plain mutable `portfolio_id` /
`program_id` foreign key with no effective-dating column — there is no "as of
this date, this project belonged to this portfolio" to consult.

**Decision:** hierarchy stays current state, not as-of tracked, matching the
record classification above. Recording the limit here rather than leaving it
implicit means a reader who asks "why did last quarter's portfolio total
change" has a documented answer — the project moved — instead of a silent
discrepancy.

## Organization boundary

Driftless enforces exactly one trust boundary today. Business is a grouping
inside the hierarchy, not an access boundary: `driftless/models/auth.py`'s
`User` and `ApiToken` carry no business foreign key, and `business_id` shows
up only as a parent that must exist (`driftless/api/app.py`, at registration)
and as a hierarchy-integrity check (`driftless/api/rules.py`) — confirming a
department or a linked objective belongs to the same business as the project
it is attached to, never as a filter on who may read or write it.

**Decision:** keep the single trust boundary. Role tiers, decided separately
in `docs/decisions-superseded.md`, sit inside this one boundary rather than
beside it. Business-scoped tokens wait until a second tenant actually exists
to need one — a scope nobody enforces is a scope that rots into a false sense
of isolation.

## Reproducibility receipt and evidence age

Two computed pages — the weekly status form (`driftless/web/status.py`) and
the project hub (`driftless/web/project_hub.py`) — carry a footer stamped by
`driftless.web.receipt.attach_receipt`: the page's own as-of, the schema
revision this build expects (`driftless/db/schema_version.py`'s
`EXPECTED_REVISION`), the git SHA it was built from (an env override,
`DRIFTLESS_GIT_SHA`, or `git rev-parse HEAD` against the checkout, or
`"unknown"` for a packaged install with neither), and a sha256 of the page's
own rendered content. **The hash covers the response body exactly as it stood
before the footer was inserted** — never the footer itself — so a reader who
strips the receipt paragraph back out of a saved copy of the page and rehashes
what remains gets the value the receipt printed. Byte-identical regeneration
at a pinned as-of (this document's own boundary, above) is what makes that
hash reproducible run to run.

Both pages also show the evidence age behind the figures they compute:
`driftless.calc.evidence_age.evidence_age(page_as_of, dates)` takes the newest
of a set of record dates that is still on or before the page's own as-of, and
reports how many days old it is — "computed from evidence as of 2026-09-14, 8
days old." The status page reads it off every status snapshot's `taken_on`
and every cost entry's `incurred_on`; the hub reads it off cost entries alone,
since that page's evidence line sits beside its earned-value figures
specifically. A date after the page's own as-of is excluded rather than
clamped — evidence a page could not yet have seen must not appear to make its
figures look fresher than they are.

The same receipt reaches the two other surfaces that leave the browser.
`driftless report all` (`driftless/report/cli.py`) appends the receipt to
every markdown document it writes, as a trailing `<!-- receipt: … -->` line —
invisible wherever the markdown is viewed, and outside what any Jinja template
renders, so `tests/test_sample_content.py`'s section assertions never see it.
`driftless.report.receipt.verify_receipt` re-hashes everything before that
line and compares it against the digest the line names; a reader (or
`driftless pmbok proof reproduce PATH`, which reads a saved report or page
straight off disk and detects markdown vs. HTML from its content, never the
extension) checks a saved document the same way. Every `?format=csv` export
(`driftless/api/export.py`)
carries the same schema/build/digest triple in an `X-Driftless-Receipt`
response header rather than in the body — a trailer row would round-trip
through `bin/driftless-import.py`'s `csv.DictReader` as a bogus record, where
an HTML comment in a markdown file round-trips through nothing. All three
surfaces share one implementation, `driftless.calc.receipt`, so the git-SHA
resolution and the sha256 digest are computed exactly one way.

## Provenance links

The same two pages link every computed figure to the rows it was computed
from, rather than asking a reader to take the number on faith. The
percent-complete trend and RAG on the weekly status page link to
`/projects/{id}/status/inputs`, a read-only page listing every
`StatusSnapshot` row the trend is swept from — in the same unfiltered,
recording-ordered set `status_form` itself reads, so the two can never
disagree about which rows feed the chart. The EVM figures on both the status
page and the hub (EV/CPI/SPI/EAC/CV/SV) link to `/projects/{id}/hub/costs`, a
read-only page listing every `CostEntry` with `incurred_on <= as_of` — the
same bound `calc.evm.actual_cost` applies, so the rows shown are exactly the
ones the actual-cost figure was summed from, never the project's whole cost
history. Both inputs pages carry the reproducibility receipt and render no
wall clock, so a pinned as-of regenerates them byte-identically like every
other computed page.
