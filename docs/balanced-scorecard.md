# Balanced scorecard decision record

**Status:** accepted for the next dashboard increment (2026-08-12).

## Decision

Driftless will present a balanced operational scorecard, not a single business
health number and not a finance-only dashboard. Each project, program,
portfolio, and business gets the same five lenses, calculated as of the page's
`as_of` date:

| Lens | Decision question | Initial evidence already in Driftless |
|---|---|---|
| Delivery | Will we deliver the agreed work when promised? | schedule SPI/slip, milestones, baseline and task progress |
| Financial stewardship | Are we controlling approved investment? | BAC, AC, EV, CPI, EAC, VAC |
| Quality and risk | Is the result fit for use and exposure controlled? | direction-aware quality metrics, risks, issues, assessed threats |
| Stakeholder and customer | Are the people affected engaged and informed? | stakeholder influence/interest, communications freshness, status reporting |
| People and capability | Can the organization sustain the work? | department ownership, assignees, capacity, allocation, lessons learned |

Every lens shows three facts together: its derived RAG, the evidence freshness
or coverage, and the action or drill-down it recommends. A missing or stale
signal is visible as **unknown**, never converted to green or hidden inside an
average.

There is deliberately no default weighted composite. A red quality, safety, or
stakeholder concern must remain legible even when cost is green. If leadership
later needs a composite, it must be a named, versioned policy with disclosed
weights, mandatory minimum coverage, and a drill-down to every source signal.

## Configuration boundary

The configuration hierarchy is the existing real data model, exposed as an
administrative journey rather than an implicit prerequisite:

1. Create a **business** and its portfolios/programs/projects.
2. Create **departments** and people; assign each project a responsible
   department and delivery contributors.
3. Configure project delivery mode, baseline, workstreams, milestones, and
   quality metric definitions.
4. Record the live evidence: status snapshots, cost, risks/issues/changes,
   stakeholder cadence, quality readings, agreements, and narrative artifacts.

The Organization configuration page now makes these steps discoverable: it
counts each durable layer, marks missing business, delivery, ownership,
objective, metric, evidence, and project-link layers as **Needs setup**, and
links to the existing Scorecard and department surfaces. It must not introduce
a second configuration store or a parallel “department/project” taxonomy.

## Strategic objective boundary

The first scorecard domain record is a **StrategicObjective**, scoped to one
business and assigned to exactly one of the four stable perspectives:
Financial, Customer & Stakeholder, Internal Operations, or People & Capability.
It carries an owner, active window, and lifecycle status. Metric definitions
and project contribution links will attach to this durable root in subsequent
slices; no free-form formula or cross-scope objective is accepted in v1.

Each objective can own named **metric definitions**. A definition gives the
direction, target and amber/red thresholds, reporting cadence, accountable
owner, and a source boundary. Sources are either manual evidence or a named
registered connector; a connector key is not executable configuration and
cannot carry credentials or arbitrary formulas.

Connector keys are accepted only after a business-scoped source registry entry
is active. The registry stores a key, name, description, and lifecycle status;
adapter credentials and execution details remain outside scorecard records.

Metric observations are append-only dated evidence. Corrections are recorded as
a new observation instead of rewriting history, so each scorecard reading can
be reproduced as of its reporting date and traced to its evidence note.

The evaluator selects the latest observation at the report's `as_of` date. It
returns `unknown/missing` when no evidence exists, `amber/stale` when an
in-tolerance reading is older than its cadence, and `red/measured` when a value
is outside its configured band. These are derived results, never stored status
fields, so late evidence cannot rewrite a historical report.

The website exposes this read model at **Scorecard** in the primary navigation.
It keeps Financial, Customer & Stakeholder, Internal Operations, and People &
Capability visible together, with a Configuration link — under Organization in
the primary navigation — for missing setup. The existing Dashboard remains the
delivery/EVM view; the Scorecard is the balanced strategy-and-evidence view.

Projects can now be linked to an objective as **direct** or **supporting**
contributions. The link is business-scoped, named on project/objective delete
guards, and shown on the Scorecard so an outcome has an auditable path back to
delivery work. The project hub now repeats those active lenses in the project's
operating workspace, including each objective's derived metric status and
coverage. A project with no links gets an explicit unknown state and a path to
the balanced Scorecard, so strategy context is never hidden behind the money
dashboard.

## Bringing OKR data from a retired tool

Microsoft retired Viva Goals on 2025-12-31, leaving its objective/key-result
data with nowhere to live. `driftless import viva-goals <file.csv> --project
P [--dry-run]` (`driftless/interchange/viva_goals.py`) reads a Viva Goals OKR
CSV export and lands its objectives and key results onto the project's
business scorecard, through the same validated write path every other
scorecard write already uses.

The export's column layout — `driftless.interchange.viva_goals.VIVA_COLUMNS`
— is based on the Viva Goals OKR export columns as documented publicly;
unverified against a live export — adjust `VIVA_COLUMNS` if yours differ. A
column this module does not name is ignored; a required column missing from
the file refuses, naming it. Viva Goals has no equivalent of a scorecard
perspective, direction, cadence, or amber/red tolerance band, so every
imported row gets the same documented default in that module rather than a
per-row guess. Re-importing the same file is idempotent: an objective, metric
definition, or observation already present is left alone, never duplicated.
`--dry-run` reports the counts it would create without writing anything. A
small invented sample export is at `tests/fixtures/interchange/viva-goals-sample.csv`.

## Delivery sequence

1. Add the scorecard read model, using assessment coverage and freshness before
   any new UI chrome.
2. Add a project scorecard to the hub; link a lens to the source record or
   corrective action.
3. Add rollups at program, portfolio, and business level, preserving each lens
   rather than averaging away a red child. Portfolio and program drill pages
   now show the four perspective rows for their descendant projects; the
   business Scorecard remains the complete objective-level view.
4. Add the configuration journey and empty-state guidance.
5. Publish the deterministic scorecard and configuration pages in the headless
   showcase so a design review can inspect the balanced model without a live
   database or browser automation.
6. Only then evaluate optional metric weighting with a decision record and
   policy/audit model.

## Acceptance checks

- A project with no financial baseline can still show delivery, people,
  stakeholder, quality, and risk evidence.
- A missing metric says unknown/missing with a link to configure it.
- A lower-is-better, higher-is-better, and target-band quality metric all have
  unambiguous pass/fail semantics.
- A department, project, or metric created through the web/API path appears in
  the scorecard without a separate sync.
- All scorecard figures stay derived, as-of reproducible, and traceable to
  source records.
