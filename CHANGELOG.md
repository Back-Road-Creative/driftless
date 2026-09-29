# Changelog

All notable, user-visible changes to svc-driftless, newest first. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version
is the one in `pyproject.toml` / `driftless.__version__`.

Every user-visible change still ships its entry **in the same PR** that makes
the change — an entry written later is an entry written from memory — but as a
fragment file in [`changelog.d/`](changelog.d/README.md), never as a direct edit
here: two open PRs appending to the same list collide on the same lines, two
fragment files cannot. `bin/assemble-changelog.py --release <version>` folds the
fragments into this file at release time.

## [Unreleased]

## [0.8.0] - 2026-09-27

### Added
- `release.yml` now builds and validates the showcase bundle at the tag with `bin/driftless-showcase.py`, uploads it as `driftless-showcase-<tag>.tar.gz` on the release, and mirrors the tag, release and asset to the public repository (automating `docs/release-publishing.md`'s snapshot procedure) whenever a `DRIFTLESS_PUBLIC_TOKEN` secret is installed. Absent the token the mirror is skipped with a visible warning and the archive-side release still publishes.

### Changed
- `sqlalchemy` is now declared `>=2.0,<2.1`, the line `requirements.lock` proves, so a new SQLAlchemy major line reaches the strict type check only through a deliberate lock bump rather than on its PyPI release date (2.1.0 broke `mypy --strict` on staging the day it shipped).

### Fixed
- The org's leak scanner now checks every release before anything is published: in
  CI on each pull request, and in its own release step on the exact snapshot the
  mirror commits, so a finding stops the release before any commit or push to the
  public repository. The scanner runs at a pinned commit with no token in its
  environment, and the public repository's `leak-scan.yml` now checks a push to
  any branch, not only to `master`.
- The public repository's CI now runs. Every workflow asked for a self-hosted
  runner, which a public repository cannot use, so there every job waited in the
  queue and never started, including the checks on a release's pull request. On
  the public repository, CI, the dependency audit, the image publish and the
  failure alert now run on GitHub-hosted runners, and the release, browser and
  uptime workflows do not run there. A test fails any job that would ask the public
  repository for a self-hosted runner.
- The release mirror's pre-commit file-list check no longer fails every snapshot that has a directory in it: `tar -tf` lists directories as entries of their own and `git ls-files` does not, so the check now compares files only, in both `release.yml` and `docs/release-publishing.md`.
- The release workflow's public mirror no longer pushes to the public `master`, which the self-hosted runner refuses. It pushes the snapshot to a `release/<tag>` branch, publishes the tag, release and showcase asset from it, and opens a pull request to `master` for a person to merge.
- `release.yml` installs the showcase venv as `.[dev]` under `requirements.lock`, the same install `ci.yml`'s Tests job runs. The bare `.` install left out `httpx` and resolved a `starlette` newer than the lock that refused to import, so the v0.7.0 release still built no asset.
- `release.yml` builds the showcase bundle from a throwaway venv that has installed this package (the same uv-then-pip shape `ci.yml` uses) instead of the runner's bare `python3`, which has no `driftless` package and failed the v0.7.0 release on `ModuleNotFoundError` before any asset was built or mirrored.

## [0.7.0] - 2026-09-24

### Added
- `Person.kind` ("human", the default, or "agent") binds an agent actor to the
  `ApiToken` it writes through (`agent_token_id`). `POST /sign-offs` refuses a
  decision made through an agent-bound token with `403` unless an operator sets
  `DRIFTLESS_ALLOW_AGENT_SIGNOFF=1`; a landed sign-off carries `signed_by_kind`,
  and the org heatmap marks an agent's row.
- `Note` files an append-only note against any record (`record_kind`/`record_id`),
  shown on the department drill page next to linked artifacts. A correction is a
  new note whose `supersedes_id` names the one it replaces; updating or deleting
  a note is refused both at the model layer and by the API, which registers
  `POST /notes` and `GET /notes` only.
- `ArtifactLink` files a URI reference against any record (`record_kind`/`record_id`),
  shown on the department drill page and exported like every other list at `/artifact-links?format=csv`.
- Added a baseline diff page (`GET /projects/{id}/baselines/diff`, optionally `?versions={v1}...{v2}`): per-line delta in dates, cost and scope between two approved baseline versions, each baseline's own approval record, and the change request that produced the later version, when one exists. Read-only and computed — no new model or migration. Linking a `SignOff` to a `Baseline` needs `"baseline"` added to `SIGNOFF_SUBJECTS` plus a migration, and is left for later.
- Every `change_log` row now also carries `prev_hash` and `row_hash`, chaining each row to
  the one before it; editing or deleting any row breaks the chain at that point, and
  `driftless.db.changelog.verify_chain` walks the table and reports the first break.
- Every `change_log` row now also carries `via` (`web`, `api`, `cli` or `mcp` — the
  channel the write came through), stamped once per session at each entry point;
  older rows and a caller that never set it read `via=NULL`, meaning unknown.
- Department workspace: each operating control now shows a computed RAG state — red for an open high/critical incident, amber for a lower-severity open incident or evidence older than 90 days, green otherwise — with its reasons and evidence age, never a stored status column.
- Added schedule health checks 8-14 (high duration, invalid dates, resources, missed tasks, critical path test, CPLI, BEI) as pure calculators over `driftless.calc.network.ScheduleNetwork`, alongside the first seven, via a new `assess_full` that also takes dates, resources and baseline data no `Activity` carries.
- Added the first seven DCMA 14-point schedule checks (logic, leads, lags, relationship types, hard constraints, high float, negative float) as pure calculators over `driftless.calc.network.ScheduleNetwork`.
- Earned schedule (Lipke): `earned_schedule`, `actual_time`, `planned_duration`,
  `schedule_performance_index_time`, `schedule_variance_time`,
  `independent_eac_time` and `earned_schedule_snapshot` in `driftless.calc.evm`
  compute ES, AT, SPI(t), SV(t) and IEAC(t) on top of the existing EVM curve.
- The earned-value calculator page now shows ES, AT, PD, SPI(t), SV(t) and
  IEAC(t) beside SPI/SV, computed from the same baseline and progress the
  rest of the page already reads — "no data yet" rather than a fabricated
  zero when the plan hasn't started.
- `driftless notify digest --as-of D [--dry-run]` emails the attention list to every
  `EmailSubscription` due a send, as text and HTML, over stdlib `smtplib` against an
  operator-supplied SMTP relay.
- `GET /projects/{id}/ev-series` returns one earned-value snapshot per period from the project's baseline start through `as_of` — a period series shaped for IPMDAR-style cost reporting.
- Added an MCP server (`driftless mcp serve`, no extra install) exposing the wizard loop and generic resource CRUD as tools over the same gated `/api/v1` handlers and bearer-token role gating the API already enforces, with `docs/agent-guide.md` §6 documenting and executing the same loop over MCP.
- Added `driftless export msproject` to write a project's approved baseline back out as Microsoft Project XML (MSPDI), round-tripping through the existing importer.
- OIDC sign-in (`/auth/oidc/start`, `/auth/oidc/callback`) maps an external IdP
  login to an existing local account via a new `User.oidc_subject` column, bound
  by an admin with `driftless user oidc-subject <username> --subject …|--clear`;
  no account is auto-provisioned. Configured with `DRIFTLESS_OIDC_ISSUER`,
  `DRIFTLESS_OIDC_CLIENT_ID`, `DRIFTLESS_OIDC_CLIENT_SECRET` (or
  `DRIFTLESS_OIDC_CLIENT_SECRET_FILE`) and `DRIFTLESS_OIDC_REDIRECT_URI`; the
  routes 404 until all are set. See the admin guide for setup against a generic
  OIDC provider.
- A print stylesheet (`/static/print.css`, `media="print"`) so any page prints cleanly
  in the browser — no PDF engine, no new dependency — and a Print link on every page
  carrying an as-of, whose href carries that same as-of so the printed page matches
  what was on screen.
- Added `driftless pmbok proof reproduce PATH` — reads a saved markdown report or HTML page off disk and verifies its reproducibility receipt, detecting the format from the content rather than the file extension.
- Added `driftless pmbok proof no-typed-status`, `baseline-immutable`, `forecast` and `process-state` — checkable subcommands for the wedge claims, each exiting 0 when the claim holds and non-zero with the offending rows otherwise.
- Every figure on the weekly-status and project-hub pages links to the rows it was computed from: the RAG/percent trend to its `StatusSnapshot` rows, the EVM figures to the `CostEntry` rows actual cost was swept from — each a small read-only inputs page, not a second write path.
- Extended the reproducibility receipt to `driftless report all`'s markdown documents (a trailing HTML-comment line with as-of, schema revision, build SHA and a sha256 of the document itself) and to every `?format=csv` export (an `X-Driftless-Receipt` response header, so the CSV body still round-trips through the importer).
- Added `driftless.report.receipt.verify_receipt`, which re-hashes a rendered markdown document and compares it against its own trailing receipt line.
- Added a reproducibility receipt (as-of, schema revision, build SHA, sha256 of the page's own content) to the weekly status and project hub pages.
- Added an evidence-age line to the same pages, showing the newest input date behind their computed figures and its age relative to the page's own as-of.
- Schedule network: the crash/fast-track preview now shows the current plan's finish, critical path and total cost beside the previewed scenario's, plus an EAC for each at today's cost efficiency — a read-only comparison, nothing stored.
- Team assist: a resource-clash preview on the assignment form shows the heatmap over-allocation a proposed person/task assignment WOULD cause before it is filed, with no auto-levelling.
- Added a schedule health checks page (`/projects/<id>/schedule-health`) and matching CSV export, one row per DCMA-thresholded check with numerator/denominator/ratio, pass/fail/not assessable status, and offending tasks named, linked from the project schedule page.
- Added `driftless import msproject` and `driftless import xer` to bring a Microsoft Project XML (MSPDI) or Primavera P6 XER schedule's tasks and dependencies into a project's own `Task`/`TaskDependency` rows, through the same validated write path the API uses.
- A sign-off can now reference a baseline version (`subject_kind: "baseline"`,
  `subject_ref` the baseline's id): the baseline diff page records and shows
  the approval decision, alongside a project's threats and process waivers.
  Only an `approved` or `superseded` baseline on the sign-off's own project is
  accepted — a `draft` plan has not been approved yet, so there is nothing to
  sign off on.
- A project can now define stage gates (`POST /gates`): a name, a sequence
  position, and the PMBOK processes required to pass. Readiness is never
  stored — it is computed from the same derived process states the process
  map draws, and shown alongside the gate's own sign-off ledger and decision
  form on `/projects/{id}/gates`. A gate sign-off is refused while the gate
  is not ready, unless the decision is `waived` — the sanctioned way to
  tailor a gate out without pretending its required work is done.
- `Task` gained `actual_finish` and `forecast_finish`, so the DCMA schedule-health
  checks (invalid dates, missed tasks, BEI) have somewhere to read them from.
- `User` gained an optional `email` column (`driftless user add --email …`,
  `driftless user email <username> --address …|--clear`); the email digest now
  sends to it, falling back to an `@`-shaped username and skipping — by name,
  in the command's output — a user with neither.
- Added `driftless import viva-goals` to bring a Viva Goals (retired 2025-12-31) OKR CSV export's objectives and key results into a project's business scorecard, through the same validated write path the API uses; idempotent on re-import, with a `--dry-run` option and a sample export at `tests/fixtures/interchange/viva-goals-sample.csv`.
- A web app manifest (`/static/manifest.webmanifest`, served as
  `application/manifest+json`) so the app can be installed as a standalone PWA —
  no service worker, no offline write, no new dependency.
- `driftless notify add`/`list`/`deliver` manage webhook subscriptions and run delivery
  from the command line, cron, or a systemd timer.
- `driftless notify` manages webhook subscriptions and delivers pending `ChangeLog`
  events to them, cursor-based, with an HMAC-SHA256 signature on every request.

### Fixed
- `schedule_data` and `project_calendars` now resolve against stored `BaselineLine`,
  `TaskDependency` and `ProjectCalendar` rows instead of reading as permanently untracked;
  both are marked optional outputs of PMBOK 6.5 Develop Schedule so a project without one
  filed yet is never held short for lacking it.
- `project_schedule_network_diagram` now resolves against stored `TaskDependency` edges
  instead of reading as permanently untracked.
- Corrected stale claims in `docs/pmbok-mapping.md` and `driftless/pmbok/mapping.py`'s
  untracked dispositions: critical path method already reads real stored dependency
  edges, to-complete performance index already computes, and a `ProjectCalendar` row
  already exists in the store even though no resolver reads it yet.
- The onboarding wizard can now produce `project_schedule_network_diagram` (a
  predecessor/successor task pair and the dependency edge between them) and
  `project_calendars`, so Sequence Activities is no longer a dead end with a
  tracked-but-unproducible required output. `schedule_data` stays derived — it
  reads the same dependency edges plus an approved baseline's dated lines, with
  no row of its own to write.

### Docs
- Refreshed `COMPETITORS.md` to 2026-09-22: landed features (WBS, traceability,
  closeout, Gantt, board, heatmap, iCal, search, CSV export, critical path,
  dependencies, calendars) moved from the gap register to cited strengths, and
  the verdict points at the wedge's own symbol citations.
- Removed `docs/pmbok7-crosswalk.md`: the team works from PMBOK 8, which `docs/pmbok8-crosswalk.md` covers.
- Added `docs/pmbok8-crosswalk.md`, an editorial crosswalk from the catalog's 49 PMBOK 6 processes to the 40 PMBOK 8 processes, per two secondary sources — not PMI's own text.

## [0.6.2] - 2026-09-14

### Fixed
- The primary-nav disclosure checkbox no longer exists above the mobile
  breakpoint. It was hidden with `opacity: 0` rather than `display: none`, so it
  stayed in the accessibility tree while its label did not — a screen reader on a
  desktop viewport met an unlabelled checkbox that toggles nothing at that width.
- The release workflow now dispatches the image build with the tag it promises.
  It stripped the leading `v` from the tag input, which `docker-publish.yml`
  documents as required and checks out verbatim, so every release died at
  checkout with `A branch or tag with the name '0.6.1' could not be found` and
  shipped no image.
- `docker-publish.yml` refuses a malformed tag input before the checkout
  consumes it, so the error names the tag instead of an unresolvable ref.

## [0.6.1] - 2026-09-14

### Fixed
- The static showcase no longer exports the method map's zoom controls. Fit,
  100%, minus and plus are driven by the app's own map script, which the bundle
  does not ship, so in the export they were four buttons that did nothing — the
  same dead shape the filter strip is already stripped for.

## [0.6.0] - 2026-09-14

### Added
- Decision-tree analysis, a risk technique that was guide-only for lack of a calculator, now has
  one: a no-write EMV what-if (`/projects/{id}/assist/decision-tree`) marking the best option.
- A glossary term whose product has one obvious home page for it now carries a
  "Where you meet it" line under its definition, linking straight there — the
  technique, artifact, or method page a reader actually meets the term on, or
  the reference index for a structural PMBOK concept like knowledge area or
  process group. Left off entirely where no single page is the obvious home.
- The glossary page now offers an A-Z jump (only for letters that actually have
  entries), a filter box that narrows the list as you type, and a back-to-top
  link after each letter group. All three are plain HTML anchors or
  progressive enhancement -- every term stays visible and reachable with
  JavaScript switched off.
- The method map now says what "washing" a node means in plain language,
  wherever the page uses the word, instead of leaving its own jargon
  unexplained. The project-washed read also links back to that project's
  onboarding wizard, matching the process map's own row of sibling links —
  the wizard already linked forward to the map, but nothing linked back.
- The method map's filters (chips, search, flow-only) now round-trip through the
  URL, so a filtered view is a link you can bookmark, reload or share; and the
  "Showing N of M nodes" sentence updates live as a filter narrows the map,
  instead of only reflecting the count at first page load.
- The method map's legend now explains state marks too, once a project washes the
  picture — the same rows `/projects/{id}/process-map` legends, never a second
  vocabulary. An always-present "How to read this page" block orients a first-time
  reader, and a Related block anchors the picture back to `/pmbok`, `/techniques`,
  `/artifacts`, `/process-map` and the washed project's own process map.
- The method map's lines now carry a `<title>`, and a node's own panel lists
  every tie it is the source of — hovering the line or opening either end
  gives the same plain-English sentence, as the user guide already promised.
- A node's `<title>` now names its process group and knowledge area (or its
  technique family), so a screen reader reaches what the band caption and the
  fill colour otherwise carry alone.
- Added the shared building blocks for the Method pages' "How to read this page"
  help block and a printable, checkable worksheet form, with one real worksheet
  (rolling wave planning) proving the registry. Not yet shown on any page.
- The technique library's index now says what each family of techniques is for, and
  gives every technique a "how much help" column — runnable here, a printable
  worksheet, or the recorded reason this product explains it rather than running it —
  so a reader can tell which techniques are runnable without opening them one by one.
  A key above the tables names the three tiers and counts how many techniques sit in
  each, and a "How to read this page" note explains the grouping.
- Every cross-cutting general-family technique that stays guide-only now carries a
  printable worksheet — expert judgment, the data gathering, analysis, representation
  and decision-making umbrellas, the communication concepts, interpersonal and team
  skills, project reporting and the project management information system. Each says
  what the sheet is for, gives prompts a person can answer in a room, and names what
  the filled-in sheet produces.
- Added printable worksheets for the schedule, quality and resource techniques
  that have no calculator behind them — dependency review, design for one
  concern, problem solving, improvement cycles, test and inspection planning,
  product evaluation, influencing and resource negotiation.
- Every risk-family technique that stays guide-only now carries a printable
  worksheet — decision trees, influence diagrams, prompt lists, ranges for an
  uncertain number, risk categorisation, sensitivity analysis and the inputs a
  quantitative simulation would need — as does the stakeholder family's ground
  rules. Each says what the sheet is for, gives prompts a person can answer in a
  room, and names what the filled-in sheet produces.
- The three integration techniques no assistant can run — change control tools,
  information management and knowledge management — now each have a printable
  worksheet. None of them is a calculation, so the honest offer is a page a team
  can take into a room and fill in: what the change actually touches downstream,
  where a record lives and who refreshes it, and who holds knowledge nobody else
  on the project has. The worksheets print and read aloud without any script.
- The procurement techniques that no calculator can serve — advertising a purchase, running a
  bidder conference, logging a disputed claim, inspecting and auditing a supplier's work, and
  reviewing a supplier's performance — each now come with a printable worksheet, so a technique
  with nothing to compute still arrives as something you can fill in on paper.
- Every subsidiary management plan's page under `/artifacts` now prints a blank
  template of the document itself — its sections, the fields each one holds and a
  line of guidance saying what belongs in each — so a reader can see the shape of
  the plan they are being asked for instead of only reading about it. Where this
  product tracks the plan, the template also names the record a filled-in copy is
  read back from. It needs no scripting and prints on paper as a worksheet.
- A method's page now glosses its summary and each practice's summary the same way
  every other detail page does, linking a term's first mention to the glossary
  instead of leaving it unexplained. It also carries its own working material now —
  a sprint-planning agenda and a Definition of Done checklist for Scrum, a
  board-policy template for Kanban — newly authored for Driftless rather than a
  quote or close paraphrase of either guide, and Kanban's page links `?project=`'s
  own board when a project is in scope. Scrum has no matching view of its own yet,
  so its page never fabricates one.
- A **Method** page at `/method` gathers the section's seven surfaces — the process
  reference, techniques, methods, artifacts, the glossary, process status and the map
  — as one card each, saying what it is for and how much it holds, counted off the
  registry behind it rather than typed. The nav's "Method" label and every breadcrumb's
  "Method" crumb lead there instead of nowhere, the pair beside it reads "Process
  status" and "Method map" so each says which it is, a project's own process map lights
  Process status, every breadcrumb names itself to a screen reader and marks the crumb
  you are on, and the stakeholder worksheet keeps your as-of on the way back.
- `/map` now reads `?from=&to=` — the shortest `feeds` path between two
  processes, drawn as its own narrow slice — and `?group=`/`?area=`, narrowing
  the drawing to one process group or one knowledge area on its own. A node's
  own link now carries the same `?as_of=&project=` wash the map was drawn
  with, so clicking a process off a washed map lands on the washed page
  instead of the unwashed one.
- Every Method-cluster page (PMBOK reference, techniques, methods, artifacts, glossary,
  the business process map, and the method map) now carries a breadcrumb trail back to
  Dashboard and Method, instead of an inline back-link or none at all; a project-scoped
  drill (``?project=``) roots the same page under its project instead.
- The PMBOK reference index now explains how to read itself: a "How to read this page"
  block defining ITTO, predictive, knowledge area and process group (the last two read
  from the glossary registry rather than retyped), a legend for the three support words
  its cells print, a real link to each project's own process map instead of a theory-only
  dead end, and a Related strip to the rest of the method reference.
- A method's practice list can now say more than what a practice IS: a
  hand-picked set of events, cadences and policies — Sprint Planning, the
  Daily Scrum, Sprint Review, Sprint Retrospective and Definition of Done for
  Scrum; Visualize the Workflow, Limit Work in Progress, Manage Flow, Make
  Policies Explicit, the Kanban Meeting and the Replenishment Meeting for
  Kanban — now carry a "Running it well" and "Going wrong looks like" section
  on the method's detail page, sourced from a new `practice_content` module.
  A practice with nothing useful to add gets no such section rather than
  filler.
- The Communications and Risk process pages now carry a worked example and a
  list of first-timer pitfalls, the depth Integration and Scope already had.
  Each area's example follows one small project the whole way through, so the
  three communications pages read as one story and the seven risk pages as
  another. Procurement and Stakeholder land theirs in a follow-up change.
- Every Cost, Quality and Resource process page now carries a worked example and a
  list of common first-timer pitfalls, the depth Integration and Scope already had.
  The "How driftless helps" section on those pages needed no new writing: it is
  derived from the technique and wizard registries the page already links to.
- Every Schedule, Procurement and Stakeholder process page now carries a worked example
  and a list of common first-timer pitfalls, the depth Integration, Scope, Cost, Quality
  and Resource already had. All three areas follow the same branch-library renovation the
  other pages use, so a reader moving between areas is following one project rather than
  meeting a new one on every page.
- A process page now explains the step before it lists anything: why it matters,
  what done looks like and a first-time tip — three fields the process-content
  registry has always filled for all 49 processes and no page ever showed — with
  the terms in its summary linked to the glossary, and the shared "Related" block
  at its foot linking the processes it feeds and is fed by, its knowledge-area and
  process-group siblings, its techniques and artifacts, and the Scrum or Kanban
  practices that cover it. Opened from a project's map it carries that project and
  the pinned as-of onto its ITTO and map links, so the next hop is still about that
  project instead of dropping the reader back into theory.
- A process page now carries a worked example, a list of first-timer pitfalls,
  and a "How driftless helps" section naming which of its techniques this
  product can already run and which of its outputs the wizard can already
  produce — derived from the same registries the rest of the page links to.
  Integration, Scope and Schedule have this depth today; the remaining seven
  knowledge areas land it in follow-up changes.
- The totality proof page (`/pmbok/proof`) links every gap member it lists --
  a technique, an artifact kind, a process or a method practice -- to its own
  page, instead of printing the bare catalog key as plain text.
- The user guide now explains the breadcrumb trail and how following a
  project's own process map onto a Method page (`?project=&as_of=`) switches
  that page's breadcrumb and adds the project's own reading, alongside the
  reference material.
- Every artifact page now ends in the shared "Related" block: the processes that make and
  read the kind, the bundle it is a named part of and the parts of its own, the agile
  evidence that can stand in for it, the rest of its family, the techniques its producing
  processes use, and the map focused on it.
- Added `driftless/web/related.py`, one shared "Related" block builder starting with a
  process page (`for_process`), and the `_related.html` macro that renders it. Not
  adopted on any page yet — a later PR wires it onto `/pmbok/{id}`, and technique,
  artifact, method-practice and glossary-term coverage follow over the same shape.
- Every technique's page now ends with a computed "Related" panel: the processes that use
  the technique, the rest of its family, the artifacts those processes produce, and the
  Scrum or Kanban practices that crosswalk to it. It is worked out from the registries
  rather than written page by page, so a technique no process names still links to its
  own place on the map.
- A method practice and a glossary term each carry the shared "Related" block: a
  practice links the processes and techniques its crosswalk names, what those
  processes work with, and the method's other practices of the same kind; a term
  links every process, technique, artifact and practice whose own words use it,
  read off a reverse index of the glossary built once at import. Terms now match
  on whole words there, so "EV" is no longer found inside "every".
- Risk probability × impact assessment, a technique that was guide-only for lack of a
  calculator, now has one: `/projects/{id}/assist/risk-pi` places every open risk on the
  standard 5×5 matrix and ranks them by score, read-only.
- The probability × impact page now carries the same "Where this comes from"
  reference card as its sibling assistant pages, citing PMBOK-6 process 11.3
  (Perform Qualitative Risk Analysis) and the Risk Probability and Impact
  Assessment technique. It prints no as-of date: a risk row carries none, so
  the date on this page filters nothing and would mislead a reader who saw it
  cited as a source.
- `/search` now finds PMBOK processes, techniques, artifacts, glossary terms and
  Scrum/Kanban practices too, alongside the existing portfolio, program, project,
  workstream, task, risk and issue rows — a Method-cluster hit needs no project.
- The technique detail page now links forward instead of dead-ending: a
  "Runnable here" support tier links to the technique's assist page when
  `?project=` is on the URL (never fabricated for a technique with no assist
  route, and never guessed at without a project), a run's `process_id` links
  to that process's own page, and the page `<title>` is qualified with
  `— driftless`, matching every other Driftless detail page. An unknown
  `?project=` id now 404s, the same way `/pmbok/{process_id}` already
  rejects one, instead of rendering as an empty run list.
- A technique's Steps now render as a checkbox list rather than plain numbered
  prose, so a reader can actually work through them on the page (or on a
  printed copy) instead of just reading a list. Arriving at a technique page
  with `?project=` now shows the same live project breadcrumb and back-to-hub
  link the PMBOK and artifact detail pages already carry, instead of stranding
  the reader in theory mode with no way back to the project they came from.
- A technique page with no PMBOK-6 clause number now says why *that* technique has
  none — narrative rather than a numbered clause, an umbrella group whose members
  carry the numbers, a tool of nearly every process — instead of the same general
  sentence on every one of them. The wording is the reason already recorded beside
  the technique, printed as written. Where that reason quotes the clause number that
  was found and ruled out it is held back, because a page for an uncited technique
  must never show a clause number a reader could take for the citation.

### Changed
- `requirements.lock` follows the grouped pip bump it constrains: psycopg and
  psycopg-binary to 3.3.5, pydantic to 2.13.5, pydantic-core to 2.46.5 and
  uvicorn to 0.52.4. Dependabot compiles `requirements-runtime.txt` and leaves
  the constraint file behind, so the two named different versions and the image
  would have shipped a set pip-audit never scanned —
  `tests/test_image_dependency_parity.py` is what noticed.
- An artifact's page carries the project and as-of it was reached with onto its
  "Made by"/"Used by" process links, and links back to that project's process
  map, so a reader who arrived from a live project is never dropped back into
  theory mode on the first hop. An untracked artifact's own page now also says
  why the store never resolves it, the same disposition sentence the catalog
  index already gives it.
- The "Where this comes from" provenance card on every assistant page now renders
  collapsed beneath the computed cards, so the figures a reader came for keep the
  page's visual weight instead of competing with a reference footnote.
- The business process map's intro now says what a "washed" grid cell means — the
  cell's background colour is tinted according to the share it reports, and a
  bigger share reads as a stronger tint — instead of leaving the word unexplained.
- The method map's shapes/lines explainer is now collapsed under its own "How
  to read this map" `<details>`, so the drawing the page exists for is not
  pushed below five paragraphs, 28 chips and 19 legend rows of prose first.
- The user guide now says which line every tie on the method map is drawn with. It described
  four of the five dash patterns; `part_of` was drawn but never explained, and `feeds` was
  named by a different verb than the page uses. A test ties the passage to `EdgeKind`, so a
  new kind of tie cannot reach the map undescribed.
- On `/map`, a `feeds` tie between two processes in the same row no longer draws a
  straight line through every process box shelved between them — it steps above
  (left-to-right) or below (right-to-left) the row instead. Every tie now starts
  and ends on the node's own box edge rather than its centre, so a line is never
  buried under a label.
- The method map's per-node panel is now a sticky column beside the drawing
  instead of a block that scrolls away below it, and its update is announced to
  assistive tech instead of requiring a reader to go hunting for it after a
  hover or a keyboard tab.
- `/map`'s per-node panels now render only for the drawn slice instead of the
  whole catalog, cutting page weight when a `focus` or narrower `view` draws a
  handful of nodes.
- An unrecognised `?focus=` or `?view=` value now shows a notice instead of
  silently falling back to the default map with no explanation.
- The project list on `/map` is bounded to 20, with a link to the dashboard
  for the rest.
- On `/map`, a `feeds` tie now carries `optional` when every artifact behind it is
  one of the producer's optional outputs, and draws with a dashed overlay for it —
  the same treatment `produces` already had, so a tie that may not exist for
  every project no longer looks certain.
- The map's legend now explains what each kind of tie means and what the dashed
  overlay means, alongside the shape and fill entries it already had.
- `GET /map/graph.json` now carries each node's `x`/`y` (the same coordinates the
  `/map` SVG draws it at), `group`/`area` (process nodes), `family` (technique and
  artifact nodes) and `href`, so an external renderer can draw the same map from this
  route alone.
- The method map (`/map`) now scales its drawing to fit the screen instead of
  shipping a fixed pixel size — Fit is the default, with 100%/+/− buttons to zoom
  back in without ever shrinking a label past legible.
- The totality proof page no longer shows twelve bare labels and counts: every row now
  says in plain words what that check looked at and what finding anything there would
  mean — an orphan technique no process ever names, a document kind the guided
  walkthrough cannot produce, a tailoring profile that leaves a monitoring process out.
  The wording is held closed over the counts themselves, so a check added later cannot
  appear on the page, or in ``driftless pmbok proof``, as a label nobody explained.
- `/methods` explains "fully crosswalked" and "guide-only" in a sentence instead of
  leaving the coverage count to guesswork, and "crosswalked" now links to a new
  glossary entry defining what a crosswalk is.
- Below the 60rem breakpoint, the shell's primary nav sits behind a "Menu" toggle
  instead of rendering all three clusters open and stacked; every route stays a real
  link in the markup, and desktop rendering is unchanged.
- The business and per-project process maps now link the washed method map and the
  PMBOK reference, and each business-grid cell also links its process's reference page.
  The `?process=` listing on the business map has its own `#listing` anchor, which every
  grid cell link now appends, so clicking a cell lands the answer instead of leaving it
  below an 80vh scroll box. The per-project grid gets the same sticky-header,
  frozen-column treatment the business grid already had. Both pages now say one line
  about what their completion rings measure, the per-project map explains "Not tracked"
  cells and links its own sign-off form, and the empty business listing links the API
  reference instead of naming a bare `POST /projects`.
- The exported demo's `index.html` now opens with a short intro naming what the
  fixed portfolio is, its measured project count, and the one project the deep
  walkthrough is told through, with links into the Method pages (PMBOK,
  techniques, artifacts, methods, glossary, map). Any exported page carrying an
  inert "unavailable" link now says why, once per page. The map page's own copy
  no longer falsely claims the export carries no separate page per node — every
  process, technique and artifact page ships too.
- The exported demo's `index.html` now opens with its own `<h1>About this
  demo</h1>` and orientation -- the story project is a link, not just bold
  text -- before the Dashboard sample that follows it, demoted to a labelled
  `<h2>` subsection. Previously the page's `<h1>` still read "Dashboard" with
  the explainer grafted on above it, so the page disagreed with its own
  heading about what it was.

### Fixed
- Links carrying a `#fragment` (technique/artifact family jumps, glossary
  cross-references) now survive the static export instead of turning into inert
  "unavailable" text: the exporter resolves the path part to its captured page and
  keeps the fragment on the rewritten href.
- Glossary term links on technique and artifact pages now match whole words
  only -- "feedback" no longer links BAC, "expert" no longer links PERT, and
  "every" no longer links EV. Four glossary definitions are also corrected:
  BAC is revised when an approved change moves the baseline (it does not stay
  fixed forever), a process group is a logical grouping of processes rather
  than a phase, the critical path's total float is usually but not always
  zero, and WBS names the hierarchical decomposition itself.
- The method map's filter chips are now drawn only for values the current
  slice actually contains — the default overview drew a Technique chip, an
  Artifact chip and ten Technique-family chips that could only empty the
  picture, since the overview holds nothing but process nodes. "Show flow
  only" is likewise dropped whenever every drawn tie is already `feeds`, the
  one case where it hid nothing. Search now matches a shape's own name
  (`data-label`) instead of its full `<title>`, which used to also match its
  kind and, once washed, its state word.
- The method map's keyboard focus ring now carries its own colour and dash
  pattern instead of matching the `?focus=` URL ring stroke-for-stroke -- a
  keyboard user tabbed onto the node the link already highlights could not
  tell "I am here" from "this is what the URL asked to highlight". The
  legend's Process swatch is no longer a flat grey no process ever draws;
  it now shows the same knowledge-area tint a real process node wears.
- Two labels on the method map no longer print on top of each other. A
  component artifact (`part_of`) is placed on its parent's label lane, but the
  walk that assigns those lanes skipped children entirely, so the satellite to
  its right was spaced against the parent's small marker rather than the
  child's full label — `performance_measurement_baseline` under
  `communications_management_plan`, and `work_breakdown_structure` under
  `project_schedule_network_diagram`. Each parent now reserves the width of
  everything forced onto its lane. The committed sample map is regenerated to
  match, the pinned viewBox width follows the same layout change, and the map's
  tray rule — an artifact no process reaches sits below every band, never
  parked in Closing — is covered again by a constructed case now that no real
  artifact is left in it.
- The method map's two dotted ties (`is used by`, `is part of`) now repeat on
  different periods so they read apart at the edge stroke width, and every
  tie now draws an arrowhead marking which end it points to. The filter pills'
  border, checked-state fill and the band/tray striping follow the theme's
  own ink token instead of a fixed literal, so they stay visible in dark mode.
- The artifact catalog index (`/artifacts`) now marks each kind Tracked or Not
  tracked, driven off the same resolver partition the detail page already
  reads (`mapping.is_tracked` / `mapping.UNTRACKED_DISPOSITIONS`), and prints
  the disposition sentence for why an untracked kind stays that way. Each
  family heading now opens with a plain-words explanation of what the family
  groups together. Any other artifact identifier a disposition sentence names
  (e.g. "folded into schedule_baseline") is spelled out as its display name
  rather than printed as the raw registry key.
- Communications and risk tools & techniques now match the PMBOK Guide 6th
  edition: Manage Communications (10.2) no longer claims communication models,
  which belongs to Plan Communications Management (10.1) alone; Plan
  Communications Management gains communication requirements analysis, Manage
  Communications gains project reporting, and Identify Risks (11.2) gains
  prompt lists. Acquire Resources (9.3) no longer names `acquisition`, a
  PMBOK-5 technique PMBOK-6 replaced with decision making, negotiation,
  pre-assignment and virtual teams.
- Focusing a technique or an artifact on the method map now draws its neighbourhood. The map has
  always offered a focus link for every shape it draws, but only a process could actually be
  focused.
- Rolling wave planning's technique page no longer offers to build a worksheet that
  already exists. Its recorded reason said a progressive-elaboration worksheet "could
  serve this", which stopped being true when that worksheet was written; the page now
  says a printable worksheet is written for it and that nothing here computes a figure.
  A new `WORKSHEET_ONLY` reason kind records a worksheet as the honest ceiling rather
  than work still owed, and the launcher suite now fails if any future worksheet ships
  while its technique still says one has yet to be built.
- Clicking a shape on the method map now opens its own page, and Ctrl/Cmd-click, Shift-click or a
  middle click open it in a new tab or window. Every shape had always been a link, but the map
  cancelled the click, so the only way from a shape to its page was a line far below the drawing.
  A shape's summary panel now opens on hover and on keyboard focus, where it used to need a click,
  and Space on the shape you have tabbed to keeps it up while you look elsewhere.
- A method-map process neighbourhood (`?focus=`, and `.map-narrow`) spaces its
  technique/artifact satellites at their own label's width instead of their small
  dot/diamond, so revealed labels no longer overlap; the shared overview/whole-graph
  drawing is unchanged.
- A printable worksheet that names a technique the catalog does not hold is now
  rejected the moment the worksheets registry discovers it, the way the technique,
  artifact and process content registries already reject one. A typo'd key used to
  survive import and surface only as a red test in CI, even though the module said
  a claimed key fails loudly; the guarantee now lives where the promise was made.
- Display names built from a snake_case key no longer capitalize minor words
  mid-label ("Interpersonal and Team Skills", "Cost of Quality"), and
  `monitoring_controlling` and `make_or_buy_analysis` now read as "Monitoring
  and Controlling" and "Make-or-Buy Analysis" instead of losing their
  conjunction or hyphen.
- The totality proof's orphan-artifact check no longer exempts a kind just
  because the store has an honest reason not to track it: whether the store
  can save a document back is a different question from whether any process
  names it, so `development_approach` and `performance_measurement_baseline`
  are now recorded as components of `project_management_plan`
  (`artifacts.COMPONENT_OF`) — reaching the method through the plan they are
  facets of, the same way the WBS reaches it through the scope baseline —
  rather than being waved through by an exemption that answered a different
  question. The method map's tray (members no process reaches at all) now
  holds one member, `technique:critical_chain_method`, down from three.
- Validate Scope (5.5) now reads `verified_deliverables` instead of the bare
  `deliverables` list, restoring the Control Quality (8.3) feeds tie; Estimate
  Costs (7.2) now names the project documents and management plans PMBOK-6
  actually lists as inputs; Plan Procurement Management (12.1) now outputs bid
  documents and independent cost estimates; Manage Stakeholder Engagement
  (13.3) no longer claims project communications as an output; and Perform
  Quantitative Risk Analysis (11.4) now names the risk report, not the risk
  register, as its output.
- The totality proof's "Orphan method practices" row no longer runs the same
  check as "Uncrosswalked method practices" and double-counts the same gap;
  it now catches a practice whose recorded crosswalk points at a process or
  technique that does not exist.
- Method map: technique/artifact satellite labels revealed under
  `.map-narrow` no longer overlap each other or run past the map's edge.
  Every one of the 49 process neighbourhoods had overlapping labels
  before -- they're now staggered onto alternating vertical lanes within
  each satellite row, and the map's viewBox grows to fit the widest label
  actually reached. `docs/samples/2026-07-01/method-map.svg` regenerated to
  match.
- The static demo no longer links a process cell to a `#listing` fragment its exported process map does not carry; the link lands on the page itself.
- The static demo now carries the whole method graph as a page of its own, and a
  "See it on the map" link from a process, technique or artifact page opens it on
  the node it names. Those links used to flatten to the process overview, which
  draws no technique and no artifact at all and pins nothing, so the reader
  arrived at a map that had forgotten what they asked to see; the two links per
  node on the map pages themselves were dropped entirely for the same reason. With
  no script running the link still lands on that node's entry in the lists under
  the drawing, which the export leaves open so the entry can be seen.
- Several technique `further_reading` citations pointed at the wrong PMBOK-6
  Guide clause (wrong knowledge area, wrong process, or the neighboring
  bullet's number) — risk quantitative-analysis techniques, some
  communications and cost techniques, `decomposition`, `rolling_wave_planning`,
  `organizational_theory`, `ground_rules`, `stakeholder_analysis`,
  `stakeholder_engagement_assessment_matrix` and `multicriteria_decision_analysis`
  now cite the clause that actually lists them; two previously-blanked risk
  response-strategy citations are cited now that the correct numbers are
  known. Also corrects the Control Resources summary (physical resources
  only, not people) and the `agreements_initial` artifact description
  (agreements with the customer/sponsor, not pre-contract seller talks).

### Docs
- The user guide's Method-page section (§8a–8j) now gives each PMBOK, technique,
  method, artifact, glossary, process-map and method-map page its own numbered
  subsection, mirroring the project hub's 5a–5k, and documents every control and
  query parameter those pages accept — including `?project=` on the technique and
  artifact detail pages, and a walkthrough of the totality proof's gap shapes.

## [0.5.0] - 2026-09-05

### Added
- The schedule evaluator now checks whether an approved baseline's own stored
  task dates fall inside the window `calc.network` computes from that
  baseline's own durations and dependencies, naming any task outside it.
- The static showcase's `manifest.json` now carries a `pages` count, a `scripts` list, and a `sha256` map of every shipped file's bytes alongside `files`; the clobber guard is keyed on `manifest.json`'s `kind` instead of a separate marker file, which is no longer written and is cleared as stale residue where found.
- The flow page now opens with a KPI tile strip (work in progress, throughput,
  median cycle time, median lead time, likely completion) — the same tile
  markup the portfolio dashboard uses, so no page restates its own CSS.
- The method-profile index (`/methods`) now states a coverage count above its list:
  how many methods it describes, how many are fully crosswalked to a PMBOK-6
  process or technique, and how many carry at least one guide-only practice.
- `tests/test_sample_content.py` checks each committed sample under `docs/samples/` for family-appropriate content (headings, minimum size) rather than only the byte-for-byte drift the CI gate already covers, so a generator regressing to a stub report can no longer pass by staying stable.

### Changed
- CI and `bin/driftless-gates.sh` put pytest's `tmp_path` in RAM (`--basetemp` under `/dev/shm`): every test builds a file-backed sqlite store there, and on the runner host's disk that held the suite at 40–54 minutes and once past the 60-minute job timeout; two test files measured 77 s on disk against 8 s in RAM.
- `docs/samples/2026-07-01/method-map.svg` is now newline-delimited (one element per
  line, 741 lines) instead of a single 78KB line, so a geometry change in the
  committed sample re-churns only the lines it actually touched and the CI drift
  gate's diff stays readable.

### Fixed
- `release.yml`'s re-dispatch recovery path now edits the release if one already exists for the tag instead of failing with "release already exists"; an empty `tag` input on the API path (`-f tag=`, which the workflow_dispatch UI cannot send but the API can) is refused with a clear error instead of silently falling back to `github.ref_name`; and the 125,000-character release-body cap is now measured in UTF-8 bytes, so a notes section heavy with accented or non-ASCII characters is still cut within GitHub's actual limit.
- The department detail page folds its seven operations sections (services, work queue, recurring work, service levels, operating controls, incidents, improvements) behind one details toggle, the project hub renders its ten knowledge-area percentages as a definition list instead of one long sentence, and search results now show a human label instead of the raw internal path.
- `docker-publish.yml` checks out the dispatched tag's own tree instead of master-at-dispatch, refuses a dispatched `tag` input that is not shaped like `v0.2.0`, only tags an image `:latest` when it is the newest published version (an older tag republished can no longer move `latest` backwards), and skips the build entirely on an archive tag push, which never publishes anyway.
- Twenty-six classes that no stylesheet, test or script ever named are gone from the templates (department and business-detail rows and lists, chart tick and band markers, the search hit row, the map label), and the class walker no longer carries a hand-kept allowlist: a class a test selects by or `map.js` queries is read off those files as a named hook, and everything else must carry a rule. Three raid-log row classes remain listed until the RAID badge change lands.
- The breadcrumb trail, the shared empty-state panel and nine other classes rendered as unstyled text because no stylesheet declared a rule for them; `scorecard.html` and `project_hub.html` also hand-rolled their own ad-hoc "nothing here yet" markup instead of the one shared empty-state partial. Both are fixed, and a new test walks every template's classes against the stylesheets so a future unstyled class fails the suite instead of shipping quietly.
- A RAID risk row's severity badge class is now computed alongside the row rather than decided by the template. The method map's per-node detail panels use a heading level that no longer drowns the page outline in one heading per node.
- `bin/driftless-showcase.py` emits every sibling page link extensionless (`href="page"`,
  `./` for the index) so Cloudflare Pages' redirect never round-trips a click, links the
  read-only bundle's about notice back to `headlessmode.com/driftless` (configurable via
  `--site-url`) instead of a dead root-relative path, and ships `driftless.css` and
  `map.css` once each as sibling files instead of inlining them into a `<style>` block on
  every page.
- `bin/driftless-showcase.py` rewrites single-quoted links and stylesheet tags the same
  as double-quoted ones, clears every stale file a prior export left behind (not only
  `*.html`) before writing a fresh bundle, and defaults `--source` to the checkout's
  short commit SHA unless HEAD carries the exact release tag its version names,
  printing which one it picked.
- Money figures (budget, EV, EAC, risk impact/exposure, etc.) render comma-grouped on every page via a shared `money` filter, instead of a bare unrounded float on the hub, weekly status, RAID log and EVM calculator. Severity/RAG badges (scorecard status, RAID status, threat severity) now share one filled `badge sev-badge` idiom instead of three inconsistent renderings, and threat scores print to two decimal places everywhere.
- The project hub now links every mounted project page, including the six schedule-network, decisions, earned-value, scope, stakeholders and risk-response assist pages it used to leave unreachable from the strip. A pinned `as_of` now survives every internal project link that reads it (the board link stays deliberately undated — nothing it shows is dated). Breadcrumb crumb labels ("Schedule", "Weekly status", "RAID log") now match the destination's own heading everywhere they appear, the process map gained the breadcrumb trail every other project sub-page already had, and the masthead no longer repeats the project name a breadcrumb trail already carries.
- The RAID log's three table-row classes, the last entries the class walker still excused, are gone; the walker now excuses nothing by hand.
- `release.yml` cuts release notes that exceed GitHub's 125,000-character body limit at a line boundary and says where the full section is, instead of failing at `gh release create` after the tag is already pushed (v0.4.0 shipped a tag with no release this way). It can also be dispatched by hand for an existing tag, so a fix to the workflow can reach a tag whose push run failed.
- The static showcase's page list is now derived from the router instead of hand-maintained, so `/search`, business/portfolio/program/department detail pages, and the full technique/artifact/PMBOK/method reference library are no longer missing from the exported demo; a test now fails the build whenever a newly mounted page is neither exported nor named in an explicit exclusion list.
- The money dashboard treemap and the method map are named groups (`role="group"`), not single images: each holds links, and `role="img"` had made the exported pages one image with interactive controls nested inside, which the site's accessibility gate refused. The exporter picks the role the same way for any SVG it names.
- Schedule-network, Gantt and status-trend/EVM SVG charts now scale to their
  column instead of rendering at a fixed 320px box, and the schedule network's
  critical-task label colour uses the real `--background` token in place of
  the undefined `--page-bg`.
- Each portfolio rectangle on the money dashboard's treemap is a focusable SVG link; it now carries the same words as its `<title>` on `aria-label` (portfolio, budget at completion, RAG as a word), so screen readers that ignore a `<title>` inside an SVG link still announce where it goes.

### Docs
- Documented and pinned that the demo's `Premiere` milestone offset is inert for the schedule-slip signal; the live slip comes from `Sizzle reel delivery` instead.
- The container image described in `README.md`, `OPERATIONS.md` and
  `docs/release-publishing.md` is now stated as conditional on a public tag,
  not already shipped: `Back-Road-Creative/driftless` has no tags, no
  releases and no `ghcr.io/back-road-creative/driftless` package as of this
  writing. `docs/release-publishing.md` also gains a public-tree-vs-source
  diff check before tagging, a step to regenerate the headlessmode showcase
  bundle and run the production smoke, and a note that the archive's own
  release workflow (which carries no repository guard) already produces
  archive-only releases today.

## [0.4.0] - 2026-09-01

### Added
- **A tagged release on the public repository publishes a container image.**
  `ghcr.io/back-road-creative/driftless` is built from the released tag's own
  tree and pushed as both `:<version>` and `:latest`, so a release is a
  version you can pull rather than one every reader builds from a checkout —
  once that tag is on `Back-Road-Creative/driftless`. 0.4.0 itself was tagged
  on the private archive only; the public repository has no tags yet, so no
  0.4.0 image exists to pull. The release notes carry the pull command, and
  `docs/release-publishing.md` is the procedure that cuts a release.
- Two new pages, `GET /methods` and `GET /methods/{key}`, describe Scrum and Kanban in
  Driftless's own words, never a quote of either guide: each practice's kind, plain summary,
  and its crosswalk to the PMBOK-6 process or technique it most nearly resembles. Scrum
  is pinned to *The Scrum Guide*, November 2020 edition; Kanban has no single canonical
  guide, so the profile names the one chosen (*Essential Kanban Condensed*, 2016). "Methods"
  joins the primary nav beside "Techniques".
- **Agile execution records: roles, backlog items, releases, definition-of-done
  and impediments.** `ProjectRole` names who holds a product/team role
  (product owner, Scrum master, developer, stakeholder proxy) by a plain name,
  not a `Person` link. `BacklogItem` is agile demand — ordered, prioritised and
  estimated in `story_points` — before it becomes a `Task`. `Release` groups
  sprints. `DefinitionOfDoneItem` is a project-wide "done means" checklist.
  `Impediment` is a dated blocker, current state like `Risk`/`Issue`. An
  "iteration" is still a `Sprint`: it now also carries a `goal`, an optional
  `release`, and the review/retrospective evidence (`review_held_on`/
  `review_notes`, `retrospective_held_on`/`retrospective_notes`) that closes it
  out, rather than a parallel iteration table. All five records are exposed
  through the same generic create/read/update/delete registry as every other
  per-project record — `/project-roles`, `/backlog-items`, `/releases`,
  `/definition-of-done-items`, `/impediments` — with `?format=csv` and the
  delete guard for free.
- API tokens can now be minted with `token add --expires-in-days N`; an omitted flag keeps a token — and every one minted before this — expiring never. An expired token and a revoked token resolve identically to a caller (both a `401`, on purpose, so which one happened is never disclosed), but `token list` now shows an operator the distinction.
- `token list` now prints when each API token was last used, or `unused` if it never has
  been. Deciding what to revoke previously meant guessing from a label and a mint date,
  which says nothing about whether anybody still holds the credential.
- The stamp is deliberately coarse — a use rewrites it at most once every 15 minutes
  (`auth.tokens.STAMP_INTERVAL`), so authenticating a read does not cost a write per
  request — and it is written with statement-level SQL so it files **no** `change_log`
  row. `change_log` records domain writes by an actor; a token being presented is
  neither, and auditing every read would bury the trail it exists to keep.
- Every resource endpoint now also answers under `/api/v1`, which is the canonical
  path and the only one the generated OpenAPI schema describes. The bare path
  (`/projects`, `/tasks`, …) keeps answering the same endpoint function, unlisted,
  so nothing already deployed breaks and the dashboard's own forms keep working.
  Both addresses reach one implementation, so they cannot drift apart.
- Operating endpoints are deliberately not versioned: `/health`, `/health/ready`,
  `/metrics` and the docs routes keep their names. Beyond a version buying nothing
  there, `is_open_path` matches `/health` exactly — on purpose, so `/health/ready`
  stays gated — and an `/api/v1/health` alias would have landed behind the
  credential gate while bare `/health` went on answering. Widening the open-path
  set to accommodate a routing change was the wrong fix; the set is unchanged, and
  a test pins that.
- **Every artifact kind now has its own page.** `/artifacts` lists the whole
  `ARTIFACT_KINDS` vocabulary — every plan, baseline, document, performance record,
  procurement record, deliverable, change and environment factor a process's ITTO
  table can name — grouped by family, and `/artifacts/{slug}` gives one artifact kind
  in full: what it is, why it matters, what it looks like on this product, which
  processes make it and which read it, and whether this product's store tracks it.
  With `?project=` the detail page also shows what that project's own store answers
  for this one kind, the same reading a process drill's ITTO table already gives.
  Every Inputs and Outputs entry on a process page now links straight into it, the
  same way its Tools & Techniques entries already link into the technique library —
  so a reader never meets the raw `snake_case` key. The catalog has its own
  primary-nav entry, and a slug matching no artifact kind answers 404 rather than
  failing.
- Artifact kinds now have an `ArtifactDefinition` registry (`driftless.pmbok.artifact_definitions.ARTIFACTS`), one entry per `driftless.pmbok.artifacts.ARTIFACT_KINDS` member, carrying its key, display name, family and a plain-language explanation — a one-sentence summary a newcomer can follow, why it matters, and what it looks like in this system. `produced_by` and `read_by` are derived by walking `driftless.pmbok.catalog.PROCESSES` rather than typed by hand, and `tracked_by` is derived from `driftless.pmbok.mapping.is_tracked`, so none of the three can drift from the tables they describe. The explanation fields compose in from one module per family under `driftless.pmbok.artifact_content`, mirroring `technique_content`'s discovery mechanism.
- Added a reusable as-of contract test harness (`assert_history_survives`) and pinned
  it against three record kinds that already guarantee it: a quality measurement,
  a process sign-off, and a PMBOK baseline approval, each posted through the real
  validated API and dated after the render's as-of, plus a store-wide `report all`
  check across two rendered output trees. Two known breaks, baseline selection and
  scorecard thresholds, are left unpinned pending their own fixes.
- Assessment results now carry explicit evidence coverage, separating measured health from stale, missing, and not-applicable controls.
- **Every routed assistant now passes one shared gate.** `tests/test_assistants_totality.py`
  derives the assistant set from `assess.model.ASSISTANT_ROUTES` and the app's own mounted
  routes, then checks every page it finds for real content, deterministic and as-of-honest
  rendering, a statement-count ceiling, a print/no-JS text alternative for any chart it draws,
  viewer-vs-writer role gating, and an export/import round trip for anything it writes.
  `tests/test_launcher_totality.py` gained the matching check that a routed technique's launch
  address is actually mounted, not just promised in the model.
- Added an admin-only tier for the sign-off ledger: `POST /sign-offs` and the `POST /sign-off` browser form that writes the same row both now refuse a contributor, where every other write still accepts one, closing the gap where the form could reach a governance decision the JSON route alone would have blocked.
- **The backup has a schedule, so RPO is a number instead of a habit.**
  `deploy/driftless-backup.timer` runs `bin/driftless-backup.sh` daily at 03:00 (±15 minutes of
  jitter) via `deploy/driftless-backup.service`, and `Persistent=true` catches up a run missed
  while the host was off — without it "daily backups" quietly means "on the days the host was
  awake at 03:00". OPERATIONS.md now states RPO as **24 hours** rather than unbounded, and
  *Backups → Scheduling the backup* is the install: an `/etc/driftless/backup.env` naming where
  the age key lives (never the key), then `systemctl enable --now`.
  The unit runs `bin/driftless-backup-run.sh`, not an `ExecStart=` one-liner: that step decrypts
  the database password, picks the stamp and decides the exit code, and it exports the password
  rather than passing it as an argument where `ps` shows it to every account on the host.
  **Failure surfaces twice** — the runner re-raises the script's exit code so systemd marks the
  unit failed, and appends `<timestamp> driftless-backup stamp=<stamp> exit=<rc>` to
  `$DRIFTLESS_BACKUP_LOG` for a watcher to scan. **Installing the units is still an operator
  step, nothing here reads that log yet, and off-host replication remains unaddressed.**
- An opt-in rendered-browser tier: `bin/driftless-gates.sh --browser` (and a
  nightly workflow) installs Chromium and loads the dashboard, project hub,
  scorecard, configuration and status pages at desktop and phone widths,
  checking that neither overflows sideways and that no page script raised.
  It answers what the text-only gates cannot, since none of them lays a page
  out. It is not a required check and it replaces nothing: the byte-diffable
  page snapshots remain the floor, and the default test run neither installs
  Chromium nor collects these checks.
- The rendered-browser tier now covers the eight display-heavy pages it skipped — the method map, process map, flow, gantt, heatmap, cost assistant, method catalogue and PMBOK proof — beside the original five, at desktop and phone widths. Each render writes an audit record (viewport, document scroll width against client width, the largest SVG's box, how many SVG labels came out visible, and everything the page logged) to `reports/browser-audit/`, and asserts what no page may do: answer with something that is not HTML, raise in the browser, come back blank, or overflow sideways. A blank or errored render is now red on its own rather than something a human had to spot in an image. It found one on its first run: `/process-map` overflows the document at both widths despite carrying a declared scroll wrapper, recorded as a strict xfail that goes red the day the layout is fixed.
- The browser tier now also checks what the pages do once a reader states a
  preference: that the dark colour scheme actually repaints each page, that the
  first Tab lands on the skip link and moves it back on-screen, and that a
  request for less motion leaves the dashboard's figures final at first paint
  rather than animating them. All three were implemented already; nothing that
  reads HTML as text can see whether the implementation reaches the page.
- Added `driftless.calc.estimating`: analogous, parametric (single- and multi-driver),
  three-point (triangular and beta/PERT, with a confidence range at +/-sigma standard
  deviations) and bottom-up estimating, each a pure function over plain numbers returning
  a frozen `EstimateScenario` (kind, inputs, value, low/high range and a plain-words
  basis) — calculator layer only, no page and no wiring into the stored task/baseline-line
  estimate yet.
- `driftless/calc/flow.py` adds kanban/flow metrics as pure functions over a plain `WorkItem`: work in progress, throughput, cycle and lead time, burndown and burnup, and cumulative flow, plus a release forecast that reuses `calc.forecast.forecast_completion` rather than a second velocity rule. Calculator only — not yet wired to stored rows or a page.
- Add a pure risk-analysis calculation core (`driftless/calc/risk.py`): a configurable
  probability x impact matrix with plain-words bands, risk breakdown structure
  categories, expected monetary value, decision-tree branch selection, tornado-ordered
  sensitivity analysis, and a seeded Monte Carlo simulation of a risk register's own
  exposure.
- **File an estimate from the cost workbench, and a department budget view.** The
  cost workbench lists the estimate scenarios filed for a project as of the date and
  grows its one write: file the last what-if computed as a stored estimate scenario
  (technique, value, range, basis, who filed it) through the same validated boundary
  the JSON route uses. The page now links the one change boundary — a change request
  against Determine Budget — since every other figure on it stays a what-if. The
  department workspace gains a budget and run-rate section: the department's own
  budget lines rolled up by category beside the run rate of spend on the projects it
  is accountable for.
- **Cost workbench calculator.** `driftless/calc/cost.py` adds pure functions over
  plain value objects, alongside `calc.evm`, `calc.forecast` and `calc.rollup`:
  `cost_aggregation` rolls planned amounts up work package -> control account ->
  project total; `reserve_analysis` states PMBOK's two reserves plainly — cost
  baseline is the work packages plus contingency, and the total project budget is
  that baseline plus a management reserve; `funding_limit_reconciliation` flags
  periods whose cumulative planned spend outruns a stated funding limit;
  `financing_cost` prices simple and compound financing; `cash_flow_s_curve`
  samples `calc.evm.planned_value` (imported, not re-derived) into a cumulative
  spend series; `run_rate` gives a department or agile team's trailing-window
  average spend; and `basis_of_estimate` renders a plain-words basis from a
  structured scenario dict, pending a future `calc.estimating.EstimateScenario`.
- **The cost workbench page.** `GET /projects/{id}/assist/cost` rolls up a project's
  own budget lines, works out its cost baseline and reserves, samples the cash-flow
  S-curve off the same accrual the earned-value calculator reads, reconciles it
  against a stated funding limit, prices financing, reads a run rate off recorded
  spend, splits cost of quality, lists other projects' actual spend as a real
  historical reference figure, and runs the four estimating techniques (analogous,
  parametric, three-point/PERT, bottom-up) — ten PMBOK tools and techniques routed
  through one no-write page, linked from the project hub.
- Every list endpoint now filters, derived off its own model's mapper rather than a
  hand-kept table: a foreign key column scopes to its parent id, and a `status`/`rag_status`
  column filters by equality. The filter narrows both the page and the `X-Total-Count`
  header, so a filtered answer never over-reports how many rows matched.
  **This is a visible behaviour change**: a query parameter no list route recognises —
  including a misspelling of one it does — used to answer `200` with the whole,
  unfiltered table; it now answers `422`, naming the parameter it did not recognise.
- **The demo store now runs one project adaptively.** Fleet Modernization seeds four
  iterations (three closed with review and retrospective notes, one in flight), a release,
  an eight-card board across all four statuses, two impediments, a definition of done and
  the product-owner and Scrum-master roles — so the flow calculator page, the hub's flow
  tile and the rollup's flow columns render a real velocity band, WIP, burndown, burnup
  and a cumulative-flow diagram instead of their empty states.
- **The demo's predictive project now has a schedule, not two bars.** Season 4 Rollout
  seeds the whole post-production chain — nine tasks from the shoot through dailies,
  assembly, rough cut, grade, mix and broadcast QC to network delivery — wired by ten
  typed dependencies including a start-to-start pair, plus five milestones. The gantt
  page and the schedule assistant now draw a real network: a critical path seven tasks
  long, the sound mix holding three days of float and music clearance holding forty-nine.
  Only the two original tasks carry planned cost, so every earned-value figure the demo
  reports is unchanged.
- **A department workspace, not just a roster.** `/org/departments/{id}/assist` adds nine
  sections built from rows the store already holds, each with a plain sentence and a link to
  its closest technique: objectives the department's accountable projects actively
  contribute to (graded from their scorecard metric evidence), an operating plan (services and
  the recurring work the department runs on its own cadence), a RACI matrix assembled from real
  rows — a service's own owner (responsible), the department itself (accountable), the
  stakeholder-proxy role holders on the department's projects (consulted), and who has raised
  work against that service (informed) — never a typed-in role column, demand versus capacity
  classified the SAME way the capacity heatmap washes its own grid (one definition of
  over-allocated, never a second copy), service levels compared against a plain average cycle
  time over completed work requests, controls with their open incidents and worst severity,
  improvements, and the vendor agreements and stakeholders touching the department's own
  projects. Linked from the department detail page. Every section is reference-only: the two
  techniques that would fit best, `resource_optimization` and `stakeholder_analysis`, are
  already claimed by a project-scoped recommended action, and a route is keyed by technique
  alone, so this page cannot honestly borrow either without breaking that action's launch link.
- **Department operations records: services, work queue, recurring work,
  service levels, controls, incidents and improvements.** `DepartmentService`
  is a department's own service catalog. `WorkRequest` is the demand queue
  against it, carrying the same three-date shape `driftless.calc.flow.WorkItem`
  reads (`raised_on`/`started_on`/`done_on`), so flow metrics — WIP,
  throughput, cycle and lead time — apply to a department's queue exactly as
  they would to a project's backlog. `RecurringWork` and `ServiceLevel` share
  one cadence vocabulary. `OperatingControl` plus `Incident` (severity, dates,
  an optional root cause, a nullable `control_id` link like `Issue.risk_id`)
  and `Improvement` (what, why, owner, status) round it out — current state
  like `Risk`/`Issue`, not as-of tracked. `BudgetLine` gains a nullable
  `department_id` alongside its existing `project_id`, with a CHECK requiring
  exactly one of the two: a department runs its own operating budget through
  the same table rather than a twin one. All seven new records are exposed
  through the same generic create/read/update/delete registry as every other
  record — `/department-services`, `/work-requests`, `/recurring-work`,
  `/service-levels`, `/operating-controls`, `/incidents`, `/improvements` —
  with `?format=csv` and the delete guard for free, and `GET
  /org/departments/{id}` now lists all seven in plain words.
- **A product shell now wraps every page.** `base.html` renders a masthead — a
  full-width bar with a bottom rule: the wordmark (never underlined, a logotype
  rather than prose) and the currently open project on the left, Search, Sign
  in/out and the as-of chip right-aligned on the same row. The primary nav is
  grouped into three screen-reader-named clusters — Work, Method, Organization —
  each a caption above its own links, one row on a desktop-width viewport and
  stacked on a narrow one, every destination still marking `aria-current="page"`.
  `driftless.css` gains a four-step type scale and an 8-pt spacing scale, a
  centred 1280px page container, a 72ch cap on prose, 32px of breathing room
  above every `h1`, and link styling (`--ink` with an underline that strengthens
  on hover and focus) in place of the browser-default blue.
- **One assistant-page pattern.** Every `assist_*.html` (and `assist_department.html`)
  now opens with a `.tiles` summary strip of its 3-5 headline figures, and renders every
  PMBOK technique as its own `.card`, with a small `.tech-chip` linking the technique
  library wherever the page already computed that reference — never a bare `<h2>` over
  prose alone. `web/templates/_assist.html` is the one place that shape is drawn
  (`summary_strip`, `section`, `empty` macros); `driftless.css` gains the matching
  `.assist-card`/`.tech-chip`/`dl.kv` styles, the last for small two-column results
  (a reserve analysis, an earned-value what-if) that used to print as a one-row table.
- **Every knowledge area and control now walks end to end, in every delivery mode.**
  A new suite parametrizes over the ten knowledge areas crossed with predictive, agile
  and hybrid, plus one department. Each walk seeds a project through the public surfaces
  only — the API resource registry and the wizard's own `produce` — files the area's
  producible inputs in lifecycle order, opens the assistant page(s) its techniques route
  to, records a `TechniqueRun`, and — for Scope and Schedule, the two areas that own the
  project's `Baseline` — raises and approves a `ChangeRequest` through the one boundary
  that produces a new version. Every process is then read back three ways that must
  agree (the computed state, the `/pmbok/{id}?project=` drill page and the business-wide
  rollup cell), cross-checked against the Process Map and Assessment report documents,
  round-tripped through `bin/driftless-import.py` where an exported kind has an importer,
  and proven as-of-sensitive: the day before the walk's last write reads differently from
  the day of it.
- Earned value now carries cost and schedule variance (CV, SV) and their percent
  forms, shown on the project hub, the earned-value calculator and the Cost Report
  (EVM). The calculator also compares all four standard EAC methods side by side,
  each with a plain-words rule for when to use it.
- **The first two runnable assistants: an earned-value calculator and its
  to-complete performance index.** `/projects/{id}/assist/earned-value` shows every
  figure the project hub already computes — BAC, PV, EV, AC, CPI, SPI, EAC, ETC, VAC
  — with its formula spelled out in plain words and one plain sentence on what it
  means, never a second computation. It also works out TCPI (`calc.evm.to_complete_performance_index`)
  in both PMBOK forms: the efficiency the remaining work needs to still land on the
  original budget, and the same question against today's forecast instead. A
  what-if box recomputes an alternate estimate at completion from a hypothetical
  remaining cost; nothing typed there is saved. `earned_value_analysis` and
  `to_complete_performance_index` are the first two techniques
  `assess.model.ASSISTANT_ROUTES` actually routes — their `assistance_mode` is
  raised to `CALCULATOR`, and every surface that used to say "reference only" for
  them (the threat board, the CLI, the Assessment Report, the process detail page)
  now offers "apply" instead, derived from the same registry rather than by hand.
- **A flow calculator, and flow figures on the project hub.** `/projects/{id}/flow`
  shows work in progress, throughput over the trailing week, cycle and lead time
  (median and 85th percentile), the release forecast band, and — for a sprint whose
  window contains the as-of — burndown and burnup as inline SVG charts with a text
  twin, plus cumulative flow as a data table. The project hub gains a Flow tile
  (WIP, throughput, median cycle time, likely release) reading the same
  `pmbok.flow_facts.flow_snapshot` adapter, so the two can never disagree. `BacklogItem`
  carries no `created_on`/`started_on`/`done_on` columns; those three dates are
  replayed from the `ChangeLog` instead, the same way task percent-complete already
  is, so a report pinned at an earlier as-of never sees a status change dated after
  it. `agile_release_planning` is now a routed technique
  (`assess.model.ASSISTANT_ROUTES`, `assistance_mode` raised to `CALCULATOR`); the
  markdown Forecast Report's sprint-history and remaining-points reading moved into
  the same adapter, so it and the flow page can never print two different release
  bands for one project.
- **The Forecast Report now shows a simulated completion.** An agile or hybrid project's
  velocity band gains a "Simulated completion" block — p50/p80/p90 completion dates from a
  seeded Monte Carlo over the same sprint history (`driftless.calc.forecast.monte_carlo_completion`),
  labelled schedule forecasting rather than risk analysis. The seed is the project id, so two
  renders of the same project are byte-identical. This is what `docs/pmbok-mapping.md`'s
  Simulation row has credited all along — it now has a caller.
- The credential gate now logs its own refusals, on `driftless.secure` at INFO: every 401 (no credential resolved) and every 403 (insufficient role) it answers itself — outside the app, so neither the request log nor the metrics endpoint ever sees one — now leaves a record naming what was refused (method, path, client, and the resolved username for a 403). It never logs the presented credential, any part or hash of it, or the `Authorization`/`Cookie` header. Before this, a burst of rejected credentials was indistinguishable from no traffic at all.
- `GET /metrics` now answers Prometheus text-exposition — request counts and durations by method, status and route template, plus process uptime — behind the same credential gate as every other route, never open to an uncredentialed scraper (`OPERATIONS.md`, *Metrics*).
- **A glossary explains PMBOK's terms of art in plain words.** `/glossary` defines
  baseline, float, critical path, EVM, WBS, RAG and the rest of the terms of art the
  app already uses without stopping to explain them; a technique page's summary,
  when-to-use and when-to-avoid prose now links each term's first mention to its
  plain-word entry. RACI, EEF, OPA, CPM, OKR, and "definition of done" are left out
  of this pass: none appears anywhere a reader can read yet, so the glossary's own
  no-orphan-terms guard would refuse them today.
- **Map views: a process-first overview and a per-node neighbourhood.**
  `driftless.pmbok.graph_views` derives two readable slices from the one
  method graph rather than a second copy of it: `overview()` is every process
  node in lifecycle order (process group, then PMBOK number) with the `feeds`
  ties between them, and `neighbourhood(node_id)` is one node's ego network —
  the node, its direct neighbours across every edge kind, and only the ties
  with both ends inside that set. A node the catalog leaves unconnected comes
  back as itself with zero ties; an unknown id raises rather than returning an
  empty view. `GraphView.counts()` reports the slice against `GRAPH.size()`
  (nodes and ties shown, nodes and ties in the whole graph) so a page can say
  how much of the map it is showing in its own words, with no sentence frozen
  here. Pure, deterministic and
  I/O-free: same input, same output, every run.
- Extend the deterministic demo seed and Headless Mode static showcase with balanced-scorecard objectives, evidence states, contributions, the Scorecard page, and Organization readiness.
- Hybrid tailoring: every Monitoring & Controlling process now says whether it runs on a predictive baseline, an adaptive commitment, or (reserved for department-scoped work) an operations cadence, with a one-sentence plain reason, per delivery mode (`driftless.pmbok.tailoring`). The project process map and the PMBOK reference detail page show the mode beside each control, and organization configuration lists the three profiles in plain words. Whatever a control is tailored to, a plan changes only one way: the earned-value calculator now links to raising a change request against the process that proposed it, through the existing `ChangeRequest` producer.
- Writes now honour an `Idempotency-Key` header, so a retried POST cannot create a second
  row. `bin/driftless-import.py` POSTs a CSV a row at a time and resumes with `--skip N`; a
  crash between the POST landing and the client recording it made the client retry a row the
  store already held, and a create carries no natural key to tell the duplicate apart.
- A replayed finished key returns the original answer (`Idempotent-Replay: true`); one
  whose request never finished answers `409`, since the write may have landed and
  re-running it is the duplicate this prevents. A key reused on another endpoint is
  `422`. Opt-in, at the middleware chokepoint, so a later write route is covered too.
- **Preview, apply and confirm a native change, and prove it reaches every consumer.**
  `driftless/services/changes.py` gives a status snapshot and a sign-off a `preview`
  (what would be written, no write made), an `apply` (through the existing
  service, never a second write path) and a `confirm` (an append-only,
  actor-stamped acknowledgement). The new propagation manifest
  (`driftless/pmbok/consumers.py`) names the five families that read a project —
  process state, the rollups, the report documents, the assessment engine and the
  export surface — and a new test proves each native change alters every family
  the manifest declares reachable, with a reason recorded for the one it cannot.
- Every technique without a runnable assistant, and every artifact kind the wizard cannot produce, now carries a documented reason with a machine-readable kind (`driftless/pmbok/reasons.py`); the suite asserts the reasons and the gaps are the same set, so a reason outlives its gap by exactly zero merges. The citation exemptions moved into the same shape.
- Every list endpoint now takes `?cursor=<id of the last row you saw>` as an
  alternative to `?offset=`, and answers `X-Next-Cursor` while rows remain. The
  header's absence is the end-of-collection signal, so a client loops until it
  stops appearing rather than guessing from a short page.
- Why it matters: `?offset=` counts positions, so deleting a row from a page
  already read slides later rows down one and the next offset page steps over
  whichever row moved into the gap. A cursor names a row, so a change behind it
  cannot move the boundary — the case that matters on append-only collections.
- `?cursor=` with `?offset=` is refused `422` rather than one being silently
  ignored. Offered on every list rather than a chosen few: each is already
  ordered by primary key, so the mechanism is identical, and a subset would
  need a hand-kept table of which resources support it.
- Every list endpoint with a `Date` column now filters on an inclusive
  `<column>_from` / `<column>_to` range — `GET /issues?raised_on_from=2026-01-01&raised_on_to=2026-01-31`
  is every issue raised in January, the 31st included. Derived off the mapper
  like the existing parent-id and status filters, so a dated column added later
  is filterable with no edit, and `X-Total-Count` narrows with the page.
- `DateTime` columns deliberately take no range. Every one in the schema is a
  system-time stamp (`signed_at`, `approved_at`, `created_at`, `revoked_at`,
  `expires_at`, `changed_at`), and a `date` bound against a timestamp compares
  to midnight — a `_to` would silently drop the last day it named. "What changed
  since" is a `ChangeLog` question, which is built as a sync cursor.
- `bin/driftless-gates.sh` runs CI's gates locally — building `.venv` from `requirements.lock` first, and reading every pinned tool version out of `.github/workflows/` rather than restating one, so a local run and the merge see the same linter, the same type checker and the same dependency set.
- `bin/driftless-gates.sh` now mirrors all four `ci.yml` jobs, not two: `--migrations`
  starts a `postgres:16` container itself and runs `tests/test_migrations.py` against it —
  closing the gap where an unset `DRIFTLESS_TEST_DB_URL` let that module's Postgres half
  skip silently and a local run prove the migration chain only on SQLite — and
  `--docker-build` runs a plain `docker build` of the repo. Both are part of the default
  full run. A new guard, `tests/test_local_gates_cover_ci.py`, reads `ci.yml`'s job list and
  fails if a future job has no matching local stage.
- Added `driftless.pmbok.graph`, a pure, clock-free method graph derived entirely from
  the ITTO catalog: every process, technique and artifact as a node, and `reads` /
  `produces` / `used_by` / `feeds` edges read straight off a process's own inputs,
  outputs and tools & techniques — no second, hand-authored picture of the wiring.
- **The method graph is now readable as JSON**, at `GET /map/graph.json`: every
  process, technique and artifact node and every `reads`/`produces`/`used_by`/`feeds`
  edge `pmbok/graph.py`'s `GRAPH.to_dict()` already computed, plus a top-level
  `source_version` naming the PMBOK edition. Read-only, no store, no `as_of` — the
  graph is built once at import and answers the same bytes on every request. This
  resolves the earlier decision that the JSON API did not expose the technique
  registry: it now does, the same way `/techniques` already exposes it as HTML.
- **The method map now lights up under a mouse or a keyboard.** Hovering or tabbing to a shape
  on `/map` highlights its ties and its neighbours; clicking or pressing Enter pins the selection
  and opens a panel with its plain-language summary and a link to its own page. Chips filter the
  drawing by kind, process group, knowledge area and technique family, a "show flow only" chip
  narrows to the derived `feeds` ties, and a search box narrows to matching labels. All of it is
  `static/map.js`, loaded only on this page: no fetch, no library, and the page stays exactly as
  usable with JavaScript off as M.3 already made it.
- **The method map is now a page.** `GET /map` draws the whole method graph — every
  process, technique and artifact, and every tie between them — as one inline SVG from
  `pmbok.graph_layout.LAYOUT`, no client-side JS or graph library required to read it.
  `?project=&as_of=` washes each process node with that project's own reading, the SAME
  wash and mark `/projects/{id}/process-map` already prints for it; `?focus={id-or-slug}`
  highlights one node and its neighbours, server-side, for a deep link or a keyboard/
  screen reader with no JS in play. Every process and technique page now carries a "See
  it on the map" link to its own node. A `<details>` list below the SVG spells out every
  tie in words, for print and for a reader the drawing does not reach.
- The generated OpenAPI schema (`/openapi.json`) now describes the real API rather
  than a fiction of it: the HTML dashboard's page routes no longer appear as though
  they answered JSON, the schema declares the bearer credential `TokenGate` actually
  enforces, every resource `_reads`/`_writes`/`_creates` register carries a tag
  grouping its endpoints, and `?limit`/`?offset` document the clamp the list
  endpoints already applied.
- The web navigation now exposes an Organization configuration page with live operating-model counts and the validated setup paths for businesses, portfolios, programs, projects, departments, people, and quality policies.
- Added `driftless user passwd <username>`, reading the new password from stdin like
  `user add` does, so a leaked or expiring credential can be rotated without the only
  prior remedy — disabling the login outright. Rotation is also a revocation: it bumps
  `session_epoch` the same way `disable` does, so every cookie the old password issued
  stops resolving the moment the new one is set.
- Added a shared plain-language contract test (`driftless/pmbok/plain_language.py`) over every artifact and process `plain_summary`, closed several raw snake_case identifiers that had leaked into technique content, and consolidated the existing per-registry checks onto it.
- **Agile evidence now counts as control coverage, derived and never copied.** Seven
  artifact kinds a Scrum or Kanban project could never produce through the
  predictive-shaped rows `mapping.py` reads (`requirements_documentation`,
  `project_schedule`, `scope_baseline`, `issue_log`, `lessons_learned_register`,
  `resource_management_plan`, `work_performance_reports`) can now resolve from that
  project's own agile evidence instead — backlog items, releases, definition-of-done
  items, impediments and sprint review/retrospective notes. A new crosswalk
  (`driftless/pmbok/crosswalk.py`) names, per kind, where that evidence lives and the
  plain-English rule that reads it, and `mapping.resolve` consults it only as a
  fallback, when its own resolver finds nothing — a native row always wins, and the
  crosswalk never writes. The process page now names the equivalence beside the
  input/output it covers ("How Scrum/Kanban projects satisfy this"), and
  `docs/pmbok-mapping.md` carries the full table, doc-tested against the code.
- **The method graph now has a deterministic layout.** `driftless.pmbok.graph_layout.LAYOUT`
  places every process, technique and artifact node on a fixed grid — processes on the
  familiar process-group-by-knowledge-area table, techniques and artifacts shelf-packed
  into bands below it, grouped by family — with no randomness, no physics library and no
  clock, so two builds are always identical and a later map renderer has real coordinates
  to draw from.
- Every one of the 49 PMBOK processes now carries a plain-language explanation on
  `/pmbok/{process_id}` — a one-sentence summary under the title, why it matters, what
  "done" looks like, and a tip for the first time you run it. The Inputs, Tools &
  Techniques and Outputs headings now read "What you need", "How you do it" and "What
  you get", with the PMBOK terms kept alongside in parentheses.
- Filled in explanation content (summary, when to use/avoid, steps, outputs,
  pitfalls, a worked example and PMBOK-6 clause references) for all eight
  procurement-family techniques: advertising, bidder conferences, claims
  administration, inspections and audits, make-or-buy analysis, procurement
  performance reviews, proposal evaluation, and source selection analysis.
  Each entry is explicit about the scale of purchase it fits and, where
  relevant, that Driftless's own procurement support starts at a signed
  `ProcurementAgreement` and has no record of the pre-signature work (make-or-buy
  decisions, solicitations, bids, proposals) the technique describes.
- Wired `driftless.pmbok.support`'s coverage view up to the surfaces a reader actually
  visits: `driftless pmbok support` prints its store-wide summary (explained techniques,
  assessable and producible processes) straight off a fresh `build_coverage()` call, so no
  count is typed twice; the `/pmbok` reference grid now names each process's support tier
  in plain words next to its link — "You can fill this in here", "We can judge this step",
  or "Read-only for now" — derived from that same process's `ProcessCoverage`; and every
  `/techniques/{slug}` page says its technique's tier — "Runnable here" once
  `assess.model.ASSISTANT_ROUTES` names a launch route for it, or "Guide only — " plus the
  exact sentence recorded for it in `pmbok/reasons.py:GUIDE_ONLY_REASONS` otherwise. Nothing
  here restates `support.py`'s rules: each surface reads its coverage rows or its
  documented-reason dict and renders them.
- **The cross-cutting technique families now have real explanations.** Expert judgment, the
  data gathering/analysis/representation/decision-making umbrella families, interpersonal and
  team skills, the four communication techniques, meetings, and the project management
  information system each carry a summary, when to use it, when to avoid it, ordered steps,
  outputs, pitfalls, and a worked example, instead of the empty placeholders the family module
  shipped with.
- Added `driftless.pmbok.proof`, the one-line totality proof over the whole ITTO
  catalog: every technique, artifact kind, process, Scrum/Kanban method practice and
  Monitoring & Controlling tailoring mapping must be reachable (no process orphan),
  explained (no blank plain-language summary), launchable or honestly excused, and
  crosswalked, and the module names the offending members for any count that is not
  zero. It reads no store and takes no as-of, and it re-derives nothing the totality
  suites already own — `driftless pmbok proof` (also `GET /pmbok/proof`) is a single
  reachable surface over registries eight different test modules already gate
  separately. `tests/test_totality_proof.py` asserts every count is zero on this
  tree, including `Proof.skipped_processes`: since `wizard.engine.next_step` no
  longer skips a process for having nothing producible (it now returns a `derived`
  or `reference` step instead), the only remaining skip clause is a static,
  store-free fact, and this module proves the live-session version of that same
  claim by importing `tests/test_wizard_totality.py`'s own lifecycle-order/waive
  strategy rather than copying it.
- **Procurement decisions and project closeout: make-or-buy, bid scoring and a
  lessons learned register that is rows, not prose.** `/projects/{id}/assist/procurement`
  shows the project's signed agreements, a closure checklist derived from their own
  `status`, and three no-write what-ifs: `calc.procurement.make_or_buy`'s break-even
  volume and make/buy call, `calc.procurement.bid_score`'s weighted ranking and its
  sensitivity to each weight, and `calc.procurement.contract_type_guidance`'s
  fixed-price / cost-reimbursable / time-and-materials recommendation.
  `make_or_buy_analysis`, `proposal_evaluation` and `source_selection_analysis` are
  now routed in `assess.model.ASSISTANT_ROUTES`, their `assistance_mode` raised to
  `CALCULATOR`. `/projects/{id}/assist/closeout` shows deliverable acceptance (milestone
  status), the lessons learned register and a final-report summary drawn from the
  same figures the hub already computes. The lessons learned register is a
  `LessonLearned` row now — project, raised-on date, PMBOK-area category, what
  happened, what to do next time, and who raised it — replacing the single
  free-text `lessons_learned` narrative body; the onboarding wizard's Close Project
  producer files a row through the same validated write path every other producer
  uses.
- Show each project's active balanced-scorecard lenses, objective metric status, and evidence coverage on the project hub, with an explicit unknown empty state.
- A quality tools calculator core (`calc/quality.py`): control charts with ±3σ limits and a rule-of-seven run signal, Pareto analysis with an 80% "vital few" cut, a statistical sampling-plan formula, cost of quality, and an Ishikawa/fishbone shape with a five-whys chain helper.
- Quality metrics can now define whether lower, higher, or an in-range value is good, with reusable project-scoped thresholds that measurements may reference.
- **The quality workbench.** `/projects/{id}/assist/quality` runs six tools over a project's
  own `QualityMetric`/`QualityMeasurement` rows: a control chart per metric with two or more
  dated readings — mean, ±3σ limits and the rule-of-seven run signal, as an inline chart with a
  text twin table — a Pareto of out-of-tolerance readings ranked by metric with the vital-few
  cut named, a no-write statistical-sampling what-if, a fishbone/five-whys root-cause worksheet
  traced over one issue from the RAID log, a no-write cost-of-quality what-if (the budget's own
  cost categories carry no conformance/non-conformance split, so this is typed by hand), and an
  audit checklist read straight off the project's quality management plan narrative, one line
  per sentence. Routes `root_cause_analysis`, `cost_of_quality` and `audits` — the three
  `TT_CATALOG` techniques this page actually launches; control charts, the Pareto split and
  statistical sampling name no catalog member of their own. Linked from the project hub.
- Every request now carries a correlation id: `driftless.request` reads it off an inbound `X-Request-ID` header when the caller supplies one, generates one otherwise, logs it as its own field, and echoes it back on the response header — so the id an operator greps out of the log is the id a user can read off the failed call. An inbound header outside a bounded alphanumeric shape is replaced rather than logged, closing off the log line to header-borne newlines and quotes.
- **Resource types and the RBS tree, the stored RACI, acquisition, training,
  team assessment, conflict and its actions — as rows, with their own
  assistant.** Eight new tables: `ResourceType` (the catalog a project's RBS
  and acquisitions draw from — people, equipment or material, each with a
  unit and a rate), `ResourceBreakdown` (the RBS tree over it, a
  self-referential `parent_id`, the same shape `Deliverable`'s WBS tree
  already uses), `ResponsibilityAssignment` (the stored RACI — a person's
  role against exactly one of a deliverable or a task, a CASE-WHEN CHECK
  counts "exactly one"), `Acquisition` (one staffing/procurement event
  against a resource type, internal or external), `TrainingRecord` (a
  person's own training ledger, not project-scoped), `TeamAssessment`
  (an append-only dated reading against one dimension, like
  `AcceptanceRecord`), `ConflictRecord` (current state, like `Risk`/`Issue`)
  and `ConflictAction` (its follow-up ledger — owner and a due date).
  `driftless.pmbok.mapping`'s resource resolvers now read these rows:
  `resource_management_plan`, `team_charter` and `team_performance_assessments`
  prefer filed rows, falling back to the stored narrative when none exist;
  `resource_breakdown_structure` and `physical_resource_assignments` move out
  of "not tracked". The new team assist page
  (`GET`/`POST /projects/{id}/assist/team`) shows the RBS as an indented list
  plus a plain-text twin, the RACI matrix, who lacks what (open acquisitions
  and untrained people), the team-assessment trend and open conflicts with
  their actions — filing an assignment, recording an assessment and logging a
  conflict/action are the writes it allows, each through
  `driftless.services.team_writes`. Routes nine Resource Management
  techniques: `organizational_theory`, `pre_assignment`, `virtual_teams`,
  `colocation`, `training`, `team_building`, `recognition_and_rewards`,
  `individual_and_team_assessments` and `conflict_management`. Exposed
  through the generic create/read/update/delete registry —
  `/resource-types`, `/resource-breakdowns`, `/responsibility-assignments`,
  `/acquisitions`, `/training-records`, `/conflict-records`,
  `/conflict-actions` — with `?format=csv` and the delete guard for free;
  `/team-assessments` is create-and-read only, like `/sign-offs`.
- `DRIFTLESS_REQUIRE_USER_AUTH=1` runs the service with **no shared bearer at all**: every
  request presents a session cookie or a `dfl_…` per-user token, so every write lands with an
  actor and no credential audits as `actor=None`. Mint a service account for whatever held
  `DRIFTLESS_API_TOKEN` and give it a token of its own.
- Previously there was no such configuration. An unset `DRIFTLESS_API_TOKEN` made the gate
  **open**, not strict, which is why startup refused it outright — so the only ways to run
  were "shared credential" or "no credential".
- Setting the new flag together with `DRIFTLESS_API_TOKEN` is refused at startup, by
  `deploy/entrypoint.sh` and again by the app. The two configurations disagree about what
  authorizes, and honouring one silently would leave the operator wrong about which.
- The shared credential itself is unchanged: still supported, still un-role-gated, still what
  a fresh install starts on. This adds the way to stop using it, rather than changing what it
  does. Note that `POST /sign-offs`' on-behalf-of `signed_by` only works for a credential that
  resolves nobody, so it does not survive the switch — `OPERATIONS.md` says so.
- **Risk response planning: owners, triggers, residual risk, and exposure that
  reaches cost, schedule, change control and the reports.** `Risk` gains
  `kind` (`threat` or `opportunity`, default `threat`), and `RiskResponse`
  files one plan against a risk — strategy, `Person` owner, trigger, planned
  action, residual probability/impact, cost, schedule impact and status —
  drawn from whichever half of the strategy vocabulary matches its risk's
  kind (avoid/mitigate/transfer/accept/escalate for a threat,
  exploit/enhance/share/accept/escalate for an opportunity), a cross-row rule
  enforced at the API boundary. `driftless.pmbok.risk_facts.gather` is the
  one adapter that turns filed responses into residual exposure, response
  schedule days and response cost, read by the new risk-response planner page
  (`GET`/`POST /projects/{id}/assist/risk-responses`, the register plus a
  no-write what-if calculator and the one write this page allows), the
  project hub's risk-reserve line, the gantt page's schedule-impact note, and
  the risk-register report's new responses table. An open risk with no filed
  response reads "no response planned" on the threat board and outranks an
  equal-severity risk that has one. Exposed through the generic
  create/read/update/delete registry — `/risk-responses` — with `?format=csv`
  and the delete guard for free.
- PATCH and DELETE on every entity now carry an optimistic-concurrency check: send
  `If-Match: <row_revision>` and a stale write is refused with 409 naming the row's
  current revision instead of silently overwriting a concurrent edit. Omitting the
  header is unchanged — it writes unconditionally, exactly as before, so no existing
  caller breaks; adopting `If-Match` is opt-in per request.
- **Responses now carry the revision `If-Match` checks against.** Every entity a PATCH
  or DELETE can reach — the 24 tables carrying `row_revision` — returns it in every
  response, not only in a 409's message text: create, read, list and patch all carry
  it now, so a client can state the precondition it just read without first losing a
  race to find out what to send. `row_revision` stays absent from every request and
  patch body — it is server-managed, bumped on a successful write, never something a
  client sets.
- **Real generated reports are in the repository, under `docs/samples/`.** Deciding
  whether driftless is worth installing meant installing it: nothing tracked here
  showed what it produces. The samples come from the shipped demo store — fictional
  businesses and people built from a fixed anchor by fixed offsets, no wall clock and
  no randomness — rendered by `driftless report all` through the new
  `bin/driftless-sample-reports.py`. Committed generated output normally rots, so the
  Tests job reruns that command on every pull request and diffs every tracked sample
  byte for byte: a template or figure change refreshes the bundle in the same change
  or the run goes red. Four documents are tracked so far; the per-project sets follow.
- **The schedule-network calculator, with crash/fast-track/levelling previews and a
  critical-chain extension.** `/projects/{id}/assist/schedule` draws the newest approved
  baseline's network — the critical path(s) and float per task, as an inline diagram plus
  its text twin — read through the new `pmbok.schedule_facts` adapter, the same "newest
  approved baseline as of the as-of" gate `web.gantt` uses. `?crash=<task>:<days>` and
  `?fast_track=<predecessor>:<successor>` each preview one scenario over that SAME network
  — never both at once, never a write — through `services.schedule_scenarios`. A
  critical-chain view sits alongside it, sized from the safety recorded on any three-point
  duration estimates on the critical chain and clearly labelled as the Driftless extension
  it is, cited to no PMBOK-6 clause. The page's one write, "Propose as a baseline change",
  recomputes the active preview server-side and files it as a draft `Baseline` (with lines)
  plus a `ChangeRequest` describing it — never the live plan itself; approving the change
  and promoting the draft is the existing generic `PATCH /baselines/{id}` /
  `PATCH /change-requests/{id}` step. Routes six more techniques through
  `assess.model.ASSISTANT_ROUTES`: `critical_path_method`, `precedence_diagramming_method`,
  `leads_and_lags`, `schedule_network_analysis`, `resource_optimization`,
  `schedule_compression`, plus the extension `critical_chain_method` — all raised out of
  `GUIDE_ONLY_REASONS` and into `assistance_mode` `CALCULATOR` (`MODELER` for the critical
  chain view).
- The schedule network: `driftless/calc/network.py` computes the critical
  path method over plain `Activity`/`Dependency` objects — forward and
  backward pass, total and free float, every zero-float path, all four
  dependency kinds with leads and lags, a diagram shaped for the method map,
  and non-mutating crashing/fast-tracking and resource-levelling scenarios.
- **Typed task dependencies, project calendars and estimate scenarios.**
  `TaskDependency` is a typed precedence edge between two of a project's own
  tasks — `kind` one of the four PMBOK relationship types (FS/SS/FF/SF),
  `lag_days` signed, a negative value a lead — with a CHECK refusing a task
  that names itself and a write-boundary check refusing any edge that would
  close a cycle through the edges already stored. `ProjectCalendar` plus
  `CalendarException` carry a project's default working-day pattern and its
  dated exceptions. `EstimateScenario` is the stored form of one estimate a
  PM ran — method, value/low/high, actor/as-of provenance, and an optional
  subject task scoped to the estimate's own project. All four new records
  are exposed through the same generic create/read/update/delete registry
  as every other record — `/task-dependencies`, `/project-calendars`,
  `/calendar-exceptions`, `/estimate-scenarios` — with `?format=csv` and the
  delete guard for free. The gantt page draws every dependency as a table
  beside the bars ("Build depends on Design (FS +2d)") and a calendar note
  when the project has one; the task board names how many tasks a card
  waits for.
- **Requirements, traceability, deliverables, acceptance and the WBS — as rows,
  with their own worksheet.** Four new tables: `Requirement` (one stated need,
  filed against a project and an optional source `Stakeholder`), `RequirementTrace`
  (a requirement pointed at exactly one of a deliverable, a task or a backlog
  item — a CASE-WHEN CHECK counts "exactly one"), `Deliverable` (the WBS node
  itself — `wbs_code` and a self-referential `parent_id`, one tree, addressed
  the same way whether it is a summary node or a leaf work package), and
  `AcceptanceRecord` (an append-only verify/accept ledger against a deliverable,
  like `SignOff` — a later verification pass files a new row, never edits an
  earlier one). `driftless.pmbok.mapping`'s scope resolvers now read these rows
  natively: `requirements_documentation` prefers filed `Requirement`s, falling
  back to the stored narrative when none exist; `requirements_traceability_matrix`
  and `work_breakdown_structure` move out of "not tracked"; `verified_deliverables`
  and `accepted_deliverables` read the acceptance ledger, honouring as-of;
  `scope_baseline` now requires an approved `Baseline` AND a WBS to read
  healthy. The new requirements/WBS worksheet
  (`GET`/`POST /projects/{id}/assist/requirements`) shows the traceability
  matrix, the untraced requirements and orphan deliverables named in words, the
  WBS as an indented list plus a plain-text twin, and the acceptance ledger —
  filing a requirement, filing a trace and recording acceptance are the three
  writes it allows, each through `driftless.services.scope_writes`. Routes
  `decomposition` (5.4 Create WBS's own technique) to a WORKSHEET. Exposed
  through the generic create/read/update/delete registry —
  `/requirements`, `/requirement-traces`, `/deliverables` — with `?format=csv`
  and the delete guard for free; `/acceptance-records` is create-and-read only,
  like `/sign-offs`.
- Added the scope worksheet (`GET /projects/{id}/assist/scope`), a single page serving five
  Scope-family techniques that have no calculable output — product analysis (Define Scope, 5.3),
  context diagram, prototypes and benchmarking (Collect Requirements, 5.2), and inspection
  (Validate Scope, 5.5) — each raised from `AssistanceMode.GUIDE` to `WORKSHEET` in
  `pmbok.definitions` and launched, not merely explained, through `assess.model.ASSISTANT_ROUTES`.
  Every section reads the project's existing rows straight off the store: product analysis's four
  plain-language prompts against the `project_scope_statement` narrative row, the context diagram
  against its stakeholders (a small inline SVG plus a table, actors placed evenly around the
  project), the prototype checklist against whether `requirements_documentation` is filed, the
  benchmarking table against `?against=` query params the reader fills by hand (no write), and the
  inspection walkthrough against the project's milestones with status. Nothing is computed and
  nothing is written; a blank narrative body is still filled in through the wizard's one producer
  (`/projects/{id}/wizard`), never a second write path.
- Expand Organization configuration with balanced-scorecard inventory and actionable readiness checks for objectives, metrics, evidence, contributions, ownership, and delivery setup.
- Add business-scoped project-to-objective contribution links shown on the balanced Scorecard.
- Preserve balanced-scorecard perspective evidence on portfolio and program drill pages, including descendant objective status, metric coverage, and contributing projects.
- Add objective-owned metric definitions with directional targets, cadence, ownership, and governed sources.
- Add deterministic as-of evaluation for balanced-scorecard metric observations.
- Add append-only, dated scorecard metric observations with evidence notes.
- Add a balanced Scorecard website view showing all four perspectives and explicit unknown/missing evidence states.
- Add business-scoped scorecard source registry entries for governed connector keys.
- `GET /projects/{id}/assist/stakeholders` is the first CALCULATOR-mode assistant page:
  a power/interest grid, a current-versus-desired engagement matrix with a per-stakeholder
  `?desired=<id>:<level>` what-if and the gap action it opens, and a communications matrix —
  all computed on read from each project's own `Stakeholder` rows, never a second table.
  `stakeholder_analysis`, `stakeholder_engagement_assessment_matrix`, `communication_methods`
  and `communication_technology` move out of `GUIDE_ONLY_REASONS` and into
  `assess.model.ASSISTANT_ROUTES`, raising their assistance mode from guide to calculator.
- A deterministic static-showcase exporter publishes seven real demo pages as a portable,
  fictional, fixed-date and read-only bundle with source provenance.
- Driftless now supports business-scoped strategic objectives across Financial, Customer & Stakeholder, Internal Operations, and People & Capability scorecard perspectives.
- Every technique in the stakeholder family now carries real explanation content — the three
  stakeholder techniques (stakeholder analysis, the stakeholder engagement assessment matrix,
  ground rules) and the four group-decision and data-gathering techniques that share this
  family (voting, autocratic decision making, multicriteria decision analysis, focus groups).
  Each entry has a summary, when to use it, when to avoid it, ordered steps, outputs, pitfalls,
  a worked example, and a PMBOK-6 citation. The stakeholder engagement assessment matrix entry
  notes plainly that this product records only interest and influence for a stakeholder today,
  with no field yet for the current-versus-desired engagement level the technique itself
  produces.
- Techniques now have a `TechniqueDefinition` registry (`driftless.pmbok.definitions.TECHNIQUES`), one entry per `driftless.pmbok.tt.FAMILIES` member, carrying its key, display name, family, source and `source_version` — the edition string, written in one place and carried only by a definition the edition actually names, so an extension Driftless added itself cites no edition rather than a false one. `TT_CATALOG` and `TECHNIQUES` are now both built from the same ten family sets in `tt.py`, so a technique can never be added to one without the other — by construction, not by a developer keeping two lists in sync. The explanation fields (summary, when to use, steps, pitfalls, worked example, further reading) are written in Driftless's own words, never quoted standard prose, and compose in from one module per family under `driftless.pmbok.technique_content`.
- Wrote the explanation content (summary, when to use, when to avoid, steps,
  outputs, pitfalls, a worked example, and further reading) for all eight
  cost techniques: cost aggregation, cost of quality, earned value analysis,
  financing, funding limit reconciliation, historical information review,
  reserve analysis, and to-complete performance index.
- The three integration-family techniques — `change_control_tools`, `information_management`,
  and `knowledge_management` — now carry full explanation content (summary, when to use, when
  to avoid, steps, outputs, pitfalls, a worked example, and further reading). The
  `change_control_tools` entry describes driftless's own structural mechanism: an approved
  `Baseline` is frozen, and only an approved `ChangeRequest` can produce a new version. The
  `information_management` and `knowledge_management` entries are written to stay distinct from
  each other — one is about storing and retrieving explicit information, the other about moving
  tacit knowledge between people — and the `knowledge_management` entry names lessons-learned
  theatre as a pitfall to avoid.
- Explanation content — summary, when to use, when to avoid, steps, outputs, pitfalls, a
  worked example, and further reading — for all seven quality-family techniques: audits,
  design for X, problem solving, quality improvement methods, root cause analysis, test and
  inspection planning, and testing/product evaluations.
- The twelve resource-management techniques (acquisition, colocation, conflict management, individual and team assessments, influencing, negotiation, organizational theory, pre-assignment, recognition and rewards, team building, training, virtual teams) now carry full explanations — when to use each, when it's a mistake to reach for it, concrete steps, and a worked example — instead of bare names.
- **Risk technique explanations.** Every risk-family technique (risk categorization,
  probability and impact assessment, representations of uncertainty, threat and
  opportunity response strategies, contingent response strategies, overall project risk
  strategies, simulation, sensitivity analysis, decision tree analysis, and influence
  diagrams) now carries a plain-language summary, when-to-use and when-to-avoid guidance,
  concrete steps, expected outputs, common pitfalls, a worked example, and a PMBOK-6
  citation.
- **Schedule technique explanations.** The 14 techniques in the schedule family — rolling wave
  planning, precedence diagramming, dependency determination, leads and lags, agile release
  planning, the four estimating techniques (analogous, parametric, three-point, bottom-up),
  critical path method, critical chain method, resource optimization, schedule compression and
  schedule network analysis — now carry full plain-language explanations: when to use each, when
  not to, ordered steps, expected outputs, common pitfalls and a worked example.
- Added explanation content (summary, when to use/avoid, steps, outputs,
  pitfalls, a worked example, and further reading) for the scope technique
  family: benchmarking, context diagram, decomposition, inspection, product
  analysis, and prototypes.
- **The technique library is now a place you can read.** `/techniques` lists every technique
  Driftless works with — the tools and techniques the PMBOK ITTO catalog names, and any
  Driftless adds to its own vocabulary that no process names — grouped by family with a
  one-line summary on each row, and `/techniques/{slug}` gives one technique in full: when to use it, when to avoid
  it, the steps in order, what it produces, the pitfalls, a worked example and — where the
  edition defines one — the PMBOK-6 clause it comes from; a technique the edition names only
  in narrative, or as an umbrella for others, carries no clause rather than an invented one.
  The address is the readable slug the ITTO page already prints, so
  `/techniques/earned-value-analysis` is the page and the raw registry key never appears in a
  URL. Every Tools & Techniques entry on a process page links straight into it, so a reader
  who follows a recommendation lands on the explanation instead of on the name. The library
  has its own primary-nav entry, and a slug matching no technique answers 404 rather than
  failing.
- **Every technique a project runs now leaves a provenance row.** `TechniqueRun` is
  append-only, like `SignOff`: which technique, which process it served, the actor
  who ran it (required), the as-of date, the method context it ran under, the
  technique definition's version, and JSON snapshots of what it read and produced.
  `driftless.services.technique_runs.record_run` is the only writer, and refuses a
  run naming an unknown technique or process, or naming nobody. A frozen
  `Provenance` dataclass (`driftless.pmbok.provenance`) is the shape any future
  calculator returns before a run is recorded. The technique library and the PMBOK
  reference pages list a project's runs in plain wording — the date, the actor,
  and the process it served — when read with `?project=`.
- **`/technique-runs` in the API.** The provenance ledger every technique run leaves
  is readable and exportable like every other record, and appendable through
  `POST /technique-runs` — the same `record_run` writer the decisions page's meeting
  form uses, so an unknown technique or process is refused there too. The CSV
  importer reads `technique_runs` and `risk_responses` kinds, so what an assistant
  page writes round-trips through export and import.
- Added `driftless.pmbok.support`, a pure, store-independent coverage view over the
  technique registry and the ITTO catalog: for each catalog process, which techniques
  it names and whether each has an explanation yet plus its declared `assistance_mode`,
  and whether the wizard can currently produce any of the process's outputs. It reuses
  `state.is_assessable` for assessability and the same producible/output intersection
  `wizard.engine._producible` uses (via the public `wizard.cli.producible_kinds`
  registry) rather than re-deriving either — no number here is a second completeness
  calculation, so it cannot drift from the one `state.py` and `rollup.py` already
  compute. Nothing here takes a session, a project, or an as-of date: a technique's
  explanation and a process's producibility are properties of the product, not of any
  one project's history, so no report or CLI surface was added for it — a plain module
  is the smallest surface that makes the numbers testable.
- **Every technique must now be explained and cited, or say why not.** A new test walks
  the whole technique catalog rather than a sample: each technique needs a non-empty
  summary, when-to-use, when-to-avoid, steps, outputs, pitfalls and worked example, with
  no blank entry inside a list. Adding a technique without writing its explanation now
  fails the suite, naming the technique and the missing field. Citations are checked the
  same way — a technique either references the PMBOK-6 clause that defines it, in the
  edition-plus-clause form the rest of the content uses, or appears in a short exemption
  list with the reason it cannot be cited. That list is held exactly equal to the set of
  uncited techniques, so it cannot quietly grow, and an exemption left behind after a
  citation is added fails too.
- **Decisions and meetings get an assistant.** `GET/POST /projects/{id}/assist/decisions`
  routes `voting`, `multicriteria_decision_analysis`, `autocratic_decision_making`,
  `focus_groups` and `meetings` — the first two as no-write calculators (a vote tally
  against unanimity, majority or plurality; a weighted-criteria ranking naming which
  criterion decides the outcome), the rest as worksheets (an autocratic decider-plus-
  rationale preview; a fixed, plain-steps facilitation agenda per technique; and a
  meeting-evidence log). Recording a meeting is the one write the page allows, through
  `services.technique_runs.record_run` — the project's own provenance ledger, never a
  second store. `driftless/calc/decisions.py` is the pure core behind all of it, with
  `multicriteria_score` named generically rather than after voting alone, since bid
  scoring is the same weighted-scoring problem a later `calc/procurement.py` should
  reuse rather than reimplement.
- The onboarding wizard's `next_step` no longer skips a process the wizard cannot
  produce an output for. Every such step now renders honestly instead, labelled
  `derived` (the output resolves on read from inputs already in the store) or
  `reference` (nothing about the process is tracked yet), naming what it produces,
  which of its inputs the project already has, and — for a missing one — the
  earlier step that produces it, with a link to go work it directly.

### Changed
- **A recommendation's anchor is now the same formula the page writes, not a second
  one that happened to agree.** `Action.technique_anchor` rebuilt the ITTO anchor id
  from the registry's `display_name`, while `pmbok_detail.html` builds the very same
  id from the raw key through `templating.technique_slug`. Two formulas over two
  inputs, equal only because every current display-name override survives humanizing
  and lowercasing unchanged — and nothing made that hold for the next override. The
  model now calls `technique_slug` itself, so the two cannot diverge; the raw
  snake_case key still never reaches a reader, because the slug erases its
  underscores.
- **The guards that claimed to check that agreement now call the real function.** The
  anchor guard took `humanize` off the template environment and then restated
  `.lower().replace(" ", "-")` inline — precisely the suffix `technique_slug` owns —
  so rewriting that hyphen to an underscore moved every rendered anchor and left the
  guard green. Its replacement calls `technique_slug` over the whole closed catalog.
  A second test named for `reference_href` never read it, deriving both sides from
  the slug alone; it now builds a real `Action` for every technique a process names,
  splits the address the model gives, and looks the fragment up on the page that
  address sends the reader to. The drill's single hand-written anchor became a walk
  over the live assessment's own actions.
- The API-only OpenAPI filter (`_leaf_routes`, `_page_route_paths`, and the
  schema generator bound to `app.openapi`) moved out of `driftless.api.app`
  into `driftless.api.openapi`, wired through a new
  `install_api_only_openapi(app)` call. No behaviour changed:
  `driftless/api/app.py` was becoming the service's one god file, and this
  filter — like the request log and metrics middleware before it — wires
  itself onto `app` from its own module rather than living inline.
- `fetch` and `insert` moved out of `driftless.api.app` into a new
  `driftless.api.records`. No behaviour changed. `app.py` still calls `fetch`
  at roughly two dozen sites, so on its own this barely shrinks it — the
  point is that the domain-rules block still living in `app.py` calls `fetch`
  throughout, and could not move to its own module while `fetch` stayed put
  without a live import cycle between the two. This is the module that block
  needs in place first.
- The write rules — the invariants a create or patch must satisfy that a CHECK
  constraint cannot express, because each needs a query — moved out of
  `driftless/api/app.py` into `driftless/api/rules.py`. No rule changed
  behaviour, and `app.py` still decides which rules hang off which route.
  `app.py` drops from 1590 lines to 1187. The `Check` / `CreateCheck` /
  `DeleteCheck` aliases move with the rules they describe, and the 19 rules
  `app.py` registers are now public names — the 14 that only other rules call
  stay private.
- `/status-snapshots`, `/cost-entries`, and `/quality-measurements` are now
  append-only, joining `/sign-offs` and `/metric-observations`: PATCH and
  DELETE both answer 405. A weekly status snapshot, a logged cost, or a
  quality reading now stay exactly what was recorded at the time, so a
  trend line, a spend total, or a quality series can never be edited into
  disagreeing with its own history.
- The README's 270-line capability inventory moved to `docs/architecture.md`.
  It sat between "who owns this" and "who uses it", so a reader arriving at the
  front door had to scroll the whole model before reaching the quick start; the
  README now summarises it in a paragraph and links out. The wording is
  unchanged — this moves text, it does not revise any claim. The citation guard
  reads both files now, so a symbol citation typed into the new document is
  checked the same way one in the README always was.
- **The business-map tests now reach the word-shaping rule instead of re-typing it.**
  The ring-label test rebuilt each knowledge area's label with the same
  underscore-to-space-and-title arithmetic that `naming.humanize` holds, and the
  listing-legend test rebuilt each process state's word the same way. Both spelled
  the rule a second time, so changing it would have moved every rendered label and
  moved the expectations with them, silently. Each now calls the very filter object
  the template renders those strings through, resolved from the Jinja environment at
  call time.
- **A substitution guard, one per page section, so a future copy cannot pass.** The
  rule is replaced with an obviously different shape and the page is re-rendered:
  every completion-ring label, every legend chip and every project state badge must
  come back spelled the new way, with the old spelling gone from the section. An
  expectation rebuilt from the rule's own arithmetic fails there, which a comparison
  of two spellings that merely agree today never would.
- **Three more restated facts in those files are gone.** The cell count and the
  charter process's name are read from the catalog rather than typed out, the
  share-bucket vocabulary is read off the legend the page renders, and the state word
  a listing row shows comes from the process-state enum.
- **The web surface's stylesheet is now a cacheable static asset.** `base.html` sent its
  whole `<style>` block — the light and dark palette, every layout rule, the one
  responsive breakpoint — inline on every request, so a browser could never cache a byte
  of it. The block now lives at `driftless/web/static/driftless.css`, linked from
  `base.html`, and is served from the existing `/static` mount alongside `driftless.js`.
  The design-token and layout-ownership contracts move with it: `tests/test_web_a11y.py`
  and `tests/test_web_responsive.py` now parse `driftless.css` for the palette and the
  breakpoint, and the rule that a colour literal may be declared in exactly one place
  still fails any template that writes one.
- The capacity heatmap reads as a heatmap rather than a wide table. Every cell now
  prints the share of that person's week it takes alongside the hours and draws a bar
  at the same length, so pressure below the amber threshold is visible at all — a cell
  at 5% of capacity and one at 78% used to paint identically. Length and text are not
  colour, so the reading survives greyscale, a colour-blind reader, high-contrast mode
  and print. Person and Capacity stay pinned to the left edge while the week columns
  scroll sideways, so a figure half way across still belongs to a name. The key under
  the grid is generated from the same thresholds the cells are judged by, which fixes
  a legend that had drifted to claiming a 120% overload threshold the code never used.
- Every server-rendered chart (the dashboard's business-wide cost S-curve, the
  portfolio treemap, the cost workbench's cash-flow S-curve, each project row's
  burn sparkline) now draws through one shared `templates/_chart.html` partial.
  An S-curve scales to 100% of its column at a fixed 16:7 aspect instead of a
  fixed pixel box, and carries light gridlines plus x ticks at the first/mid/last
  sampled date and y ticks at 0/mid/max with a thousands separator — the cost
  workbench's curve used to render as an unlabeled 300px line with no axis at
  all. Each chart's own data table now sits behind a closed-by-default
  `<details class="figures">` toggle rather than printed open beneath it, still
  the chart's accessible twin, one keystroke away rather than forced reading.
- CI now runs on pull requests against `staging` and on every push to `staging`, so the staging autolander has a run bound to the exact branch head to gate on. Master is unchanged.
- A `CostEntry.amount` can now be negative. `CostEntry` is append-only, so a
  wrong figure is corrected by a reversing row (the wrong amount negated)
  plus a new row carrying the correct one, never an edit — standard ledger
  practice, and an as-of sum then lands on the corrected figure with no flag
  a reader could forget to filter on. The old `amount >= 0` rule is replaced,
  at both the request schema and the database, by a symmetric sanity range
  (`driftless.models.records.COST_ENTRY_AMOUNT_BOUND`) that still refuses an
  implausible magnitude in either direction.
- `driftless.api.app` builds its app through `create_app()` instead of at module scope.
  The fourteen `@app.get`/`@app.post`/`@app.exception_handler` decorators became
  `add_api_route`/`add_exception_handler` calls inside `_register_routes(app)`, and the
  construction, the four installs, the resource registration, the page mount and the
  versioned twins all moved into the factory in the order they already ran. Importing the
  module used to BE the construction, so a process could hold exactly one app and no
  variation of one could be built or tested; two `create_app()` calls now return
  independent apps with equal route tables. `app = create_app()` stays at module scope
  deliberately — the production entrypoint is `uvicorn driftless.api.secure:secured` and
  `driftless.api.secure` imports that name — and `tests/test_app_factory.py` asserts it
  survives, because losing it breaks the container at deploy while every test, which
  builds its own client, stays green.
- The generic CRUD machinery moved out of `driftless.api.app` into `driftless.api.crud`:
  `_reads`, `_writes` and `_creates`, the eight helpers they lean on (list windowing,
  filter-vocabulary derivation, stale-write refusal, delete-blocking-child reflection),
  and the four constants they read. None of it knows which resources exist — B1 had
  already made it take the app it registers onto — so it was part of the app module only
  because everything was. `driftless/api/app.py` drops from 1186 lines to 777.
  `tests/test_crud_module.py` pins the move in both directions: the machinery answers
  from the new module, `api/app.py` no longer defines it, and the generic list/patch/
  delete routes are still on the live table.
- The database-session lifecycle (`session_scope`, `temporary_factory`, and the
  lazy factory they share) moved out of `driftless.api.app` into
  `driftless.db.session`. No behaviour changed: `driftless/api/app.py` was
  becoming the service's one god file, and the session lifecycle is
  transport-agnostic — it belongs beside the rest of `driftless/db`, not
  wired to FastAPI.
- The five project sub-pages (Gantt, Board, Wizard, Status Update, RAID Log) no longer
  hand-copy their `<nav class="breadcrumbs">` block: `web/templates/_breadcrumbs.html`
  is now the one place it is written, and `tests/test_web_a11y.py` fails any template
  that writes the markup itself rather than importing the macro.
- `driftless.css`'s two `:root` blocks gain a small token vocabulary beyond colour —
  a two-step type scale, a two-step spacing scale and a two-step radius scale — and the
  scattered literals that duplicated them (table cell padding and font size, `.card`
  and `.tile` radii, badge radii and sizes, the skip link's padding) now read
  `var(--token)`. Form controls (`input`, `select`, `textarea`, `button`), previously
  browser-default, now draw from the same tokens. The nine remaining page-local
  `style=` attributes are gone, folded into `driftless.css` as classes or
  descendant-selector rules (`figure`, `.ring`, `.evm figcaption`, `.evm p`,
  `.board-col h2`, `.board-col ol`).
- **A technique marked as a Driftless extension now has to mean it.** The extension
  marker in `driftless.pmbok.tt` is a dictionary of technique key to the written
  reason PMBOK-6 does not tie it to a process, the same standard the citation
  exemptions are already held to; the key set the rest of the code reads is derived
  from it rather than restated, so the two cannot disagree. Three property tests
  walk every member: an extension may not be named by any process (an edition that
  does tie it to one makes the marker stale, and a stale marker silently strips the
  edition string off a definition that has earned it), it may not carry a PMBOK-6
  clause citation while its definition says no clause defines it, and it may not
  ship without a reason. Each failure names the offending technique.
- **A refused wizard body now points at the field it is about.** The wizard's and the
  login page's refusal was one free-text string with nowhere for a keyboard user to land;
  `_alert.html`'s macro grows an optional `fields` mapping (`{id: message}`) that renders
  each as a link to `#id`, still under one `role="alert"` announcement. `wizard_apply`
  attributes the two refusals it authors itself — a blank or oversize body — to `#body`;
  everything `wizard_cli.produce` raises stays general prose, since that text is not
  parsed for a field name it does not structurally carry. Login's refusals stay general
  too, on purpose: "wrong password" cannot say which half was wrong without becoming a
  username oracle. Both producers now share the same field-keyed shape, so a future
  refusal on either page cannot drift the other back into a single string.
- **The error alert, the button hierarchy and label associations are now standards, not
  per-page habits.** `web/templates/_alert.html` is the one place `<p class="card sev-red"
  role="alert">` is written — login.html and wizard.html once hand-copied it byte-for-byte,
  and `tests/test_web_a11y.py` now fails any template that writes the markup itself rather
  than importing the macro. Every `<button>` gains `.btn` plus `.btn-primary` (the form's
  main action — sign in, search, save a snapshot, produce a wizard output) or
  `.btn-secondary` (an auxiliary action beside it — sign out, sign off, record a decision),
  filled in the already-rated `--badge-ink` on `--ink` pairing rather than a new token.
  login.html's and status_form.html's wrapping `<label>`s, and wizard's per-field loop
  (`id="field-{{ f.name }}"`), now carry explicit `for`/`id` pairs instead of relying on
  wrapping alone, and the wizard's `kind` select gets a visible label instead of an
  `aria-label` only a screen reader could read.
- `bin/driftless-import.py` now sends an `Idempotency-Key` on every row, derived from
  the import's id and the row's position. Re-running the same file is therefore safe:
  rows already created are recognised rather than duplicated, which is what recovery
  used to depend on the operator counting `--skip N` correctly to achieve.
- `--skip N` survives as an optimisation (it saves re-sending rows) and seeds the row
  counter so a resumed run lands on the keys the interrupted one used. `--import-id`
  names an import explicitly; it defaults to a hash of the file's contents, so an
  edited file is a different import and the same file re-run is not.
- The KPI strip on the dashboard, the portfolio/program drill and the
  configuration inventory now renders from a single `_tiles.html` macro instead
  of markup each page re-typed. The drill page's comment already promised its
  tiles were literally the same ones as the dashboard's; the copies had in fact
  drifted, with only the dashboard carrying the count-up hook. That difference
  is deliberate and unchanged, but it is a macro argument now rather than
  something two hand-copied blocks can disagree about unnoticed.
- `bin/driftless-gates.sh --audit` now audits a clean venv built to match `pip-audit.yml` exactly (`requirements.lock`-constrained `.[dev]` plus `uvicorn`, `.pip-audit-ignore` applied, bounded retry on a transient network error), and runs as part of the default full run — `pip-audit.yml`'s own nightly no longer executes now that Actions is dead, so this is the only cadence left. `--no-audit` is the declared, printed opt-out for an offline run. `tests/test_local_gates_cover_ci.py` now also covers `pip-audit.yml`, not just `ci.yml`.
- **The method map is legible.** `graph_layout.py` now lays every process, technique
  and artifact into five horizontal bands (Initiating through Closing, PMBOK-number
  order within a band); every technique and artifact is a satellite of the process(es)
  that reach it, placed near its own connected processes rather than in a fixed grid
  cell. Nodes are filled shapes — process a rounded square, technique a circle,
  artifact a diamond — tinted by knowledge area; a process label stays visible at
  rest, a technique's or artifact's shows on hover, on keyboard focus, or once a
  filter narrows the map to a legible handful. Edges default to a faint 0.75px/22%
  line and light up on hover/focus of either endpoint. Filters are pill toggles with
  a reset control and a shape/colour legend.
- **The method map opens on the processes, not the hairball.** `GET /map` draws
  `graph_views.overview()` — the processes in their lifecycle bands, every one labelled —
  instead of all 217 nodes and 1,110 edges scaled into one picture that was thumbnail-sized
  at 390px with 168 labels hidden until hover. Opening a node draws its
  `graph_views.neighbourhood()`: the node, what it touches, and only the ties between them.
  A sentence above the drawing says what is on screen, composed in the page from the view's
  own measured counts; `?view=all` keeps the exhaustive read. The drawing carries its own
  pixel size so labels stay legible and the scroll box moves sideways, not the document.
- Primary navigation now groups the three `/org/…` pages (Configuration,
  Departments, Capacity) under an Organization label — the one grouping backed
  by a real shared route prefix — and every nav link lights when the current
  page is nested under it, not only on an exact match, so `/org/departments/{id}`
  and a PMBOK process detail page now show where the reader is. The item that
  used to read Organization is renamed Configuration, since Organization now
  names the group it sits inside. The group names itself to a screen reader
  rather than sitting beside the list as loose text, so the grouping reaches
  the readers it helps most. The rule stays literal: the project sub-pages,
  the portfolio/program rollups, and sign-in still have no nav ancestor and
  light nothing, unchanged from before.
- **A technique's display name is now the shared word-shaping rule, called rather
  than restated.** The technique registry spelled out its own copy of what
  `driftless.naming.humanize` does, while the module that owns that rule declared
  itself the only holder of it. Because the technique URL slug really is built from
  `humanize`, the two copies meant a rewrite of the rule moved every technique
  address while every visible name stayed exactly where it was, and nothing failed.
  There is one rule now, plus a short table of the PMBOK terms of art title case gets
  wrong; a guard walks every technique and a second one pins the call itself, so a
  fresh copy that happens to agree on the day it is written cannot pass.
- **Removed `Action.reference_process_id`.** It answered "which process names this
  technique", which was how the old reference address was built before a
  recommendation started linking the technique's own explanation page. Nothing has
  read it since, and its own documentation described a case with no caller. Which
  techniques a process names is still derived where it is needed, off the process
  catalog directly.
- **The `pmbok` CLI's identifier guard now covers all three vocabularies it prints, not one.**
  The suite's leak guard derived its forbidden set from the technique catalog alone, so the
  process-group and knowledge-area values in a process's `[group / area]` header were never
  walked and `monitoring_controlling` sat in reader-facing output unremarked. Those values are
  printed raw on purpose — `--group` and `--area` accept exactly those spellings, so each is a
  handle a reader types back, the same call the artifact kinds already make. That reason is now
  rechecked by machine rather than trusted: the walk covers every group and area listing, and
  runs the CLI with each value, so a flag that stops accepting one turns it back into a leak and
  fails. The four process counts the CLI tests asserted as literals are read out of the catalog
  instead; the sizes themselves stay pinned once, where the catalog's own tests pin them.
- **A RAID-log test can no longer skip itself into silence.** It skipped when the shared web
  fixture held no project, so a fixture that stopped seeding one would have removed the whole
  surface from a suite that still reported green. It asserts the fixture instead.
- **A control's completeness now reads the evidence its tailoring mode names.**
  `driftless/pmbok/tailoring.py`'s per-control mode used to be presentation-only —
  it labelled a Monitoring & Controlling control `PREDICTIVE_BASELINE` or
  `ADAPTIVE_COMMITMENT` and printed a reason, but `state.process_state` read every
  control's evidence the same way regardless. It now reads that mode: a
  `PREDICTIVE_BASELINE` control resolves off its native rows alone, never falling
  back to agile or operations evidence even on a hybrid or agile project whose
  OTHER controls do — so a hybrid project's cost control stays pinned to its
  baseline while the same project's scope control reads the team's sprint. A new
  `ControlMode.OPERATIONS_CADENCE` profile (`Project.delivery_mode == "operations"`,
  a new value in that vocabulary — migration `d4f8b3e19a72`) reads every control
  except the fixed change boundary off a department's own service levels,
  incidents and recurring work (`models/operations.py`, via
  `Project.responsible_department_id`) instead of a project baseline or a sprint.
  `driftless/pmbok/crosswalk.py:EQUIVALENCES` gained two entries
  (`work_performance_information`, `schedule_baseline`) whose resolvers read
  agile or operations evidence depending on the project's own `delivery_mode` —
  one seam, never a second dispatch table. `mapping.resolve` grew an
  `allow_crosswalk` parameter, the one place `state.py` gates the fallback per
  control.
- `pmbok/mapping.py`'s `_approved_baseline` now picks its baseline the same way `adapters.plan_baseline` does — the identical `max(..., key=...)` version pick, not an independently-drifting `sort()[0]` — and its docstring names the selector it mirrors and pins the two against each other in `tests/test_process_state.py`; it still reads through mapping's own batched `_rows` rather than calling `plan_baseline` directly, because delegating the read measurably reintroduces a per-project query (`business_process_cells` at 27 statements against a ceiling of 19) that the PMBOK artifact map's `prefetched` scope exists to prevent.
- `requires-python` is now `>=3.12,<3.13` instead of an unbounded `>=3.12`. CI runs 3.12
  and only 3.12, and the image ships 3.12, so the old declaration promised 3.13 and every
  release after it though nothing has run a line of driftless on any of them. The ceiling
  moves when a CI matrix moves, not before.
- Quality assessment now evaluates linked lower-is-better, higher-is-better, and target-band metric policies instead of assuming every measurement is lower-is-better.
- **A recommendation now links the technique's explanation, not its name.** An
  `Action`'s `reference_href` addressed `/pmbok/{process}#tt-{slug}` — an anchor on
  the ITTO list of some process that names the technique, which shows the technique's
  name and stops there. It addresses `/techniques/{slug}` now, the page that says when
  to use it, when not to, the steps in order, what it produces, what usually goes wrong
  and a worked example. Every surface moves at once: the threat board, a process
  drill-down, `driftless assess` and the Assessment Report all read the one property.
- **The one technique Driftless added is no longer described as missing.** A Driftless
  extension is tied to no PMBOK process by definition, so `reference_href` came back
  empty for it and all four surfaces said "reference only — no linked process yet
  either" — at the exact moment its full page was being served at its own address. The
  library is keyed by a slug index over exactly the keys an `Action` is allowed to name,
  so the link is now total: a `str`, never empty, and the four "nowhere to send you"
  branches are deleted rather than left unreachable.
- **Two tests changed rather than being satisfied.** One pinned the old
  `/pmbok/...#tt-...` address and one asserted the "no linked process yet either" copy
  appears on the threat board. Both encoded the routing decision this change reverses,
  so both were rewritten to the new one; the copy is now guarded absent across the whole
  shipped tree, since once the link became total the old branch stopped being wrong and
  became merely unreachable, which no rendering test can catch.
- **The slug formula moved to a leaf module both layers import at module scope.** It
  lived in the web templating module, which the assessment model cannot import at module
  scope without a circular import, so the model reached it from inside a property body.
  `driftless.naming` imports nothing at all, so both sides reach one function object and
  the deferred import is gone; templates call the filter exactly as before.
- The `id="tt-{slug}"` deep-link anchor on a process's Tools & Techniques rows is kept —
  it is how a bookmark or a link in a note lands on one row of a dozen — and now has a
  guard of its own rather than being incidentally covered by the link that moved off it.
- The seventy-four CRUD resource registrations moved from module scope into
  `_register_resources(app)`, and `_reads`/`_writes`/`_creates` take the app as a
  parameter instead of closing over the module-level global. Importing
  `driftless.api.app` *was* the registration, so there was no way to build a second app
  or to test a variation of one; the same registration now runs against any
  `FastAPI()` handed to it. Ordinary functions rather than an `APIRouter`, deliberately:
  `install_versioned_api` walks `app.routes` flat for `APIRoute`s, and an included
  router hangs its routes off a wrapper it never looks inside, so every `/api/v1` twin
  would have silently disappeared. `tests/test_resource_registration.py` pins both
  halves — a fresh app gets the same routes, and registering elsewhere leaves the
  singleton's table untouched.
- Which resources the API serves now lives in `driftless.api.resources`, split by family,
  rather than in one flat block inside `driftless.api.app`. `driftless.api.crud` knows
  how to give a resource its routes; this module is the only place that says which
  resources exist, so a new one is added next to the family it belongs with instead of at
  the end of a 349-line run. This change moves the hierarchy (business through task) and
  the org chart (departments, people); the remaining families follow. `register_resources`
  is public because `driftless.api.app` calls it, and the per-family registrars are
  private because nothing outside the module does.
- The resource registration block is fully out of `driftless.api.app`. The last family —
  the append-only ledgers and the artefacts hung off a project (status snapshots,
  narrative artifacts, quality metrics and measurements, procurement agreements,
  sign-offs) — joins the other five in `driftless.api.resources`, and the emptied
  `_register_resources` and its `create_app()` call are deleted with it, so
  `create_app()` reads as one sequence again. `driftless/api/app.py` is 391 lines, down
  from 1237 when this work started: `driftless.api.crud` holds how a resource gets its
  routes, `driftless.api.resources` holds which resources exist, and the app module holds
  the factory that assembles them.
- CI and the dependency audit now run on the organization's self-hosted runners
  instead of GitHub-hosted ones. The ban on self-hosted runners for pull-request
  workflows is narrowed rather than dropped: `pull_request_target` still refuses
  one, because that trigger carries the repository's secrets while checking out a
  fork's code. The old absolute assumed anyone could open a pull request here; this
  repository is private and single-maintainer, and the test now records the
  condition — an outside collaborator, or going public — that would make the
  absolute correct again.
- Every page router resolved its own `?as_of=` fallback inline (`resolve = default_as_of if callable(...) else ...` plus `as_of or resolve()`, repeated in nine `create_*_router` factories); they now share one `driftless.web.as_of.as_of_dependency` builder, wired through FastAPI's `Depends` for the GET routes and called directly where a POST route already parsed `as_of` off its form. The `?as_of=` query parameter's name, type and default are unchanged, and a callable default is still resolved fresh per request, never once at mount time.
- The static showcase (`bin/driftless-showcase.py`) now exports the method map, the
  PMBOK/technique/artifact catalogs and their proof page, the organization capacity
  heatmap, the per-project flow/RAID/status/process-map pages, every project assistant,
  and one department's assist workspace, alongside the pages it already carried — 34
  read-only pages in all, still byte-identical run to run at one anchor.
- Corrected every docstring and template comment that still sent a reader to
  `web/pages.py`, the module retired when the page routes were split apart. Each now
  names where the behaviour actually lives — the sign-off write, the threat board's
  pagination, the process-map subject ref, the wizard's field-keyed refusal — and the
  route-shadowing claims point at the test that walks the real app instead of at an
  exemplar module. Mentions that record where a module was carved from are history and
  are kept as they are.
- Added a guard that walks every `.py` and `.html` under `driftless/`, pulls out
  anything shaped like a module path, and fails when the named file does not exist.
  Deliberately historical mentions are recorded once with the reason, and that record
  is asserted exactly equal to what the walk observes, so a stale entry fails as loudly
  as a stale reference.
- A second `StatusSnapshot` for an already-snapshotted date is now accepted
  instead of a 409. `StatusSnapshot` is append-only, so a wrong reading could
  never be edited, and `uq_status_snapshot_project_date` left no way to
  correct one either. The most recently RECORDED row — the higher `id`, never
  `taken_on` order, which two same-date rows can now share — is the one every
  "latest reading" read returns; there is deliberately no backward link from
  a correction to the row it supersedes, since `ChangeLog` already records
  who filed which row and when.
- Technique explanation content (summary, steps, pitfalls, and the rest of
  `TechniqueDefinition`'s explanation fields) now composes from one module per
  technique family under `driftless.pmbok.technique_content`, auto-discovered
  by `collect_content`, instead of living in `definitions.py` directly. A
  family's explanations can now be written in a single new file that touches
  no other module, so the ten per-family content pull requests can be
  authored concurrently without colliding on a shared list. A content module
  claiming a key outside its own family, a key outside the technique catalog,
  or a key another module already claimed fails loudly at collection time.
  `TECHNIQUES` itself is unchanged for every caller: it still has exactly one
  entry per catalog key, and a key whose family module claims no content still
  gets a definition with its explanation fields empty.
- Every technique now carries honest provenance: a technique Driftless added
  itself is recorded as an extension instead of being credited to PMBOK-6, and
  each PMBOK-sourced technique names the edition in a field rather than in
  prose. Which techniques are extensions is read from the one set that decides
  it, so adding one can never leave a false citation behind.
- **Every technique's `summary` now reads for a newcomer, held to the same rule as
  `plain_summary`.** `tests/test_technique_totality.py` calls
  `driftless.pmbok.plain_language.violations` on every `TECHNIQUES.summary` — one
  sentence, at most 25 words, no acronym, no raw identifier — the rule `#316` scoped
  to `plain_summary` alone because most technique summaries were dense PMBOK prose.
  80 of 88 summaries were rewritten in plain language; the other explanation fields
  (`when_to_use`, `steps`, `worked_example`, ...) keep their acronyms and terms of
  art, and `driftless/pmbok/glossary.py` gained entries for the acronyms those
  fields still carry that had none (`bac`, `dmaic`, `eac`, `ev`, `pdca`, `pm`,
  `pmis`, `swot`).
- The last of the import-cycle workarounds are gone. `driftless.web` resolved its four
  public router factories through a `__getattr__` hook, `driftless.api.assembly` imported
  all nineteen page modules from inside `mount_web`'s body, and both
  `driftless.api.openapi.page_route_paths` and the API's 409 handler deferred
  `driftless.web.errors` the same way — every one of them because a `driftless.web`
  module used to import `driftless.api.app`. None does now, so all of them are plain
  module-scope imports and a typo in `driftless.web.__all__` fails at import rather than
  at first use. One deferred import survives, in `driftless.api.openapi`, and its
  docstring now says why it is the only one: `driftless.api.secure` imports the finished
  `app`, so it really does sit on the far side of the graph. Four comments naming a
  `_mount_web` that no longer exists were corrected too.
- The web-mount assembly (`_web_mounted`, `web_mid_import`, `mount_web`, and
  `install_page_errors`) moved out of `driftless.api.app` into
  `driftless.api.assembly`, wired through the same `app.py`-calls-in
  idiom as `driftless.api.logging`, `driftless.api.metrics`, and
  `driftless.api.openapi`. No behaviour changed: `driftless/api/app.py` was
  becoming the service's one god file, and this is the module that guards
  the dashboard router mount against running twice — from either of its
  two call sites, module import and the lifespan backstop. A new test,
  `tests/test_web_mount_once.py`, closes a real gap the move exposed: the
  existing route-table tests compare sets, which silently collapse a
  duplicated route path, so a double mount had no test that could catch it.
- The web mount is one unconditional call again. `_web_mounted` and the
  `web_mid_import()` probe (which read `__spec__._initializing` off every loaded
  module) are deleted from `driftless.api.assembly`, and `driftless.api.app` no longer
  mounts the pages a second time from its lifespan. All three existed to survive the
  `driftless.web` -> `driftless.api.app` import cycle, and that cycle is gone: the
  session, signer and write helpers the page modules needed now live in the leaf
  modules `driftless.api.deps`, `driftless.assess.percent` and `driftless.services`,
  so no module under `driftless/web` imports `driftless.api.app` at all.
  `tests/test_api_import_order.py` keeps its web-first subprocess probes, gains one
  that never starts the app (the order the backstop existed to rescue), and gains a
  structural check so the flag and the probe cannot come back unnoticed.
- The presentation helpers that shape what a template renders — threat cards, the process
  and reference grids, EVM curves, trend series, per-area completeness — moved out of
  `web/pages.py` into a new `web/views.py`. Code motion only; no behaviour changes.
- They never touched a router: each takes rows or engine output and returns plain dicts and
  strings. `web/project_hub.py`, `web/business_map.py`, `report/gather.py` and
  `assess/adapters.py` all call them, and none of those wants an `APIRouter` imported as a
  side effect of asking for a percentage. `pages.py` drops from 924 lines to 561.
- Four names became public because the router now calls them across a module boundary, which
  the package's own no-private-cross-imports rule forbids: `reference_grid`, `process_grid`,
  `LEGEND`, and `_cell_state` — renamed `state_word`, since `cell_state` was already a local
  variable inside `process_grid`.
- **A refused field is now described, not just linked.** `_alert.html`'s field-keyed
  `<li>` carries an `id` (`{id}-error`) alongside its existing `#id` link, and the
  control the refusal is about gets `aria-describedby` pointing at it — the link
  moves a keyboard user's focus, but a screen reader landing on the control in
  isolation had no association to the error text until now. Wired for the wizard's
  `body` textarea (the live case) and its dynamic per-kind `<select>`/`<input>`
  fields alike, so a future field-keyed refusal on either is correct by construction.
  Separately, the three server-mandatory `<select>` controls that carried no
  `required` — the wizard's output-kind picker, the process map's sign-off subject,
  and the shared decision select every sign-off form uses — now declare it. All
  three are always pre-populated with no blank option, so an empty submit was never
  reachable through the UI; the gap was only that nothing told assistive tech the
  field was mandatory.
- **The wizard's current step is now a workspace, not a bare form.** The page names
  the process's own plain-language explanation, "What you need" (each input linked
  to its artifact page and, when missing, to the process that produces it), "How
  you do it" (each technique's support tier in words and a link to run or read it),
  "What you get" (each output naming the on-page form or why it is read instead),
  "In your method" (the Scrum/Kanban practices that crosswalk to this step, read
  from `?method=scrum|kanban` since `Project` carries no method of its own yet),
  and a "See it on the map" link focused on the same process. The producible-kind
  select and the narrative-body label now show the artifact's plain name rather
  than its raw store kind.
- The onboarding wizard's producers no longer write the ORM directly. They moved from
  `driftless.wizard.cli` into `driftless.services.wizard_writes`, alongside the
  status-snapshot and sign-off services web and API already shared, and every one of the
  three now requires a named actor rather than an optional one — the CLI's `wizard apply`
  takes `--actor` and credits it on the ChangeLog exactly as an authenticated web or API
  write already was, which now hands in the same identity `get_session` resolved for the
  request instead of leaving the service to invent one. The stale-write precondition
  check moved out of `driftless.api.crud` into `driftless.services.concurrency`, which
  `crud` now imports rather than keeping its own copy.

### Fixed
- Fixed the four report surfaces `adapters.plan_baseline` calls that still resolved the live, unfiltered plan instead of the one visible as of the date being rendered: `gather.snapshot_sweep` (and through it `gather.business_curve` and `home._burn_series`'s swept S-curves), `gather.business_curve`'s own window selection, `home._burn_series`'s window selection, and `pages.evm_curve`'s window selection. `snapshot_sweep` now adapts each DISTINCT baseline once, memoized as the sweep first meets it, rather than hoisting a single plan for the whole date range — so a baseline approved partway through a swept window still shows the correct plan on either side of its approval instead of flattening the curve onto whichever version the sweep happened to grab first, and the byte-identity pins against the per-sample adapter now cover that regime instead of being blind to it.
- Backlog items now store `created_on`, `started_on` and `done_on` instead of having them
  reconstructed from the audit trail, which dated an item by when its row was written rather
  than when the work moved. A store seeded, imported or restored into a new database and read
  at an earlier as-of date lost its flow history that way: throughput and the cycle-time and
  lead-time medians were all structurally zero. The migration backfills the existing rows.
- Fixed the capacity heatmap's (`/org/heatmap`) legend swatches rendering as invisible,
  zero-size boxes: `.chip` was declared only inside `home.html`'s own page-local
  `<style>` block, which no page other than the dashboard ever saw, so the heatmap's
  legend read as four bare text labels with no colour key. `.chip` and the rest of that
  page-local block (which held nothing but static rules — no Jinja interpolation) now
  live in the shared `driftless.css`, reachable from every page that links it.
- **The heavy test job now runs one at a time across the repository.** The runner pool is
  several self-hosted runners sharing a single workstation, so test jobs overlapped and each
  got a fraction of the machine: alone the job takes about 21 minutes, and sharing the box it
  did not finish inside its 30-minute budget at all. Five pull requests were cancelled for
  that co-tenancy rather than for anything in their own diffs. The job now queues instead of
  overlapping, and is never cancelled, because the queued run is the one under review.
- **The test job survives a busy runner pool again.** Several self-hosted runners share one
  workstation, so test jobs overlap and each gets a fraction of the machine — the job takes
  about 21 minutes alone and over 30 while sharing, and five pull requests were cancelled at
  their 30-minute budget for that rather than for anything in their own diffs. The budget is
  now 60 minutes. The concurrency group added alongside it has been removed: a group holds
  exactly one pending job and evicts any further arrival, so with six pull requests open three
  were cancelled after one to three seconds having run no steps at all.
- The technique-content tests asserted that every family module was still empty,
  which contradicted the property the package exists to provide: a family's
  explanations are meant to arrive without any existing file being touched, yet
  the first family to land content would have had to edit a shared test — and
  ten concurrent family branches would all have had to edit the same lines. Both
  tests now assert what they meant to: that a technique no module claims is
  still a full registry member with empty explanation fields, looked up rather
  than named, and that every family ships a discoverable module claiming only
  its own keys, whatever amount of content it carries.
- Fixed `adapters.plan_baseline` to gate on its own `as_of`: a baseline approved after the date a report is rendered against no longer becomes that report's plan, closing the last earned-value read path where a later approval could silently repaint an earlier as-of — a break the as-of contract suite had pinned as unfixed, and which now has a pin proving it closed. `progress_history`'s per-session memo is keyed on the baseline it replays against rather than the project alone, so two as-ofs selecting different plans no longer share one cached history while two selecting the same plan still share one replay.
- The demo's board cards now carry real `created_on`/`started_on`/`done_on` dates, so the
  flow surfaces read honestly at the 2026-07-01 anchor instead of showing a trailing week's
  throughput of zero and cycle- and lead-time medians of zero. The cards trace the same
  story the seeded sprint reviews tell — two closed inside the first iteration, the deferred
  fuel log picked up later, carried over and finished four days before the anchor — so the
  durations are a spread rather than one number repeated three ways. Writing a backlog item
  through the API accepts those three dates as well; a caller that omits them still gets the
  audit-trail replay.
- Static showcase: every `/static/*.css` link is inlined (the method map's `map.css` was a dead link, so the export lost its legend and controls), and an unavailable link inside an SVG stays an SVG element instead of an HTML `span` that stopped the treemap painting.
- S-curve end labels stack when planned and actual finish within a line of each other, and never sink into the x ticks.
- The dashboard, threat board and project hub rail now read "no data yet" and a real plural ("1 milestone slipped", "2 milestones slipped") instead of `n/a` and `milestone(s)`.
- **Every catalog technique is now reachable from a process.** Nine `TT_CATALOG`
  members had no process naming them, so a reader could never arrive at them from
  the ITTO catalog: `autocratic_decision_making`, `benchmarking`, `focus_groups`,
  `multicriteria_decision_analysis`, and `voting` are now attached to Collect
  Requirements (5.2); `cost_of_quality` to Plan Quality Management (8.1);
  `reserve_analysis` to Control Costs (7.4); `team_building` to Develop Team (9.4);
  and `stakeholder_engagement_assessment_matrix` to Monitor Stakeholder Engagement
  (13.4) — closing the gap where the stakeholder evaluator already recommended that
  last one by name with no ITTO route behind it. Separately, `driftless.pmbok.tt`
  now exposes `EXTENSIONS`, a named subset of `TT_CATALOG` for real techniques the
  edition does not tie to a process; `critical_chain_method` is added to the
  vocabulary as the first member, marked as a Driftless extension rather than
  folded silently into the PMBOK-6 set. A property test asserts every catalog
  member reaches a process or is a named extension, computed from the live catalog.
- **Nothing in the tree only makes sense on one machine.** `README.md` and `CLAUDE.md`
  sent the reader to a venv at an absolute path inside one user's home directory, which
  is a dead end for every other reader; both now describe building the venv a clone
  needs, and keeping one outside the checkout is documented as the second setup it is
  rather than as this machine's. A workflow comment named the private sibling repository
  its dedupe shape came from — the reason it is shaped that way was the useful half and
  stays. `tests/test_governance_contract.py` described another repository's scanner, its
  file layout and the fact that its check passes without reading anything; the reasoning
  for why this repo checks its own README survives without naming anyone. `.mailmap` is
  deleted: it folded two personal addresses onto a third, so every address in it was one
  the file itself published. Four guards keep it that way — no tracked file names a home
  directory, none names a repository but this one, the changelog carries no authoring
  scaffold, and no `.mailmap` comes back.
- **A changelog fragment carrying markup is refused rather than published twice.**
  `bin/assemble-changelog.py` validated fragment *names* and never their content, so two
  closing tags from an authoring tool folded into `CHANGELOG.md` and from there into the
  v0.1.0 release notes, where a commit cannot reach them. `read_fragments` is the one
  place preview, `--check` and `--release` all pass, so the check sits there and names
  the file and the tag it refused. Code spans and autolinks are removed before the scan,
  so a tag quoted as an example, a `<https://…>` link and `limit > 100` all still read
  as the prose they are.
- The Gantt page and the capacity heatmap now gate their baseline picks on `adapters.approved_as_of`, the same approval-date rule `plan_baseline` applies for earned value: a baseline approved after the as-of a page is rendered for no longer repaints that page's bars or books its hours into the capacity grid on a later render, and a baseline with no recorded `approved_at` stays visible at every as-of, matching `plan_baseline`'s own null policy exactly.
- **The committed method-map sample is the method map.** `bin/driftless-sample-reports.py`
  took the first `<svg>` on `GET /map`, and the legend renders a swatch per shape and per
  knowledge area above the graph — so `docs/samples/2026-07-01/method-map.svg` had only ever
  held a 153-byte legend chip. The graph is now picked out by its `aria-label`, which also
  survives a change to which view the page opens on, and the sample is regenerated. The
  drift gate never caught it: rerunning the generator and diffing the bytes proves the
  generator is deterministic, not that it captured the right element, so the bundle is now
  checked for the map's own identity as well.
- **The method map no longer claims four members belong to Closing.** The layout used
  to hand any member with no tie the last lifecycle band as a fallback coordinate, so
  three artifacts and one technique — accounted for elsewhere in the catalog, and so
  correctly not counted as orphans — were drawn at the bottom of the Closing band as
  though the method placed them there. Nothing in the catalog says that. Those members
  now sit in their own captioned tray below every band, clear of all five, and the map
  says in words what the tray is instead of leaving a reader to infer a lifecycle home.
  A component artifact (the work breakdown structure, part of the scope baseline) is no
  longer swept up in the same fallback either: it inherits its parent's band, because
  it does have a tie — just not a process's. The tray's membership is now a named
  contract in the test suite, so a fifth member cannot appear silently and a member
  that grows a real tie has to be taken off the list on purpose.
- A process page's Tools & Techniques list now shows a technique under the same
  name its own technique page does. The list built the name from the raw key by
  title-casing it, which is exactly what the registry's display names exist to
  correct, so "To-Complete Performance Index" and "Design for X" were spelled two
  ways depending on which page you were reading. Both pages now read the one name
  the technique registry holds.
- A technique Driftless added to its own vocabulary now shows the recorded reason
  the PMBOK-6 edition's processes do not name it, instead of only stating that
  Driftless added it.
- `docs/architecture.md` now carries a `## Pages` list — every page the app serves, one
  bullet each, address first — and the suite reads it against the live router in both
  directions. A page mounted with no line there fails, as it did before; a line naming an
  address nothing serves now fails too. It did not: a mutation audit added a phantom
  `/ghost-page` to the document, and separately un-mounted a real page while the document
  still named it, and the suite stayed green through both. Each bullet's primary-nav mark
  is walked against the nav template's own links rather than kept in step by hand.
- **`driftless pmbok` prints a technique's words, not its catalog key.** The listing and
  `show` read each technique's display name out of the technique registry, the same
  registry the technique library pages, `driftless assess` and the assessment report
  already use, so the terminal no longer asks a reader to decode `to_complete_performance_index`
  and gets the PMBOK terms of art that plain title-casing spells wrong. Inputs and outputs
  keep their artifact-kind keys: nothing owns a display name for an artifact kind, and the
  key is the handle a reader carries onward to `driftless wizard apply --kind`.
- **The test that pinned the leak is reversed, not deleted.** `tests/test_pmbok_cli.py`
  asserted a raw technique identifier was present in the output, which is what kept this
  one surface behind every other while the rest of the product moved to readable names.
  Its replacement walks the whole technique catalog over every command's output and fails
  on any raw identifier — limited, as the pages' equivalent guard is, to keys carrying an
  underscore, since a one-word key is spelled exactly like the word for it and no walk can
  tell prose from identifier there.
- `pmbok_detail.html` and `wizard.html` printed every ITTO input, output and
  tools-and-techniques name as the raw catalog identifier (`expert_judgment`,
  `project_management_information_system`) instead of language a reader can parse.
  Both pages now run the same `humanize` filter already applied to group and area
  names over these lists too. The artifact status lookup in `pmbok_detail.html`'s
  `itto` macro still keys off the raw identifier — only the printed label changed —
  so a technique's or artifact's status badge keeps resolving exactly as before.
- **The business process map no longer pushes the page sideways.** `/process-map` scrolled
  the whole document 475px at 1280 and 1357px at 390 even though the grid sat in a scroll
  container: the off-screen text inside its cells is absolutely positioned, so with no
  positioned ancestor it laid out against the page rather than the box and escaped the
  box's clip. The shared scroll container is a containing block now, so a wide grid scrolls
  inside itself on every page that uses one. The grid's own headings also freeze while it
  scrolls — the knowledge-area column at the left edge, the process-group headings at the
  top — so a figure in the middle of it keeps both of the words that say what it counts.
- A recommended action's technique is now validated against the technique registry and named in the CLI and Assessment Report by its display name, with a link to its reference page when a process names it and a plain "reference only" statement when none does or no assistant exists yet — instead of naming a technique nowhere the reader could act on it.
- **A release tag can no longer outrun the version its tree declares.** `v0.3.0` was tagged
  from a tree still declaring `0.2.0`, so the package metadata and the showcase exporter's
  default `--source v<__version__>` both named a release that was not the one being
  published. `docs/release-publishing.md` had always said to bump `pyproject.toml` and
  `driftless/__init__.py` first; nothing enforced it. The tag-triggered workflow now refuses
  a tag that does not match both declarations, and refuses the two declarations disagreeing
  with each other.
- **The repository-name guard can see the private sibling.** This tree is snapshotted
  verbatim into a public repository per release, so the guard in
  `tests/test_governance_contract.py` exists to stop any sentence naming a sibling
  repository from shipping to strangers. Its lookahead ended on `\b`, and a word boundary
  sits between `driftless` and the `-` that follows it — so the one name the check was
  written to keep out was the only name it could never flag, while unrelated repositories
  were caught normally and made the check look like it worked. The lookahead now has to
  reach the end of the name, with `.git` allowed through because a clone URL carries it
  and still names this repo. A table of cases fails if the boundary comes back.
- Fixed a 500 answered by a raising route to carry the same `X-Request-ID` its log line does. `driftless.api.logging.log_request` stashes the resolved id on `request.state` before `call_next`, so `driftless.web.errors.page_server_error` — the handler that actually answers a raising route, above the logging middleware — reads it back and stamps it on the response it builds, page or JSON API alike, closing the one case the correlation id most exists for: an operator reading a 500 tying it to what the user actually held.
- Fixed the `risk_report` disposition in `driftless/pmbok/mapping.py` and the matching row in `docs/pmbok-mapping.md`: both used to credit the risk report with "the seeded Monte Carlo," but `monte_carlo_completion` is a sprint-velocity completion forecast with no caller outside `driftless/calc/` — no rendered report runs it. Both now say the risk report is the register plus derived exposure, and note plainly that the only Monte Carlo in the codebase forecasts schedule completion and is not wired into any risk output.
- **`bin/driftless-sample-reports.py` refuses an `--out` it does not own.** It deletes
  before it writes, and `--out` is whatever an operator typed, so `--out docs` would have
  cleared hand-written documents on the reasoning that the subtree it removes is named
  after an ISO date. It now takes the rail its sibling `bin/driftless-snapshot-pages.py`
  already had: it writes only into a directory it created — marked by a file committed
  with the samples, so a fresh clone regenerates its own bundle in place — one that is
  empty, or one that does not exist yet, and refuses anything else by name. The clear no
  longer ignores errors either, so a half-removed subtree fails where it happens rather
  than as a puzzling drift diff in CI.
- Fixed the API to refuse to start when `DRIFTLESS_API_TOKEN` is unset, instead of quietly serving the whole API unauthenticated with only a warning in a log nobody reads. Local development keeps a way to run open — `DRIFTLESS_ALLOW_UNAUTHENTICATED=1`, an explicit opt-in — and still warns on that path.
- Fixed the page snapshot and static showcase tools so their TestClient lifespan schema check uses the same throwaway store as seeded requests, never the deployment database.
- **The published static showcase's method map interacts again, and its copy is true.**
  Read-only means the demo cannot write, not that it cannot be explored: the export now
  re-admits exactly one audited, byte-pinned file, `bin/showcase-map.js`, on the map page
  alone. It lights a node's own name and its ties on hover, on keyboard focus and on
  click, and opens that node's summary — reading only the markup already rendered, with
  no network request, no storage, no form and nothing that writes. Every other script,
  sign-in and form stays stripped, and the page still reads correctly with the file
  absent. The map's copy no longer promises filters the export drops or a page per node
  the bundle does not carry, and the 439 links that flattened to the map's own file name
  — a project wash, one node's neighbourhood, the whole graph — are gone rather than
  quietly reloading the page they sat on.
- **`POST /sign-off` refuses a bad field instead of crashing.** A `decision` or
  `subject_kind` that failed schema validation raised pydantic's own
  `ValidationError` with nothing catching it, so the request fell through to the
  catch-all 500 page. It is now wrapped exactly as `status_submit` next door
  already wraps `StatusSnapshotIn`: `raise HTTPException(422, ...)`, which the
  page-route error handler renders as the same "that submission does not parse"
  shell every other page refusal uses, never the exception's own detail.
- Every write request now refuses a field it does not declare with a `422`
  instead of silently discarding it: a typo'd or retired field name used to
  return `201` with the value thrown away, and the caller had no way to tell
  the write did less than it claimed. A parent-scoping foreign key on a
  `PATCH` (deliberately absent from every patch body so a partial update can
  never re-parent a row) still lands as a no-op rather than a `422`, exactly
  as before. The threat board's and attention rail's hidden `signal` input,
  already ignored by the server, is removed from both sign-off forms now that
  posting it would trip the same check.
- **Technique citations that could not be right are now blank rather than plausible.**
  PMBOK-6 numbers a process's inputs, tools and techniques, and outputs in that order, so a
  technique can only be defined under the middle one — two cost techniques cited an outputs
  subsection and cannot have been correct. Three risk citations contradicted their own
  siblings: two response-strategy families shared one leaf clause number, which two
  separately named families cannot do, and two more sat under a different process than every
  technique beside them. None of them could be corrected from anything in the repository,
  so each was blanked and the reason recorded next to the technique's key, on the principle
  that a missing citation is honest where an invented one is not. Their pages now show no
  Source block instead of a wrong one.
- **The citation guard now checks meaning, not just shape.** It reads the clause number
  itself: the subdivision naming the tools-and-techniques list must be the tools-and-techniques
  one, and no two techniques may claim the same leaf clause unless the collision is recorded
  with the reason it is benign. Both records are asserted exactly equal to what the registry
  actually shows, so a stale entry fails as loudly as a missing one, and neither is a table of
  correct clause numbers.
- **A permanently skipped test now exercises the fallback it was named for.** Every technique
  carries content, so the empty-definition test had skipped for as long as that stayed true,
  claiming coverage that lived nowhere — the empty-content fallback in the registry was reached
  by no test at all. It now calls the fallback directly with a key no content module claims and
  requires every explanation field, read off the dataclass, to be at its empty default.
- The technique library no longer prints a raw registry identifier to the reader. Two integration techniques cross-referenced each other by key, so the index and a detail page showed a word only the code speaks; the cross-reference is kept and now reads the way a reader would say it, and a walk over every technique on every library page fails on the next one.
- A technique's detail page now says where the technique comes from: a technique the PMBOK Guide names shows the edition, one the registry leaves uncited says so rather than growing a clause number, and the techniques Driftless added to its own vocabulary say plainly that no clause of the standard defines them.
- Every family heading a detail page links back to is now checked by machine, so a "back to the library" link can no longer point at a fragment the index does not name.
- The trend chart now plots one point per date when a `StatusSnapshot` date
  has been corrected, reading the most recently recorded row rather than
  whichever the query happened to return first. Same-date rows became
  possible when `uq_status_snapshot_project_date` was dropped; this settles
  the tie the constraint used to make impossible. `pmbok.mapping` spells out
  the same tiebreak, though its answer was never in doubt — it reads a date
  every same-date candidate agrees on.
- Fixed the last live temporal break: a scorecard metric's threshold, direction and cadence no
  longer regrade history when they change. `scorecard_metric_definition` becomes a versioned
  definition — dated rows sharing one `(objective_id, name)`, the one in force chosen per report
  `as_of`. A PATCH of any grading input is now refused, not quietly dropped: it is a new row.
- The web surface no longer prints the bare `n/a` shorthand for a figure nothing
  has computed yet -- every tile, table cell and chart label now says `no data
  yet` instead. The `item(s)`/`day(s)`/`month(s)` pluralisation shorthand is gone
  too, replaced by a real singular or plural everywhere it appeared. The wizard's
  "In your method" prompt and the method map's project overlay no longer tell a
  reader to type `?method=scrum` or `?project={id}` into the address bar -- both
  now offer real links to the same page instead. The dashboard subtitle no
  longer names the internal `driftless.calc` module, and the method map,
  totality proof, method profile and artifact catalog pages each open with one
  plain-language sentence saying what the page is for.

### Security
- **The backup dump is encrypted where it lands.** `bin/driftless-backup.sh` piped `pg_dump`
  straight to a plaintext `.dump`: file modes were the only thing between the whole database and
  anyone who reached the disk, the backup directory, or the off-host copy the operations guide
  asks for. It now writes `driftless-<stamp>.dump.age`, encrypted **in flight** to the age key
  that already had to exist and already had to be escrowed — the one the secrets overlay is
  proved against on every run — so there is no second secret to keep and no window in which the
  cleartext exists on disk. Restore-verify decrypts into `pg_restore` the same way, which makes
  one run prove both that the dump restores and that the escrowed key opens it. Restoring now
  reads `age -d -i <key> <backups/driftless-<stamp>.dump.age | pg_restore …` (*OPERATIONS.md →
  Restoring*). **An existing plaintext `.dump` is not readable by the new procedure and not
  rewritten by it** — keep the old restore command with those files, or take a fresh backup.

### Docs
- `OPERATIONS.md` now states the recovery objectives: RPO is unbounded because no schedule ships with the backup script, RTO is untimed because the bare-host restore has never run as a drill, and retention and offsite storage are both manual — named as gaps, not invented as a policy nothing enforces.
- Document the balanced operational scorecard, its evidence and configuration model, and the sequence for replacing the finance-first dashboard.
- `COMPETITORS.md` cited code by line number and five of those nine citations had drifted onto unrelated code — a `stamped_percent` 210 lines away, an `is_suppressed` 9 lines away, a bounds validator standing in for a create body, and a test function two lines below the number naming it. Every code citation now names a symbol instead, which survives an insertion above it, and `tests/test_docs_competitors.py` reads each one and refuses a line number coming back.
- **The coverage floor's rationale no longer carries a number that rots.** The comment above
  `--cov-fail-under` claimed the suite measured 99.64% of 4935 statements and that the floor
  left ~22 statements of slack. The tree has since more than doubled, and at 11865 statements
  the real slack is one: 95 missed statements still pass, 96 fail. The comment now says how to
  re-derive the measurement from the run's own TOTAL line instead of restating it, and records
  that the measurement is deterministic — two `-n auto` runs on a loaded host and one serial
  run produced byte-identical missed-line sets — so a drop is an uncovered line, never xdist.
- Every resource example in the agent and admin guides now addresses `/api/v1/…`, the
  canonical path, rather than the unadvertised bare alias they were written against before
  the version existed. Both guides are executable, so these paths are exercised rather than
  asserted.
- The guides now also say which addresses are deliberately *not* versioned, so a missing
  `/api/v1` reads as the rule it is instead of an oversight: the operating endpoints
  (`/health`, `/health/ready`, `/metrics`) and the browser's own form posts, such as
  `POST /projects/{id}/wizard/apply`, which answer a redirect to a page rather than a
  resource.
- **The documentation stopped telling the truth about the code, and now a test says so.**
  `README.md`'s gate-runner section described `--migrations` and pip-audit as opt-in and told
  the reader to point an environment variable at a database; both stages are part of a plain
  `bin/driftless-gates.sh` run, nothing anywhere reads that variable, and the migrations stage
  starts its own Postgres and hands the suite the URL. The section now lists every flag the
  script accepts and says what a bare run actually does, and
  `tests/test_docs_numbers_are_measured.py` reads the flag list back off the script's own
  argument parser, in both directions — a flag added there is undocumented until the README
  names it, and a flag the README shows must still be one the script accepts.
- `docs/decisions-superseded.md` quoted the no-JavaScript contract out of a module that was
  split into four and no longer exists. It now quotes `driftless/web/status.py`, which states
  it beside a form that actually posts. The citation guard only ever read two documents, which
  is why nothing caught it; it now reads every tracked document under `docs/`, and it catches a
  path with no symbol on it as well as a symbol the cited file does not define.
- The measured numbers in `docs/architecture.md` — the process count, the search window, the
  staleness threshold and the capacity heatmap's horizon and ceiling — were restated in prose
  with nothing reading them back, while the identical sentences in `docs/user-guide.md` were
  pinned. They are pinned now too, off the same constants, as is the user guide's count of the
  home page's KPI tiles, which the home template decides.
- The technique library's index page claimed to explain every technique the PMBOK ITTO catalog
  names, when it also renders the ones Driftless adds to its own vocabulary that no process
  names. The page and its changelog entry now say what they actually show.
- Two pages listed the reasons a technique may carry no clause citation as though the list
  were complete; the live exemption set holds reasons neither of them named. Both now send the
  reader to the set itself, where the reason is recorded beside the technique it excuses,
  instead of keeping a copy that falls behind it.
- An unreleased fragment announced the citation test while stating a citation that test would
  have failed, naming a module that imports `create_sign_off` rather than the one that defines
  it. Corrected to the address the README actually carries.
- `docs/architecture.md` had two merge artifacts from the many branches folded into this
  campaign: a duplicated **Calculation core** bullet (folded into one, estimating joined to
  the cost workbench it sits beside) and a garbled sentence naming two disagreeing table
  counts for `row_revision` plus an orphaned "same seed, same percentiles" fragment left
  dangling ahead of the quality-tools bullet. Both read correctly now, with no measured count
  restated in prose — the file's own stated rule.
- Document the method map: `docs/user-guide.md` gains a "Reading the map"
  section in plain words (the three node shapes, what a tie and its dash
  pattern mean, `?project=`/`?focus=`, and what the no-JS list below the
  drawing is for), and `docs/architecture.md` names the derivation chain
  from the catalog through the graph, the layout, the page and the graph's
  own JSON shape.
- Commit a rendered sample, `docs/samples/2026-07-01/method-map.svg` — the
  theory map, no project — written by `bin/driftless-sample-reports.py`
  alongside the report documents, so CI's sample-drift gate byte-diffs it too.
- Pin `OPERATIONS.md`'s Public paths list to the live route table and
  `driftless.api.secure.is_open_path`, so a path added to (or dropped from)
  either side without the other cannot go unnoticed.
- `docs/pmbok-mapping.md` cited code by line number on the stated argument that a dense
  per-process table needs the line as the address — the same style `COMPETITORS.md` had
  already dropped for going stale unnoticed. An agent adding a module-level import to
  `driftless/assess/scorecard.py` instead wrote it inside the function body to keep
  `evaluate_metric` on the line this file cited, with no import cycle forcing that shape:
  the citation format had bent production code around itself. Every citation already named
  the symbol, so the line number carried nothing the symbol didn't. Citations are now
  `path:symbol`, and `tests/test_docs_pmbok_mapping.py` resolves each one the way
  `tests/test_docs_competitors.py` resolves its own, and refuses a line number coming back.
- `README.md`'s one code citation named `api/app.py:create_sign_off` — a path that never existed at the repo root, since the file lives at `driftless/api/app.py`. It now cites `driftless/services/sign_offs.py:create_sign_off` — the module that DEFINES the function, not one of the modules that import it — and `tests/test_docs_readme_citations.py` reads it back: every citation must name a symbol the cited file actually defines, and no citation may address a line number, the same discipline `tests/test_docs_competitors.py` and `tests/test_docs_pmbok_mapping.py` already hold their own docs to.
- Moved the performance, accessibility and responsive floor sections out of `README.md` into `docs/testing-and-quality-gates.md`, alongside the CI/snapshot/showcase reference material that moved there earlier.
- Moved the `## Sample reports` section out of `README.md` into `docs/testing-and-quality-gates.md`, completing the split of testing/quality-gates reference material out of the README.
- The prose describing the technique library now matches what shipped, and two guards keep
  it that way. The user guide and the release note promised a PMBOK-6 clause on every
  technique page; ten techniques carry none on purpose, because the edition defines them in
  narrative or as an umbrella group and one is a Driftless extension — an invented clause
  number is worse than a missing one, so both now say where a clause exists and why it
  sometimes does not. The release note also advertised `/techniques/{key}`, which 404s: the
  route is keyed on the readable slug. `docs/architecture.md`'s web-surface inventory gained
  the two technique routes and their nav entry, and five other pages it had quietly stopped
  listing; it also gained the technique registry, the per-family content package and the
  support-coverage module, which the capability inventory did not mention at all.
  `docs/pmbok-mapping.md` gained the row for explaining a technique, and
  `docs/testing-and-quality-gates.md` documents the totality gate and drops a wrapped-table
  count it should never have written down.
- Two claims in the docs are now machine-checked rather than argued: every GET page the app
  registers must be named in the architecture inventory, so a page cannot ship undocumented;
  and no document may promise a clause on every technique page while any technique carries
  none — a check that runs both ways, so the hedge has to come out if the last citation ever
  lands.
- Comments promising work that has since landed are retired: the technique registry, the
  coverage module and the recommended-action model no longer describe empty fields "a later
  PR fills in", and three stale counts in source docstrings — templates, unnamed techniques,
  processes with no tracked output — are gone rather than refreshed, since nothing rechecks
  a number typed into a comment.
- Record the temporal model decision: as-of documents are already
  byte-identical from an unchanged store, but baseline selection and
  scorecard thresholds are not yet historically reproducible after later
  changes, plus the effective-time, record-classification, hierarchy, and
  organization decisions this schema now stands on.
- Record the verdicts on four earlier decisions against what Driftless does
  today: pagination clamping is affirmed, the no-admin-tier decision is
  superseded, the HTML-snapshot decision is amended with a small rendered
  tier, and the no-JavaScript invariant is affirmed with a regression floor.
- The temporal model decision record now describes baseline selection as it stands after `plan_baseline()` became date-aware: the function filters on `approved_at`, the permissive `as_of=None` reading is named as the live view the re-baseline write guard needs, and the report surfaces still to be threaded are pointed at the exact-set guard that enumerates them — so the record states what is fixed, what is deliberately permissive, and what is left, rather than a break that has since been closed.
- Recorded the baseline-selection reproducibility break as closed rather than half-closed: `docs/temporal-model.md` still described the four report surfaces and the two SQL selections as unthreaded, which the same wave made false, and it now states what actually closed them — a sweep that adapts once per distinct baseline instead of once per span, and one shared `approved_as_of()` predicate for the query side — along with the fact that the byte-identity pins guarding the sweep were blind until a mid-span approval was added to their fixtures.
- Moved the continuous integration, page-snapshot bundle, and static showcase reference material out of `README.md` into a new `docs/testing-and-quality-gates.md`, with a pointer left in its place.

## [0.2.0] - 2026-08-02

### Added
- **A pushed version tag publishes the release notes the changelog already holds.** `v0.1.0` was
  tagged on 2026-07-31 and no GitHub release object ever appeared: every workflow here started on a
  pull request, a schedule, a dispatch or a workflow_call, so a tag started nothing and publishing
  was a manual step nobody took — the changelog said what shipped and the one place a reader looks
  said nothing. `.github/workflows/release.yml` now runs on `v[0-9]+.[0-9]+.[0-9]+`, reads the dated
  `## [x.y.z] - YYYY-MM-DD` section for that version out of `CHANGELOG.md`, and creates the release
  from it with the workflow's own `GITHUB_TOKEN` (`contents: write`, job-scoped; no secret added).
  The notes are read rather than re-assembled because the fragments are already folded and deleted
  by tag time. A tag whose version has no section — or whose section is empty — fails the run and
  writes no notes file, so an empty release cannot be published;
  `tests/test_release_workflow.py` runs that failure, not just the success.

### Security
- **The image installs only distributions whose sha256 this repo committed.** `requirements.lock`
  pinned exact versions, which decides which release the build asks for and says nothing about
  what the index returned; the build then `chmod`ed and ran whatever arrived. The runtime closure
  is now compiled into `requirements-runtime.txt` with a hash per distribution and installed
  `--require-hashes`, so a substituted artefact fails the build instead of shipping. The checkout
  itself installs on a second line with `--no-deps` — pip refuses to hash-verify a directory, and
  without `--no-deps` that line would re-resolve every dependency from the index unhashed and undo
  the first. The new file is compiled under `-c requirements.lock`, so the image, the Tests job and
  pip-audit stay on one version set, and `tests/test_image_dependency_parity.py` fails if they
  drift, if a pin loses its digest, or if the compiled-from name list stops matching
  `[project.dependencies]` plus uvicorn.

## [0.1.0] - 2026-07-31

The first deployable shape of the service:

- **One normalized store** — business → portfolio → program → project →
  workstream → task, plus per-project delivery, RAID, cost, org, sign-off,
  narrative, quality and procurement records, built by an Alembic chain that the
  suite asserts against the models.
- **One validated write path** — a FastAPI CRUD boundary enforcing the
  cross-row rules (parent scoping, approved-baseline freeze, unit/mode
  agreement, no orphaning delete), with every write recorded on the append-only
  ChangeLog.
- **Computed views, nothing stored twice** — the pure calc core (EVM, rollups,
  forecast incl. seeded Monte Carlo), the PMBOK 49-process catalog with derived
  process state, and the assessment engine's ranked attention feed.
- **Server-rendered web surface** — command center, threat board, process maps,
  department, portfolio/program drill and project-hub pages, the wizard and the
  weekly-status form, behind a bearer-token gate with `/health` open.
- **Generated reports** — `driftless report all` from an explicit as-of,
  byte-identical on regeneration, plus the Docker/SOPS deployment with
  restore-verified backups and an API-based import path.

The sections below are every change that landed before the stamp — the audit
campaign that hardened the shape above into a releasable one.

### Added
- **`docs/user-guide.md` — the guide for the person using the product**, the last audience with no
  document of its own: signing in, what each screen answers, filing a weekly status, reading
  RAG/EV/CPI/SPI (why `n/a` is never a zero), CSV and calendar exports, and what to do when a figure
  looks wrong. `tests/test_docs_user_guide.py` opens every address in it as a real signed-in browser
  — form, CSRF pair, cookie, no header — against the demo store, so a label that stops being true fails there.

- **The dashboard's cost S-curve carries its shape as text.** The SVG's `aria-label` named the
  endpoint pair and the two in-SVG end labels repeated it; everything between — where actual crossed
  planned, and how far above or below it sat at each sample — was reachable by eye alone. That is the
  argument that earned the Gantt its table twin, so this is the same answer in the same idiom: every
  plotted point becomes one row (sampled date, planned total, actual total) in plot order, under an
  `sr-only` caption, in the shared `scroll.wide` box. No arithmetic lands in the template —
  `report.gather.business_curve` already computed each sample's date to take the sample and threw it
  away, and now keeps it, so re-deriving the window in Jinja never becomes a second copy of
  `sample_dates` free to drift from the first. No baseline anywhere still means no points, so chart
  and table are absent together, never an empty table under a caption promising rows.

- **`docs/pmbok-mapping.md` — which PMBOK practices this tool implements, and which it deliberately
  does not.** The boundary a PMP-trained reader needs first lived only in reviewers' heads. It is now
  three tables: a vocabulary map (PMBOK's *work performance report* is this tool's *status snapshot*),
  the supported practices each naming the code behind it as `path:line symbol`, and the non-goals —
  WBS decomposition, requirements traceability, activity sequencing and critical path, resource
  levelling, estimating ranges, TCPI, subsidiary management plans, solicitation, closeout — each
  naming the artifact kinds it would have produced. `tests/test_docs_pmbok_mapping.py` makes it
  checked rather than merely written: every citation must resolve to that symbol at that line, the
  counts must be the live catalog's own, and a kind listed as absent that starts resolving turns the
  suite red until the document says so.

**Entered late**, both of the above: they shipped with no line here and are written off the source and
the tests as they stand, not from memory. They sit below the user guide because they landed before it.

- **Milestones and sprints as a calendar anyone can subscribe to** — `GET /calendar.ics` (the whole
  store) and `GET /projects/{id}/calendar.ics` (one project) serve RFC 5545 iCalendar, so dates that
  until now could only be read inside the product land in Outlook, Google or Apple Calendar. All-day
  events, each `UID` off the row's own key so a rename updates rather than duplicates, no clock read
  anywhere, and a hand-written escaper/folder rather than a new dependency.

- **The surface holds together down to a tablet.** Every wide surface — the RAG rollup, the
  person × week capacity grid, the PMBOK and process grids, the Gantt's text twin — assumed a
  desktop viewport and overflowed the page below it. There is now **one** width breakpoint,
  `@media (max-width: 60rem)` (960px), argued in `base.html`'s own comment rather than named after
  a device: the dashboard's command split is 36rem of heatmap + 18rem of rail + a 1.5rem gap =
  55.5rem, which stops fitting inside the 2rem body gutters at 59.5rem of viewport. Below it the
  gutters narrow and the SVG charts scale on their viewBox; the flex rows wrap at every width, so
  board columns wrap (a card still reads at 12rem) and a too-wide table scrolls sideways instead of
  clipping. Nothing is hidden or dropped at any width — a manager on a tablet must not decide
  without the column that mattered. `_scroll.html` is the only way a scroll box is written, so
  every one carries `tabindex="0"` and a named `role="region"`: the affordance cannot be mouse-only
  by construction rather than by review. Layout moved out of the page-local `<style>` blocks and
  `style=` attributes into `base.html`, so home.html and drill.html can no longer lay the same
  rollup out differently. `tests/test_web_responsive.py` walks the real routes for the viewport
  meta tag and for every table sitting in a reachable, named scroll container, and pins the
  breakpoint at exactly one; its docstring states what it does not prove — nothing here renders a
  viewport, so how it *looks* at 768px is still an eye check. **Entered late**: this shipped with
  no line here, so it is written off that source and that test as they stand, not from memory of
  what was intended. It sits below the calendar entry because it landed just before it, and moving
  it to the top would say it shipped last.

- **The demo store now shows every surface with something real on it.** Walking the seeded store
  page by page found what a screenshot would have: no task carried a percent complete, so EV, CPI
  and SPI read `0.00` and EAC `n/a` on *every* project — a portfolio that had spent money and
  delivered nothing — and every RAG token on the dashboard was `red` in consequence. Both department
  pages were empty (no project named a department), no task had an assignee, RAID read `0` issues
  and `0` changes everywhere, and three of four milestone statuses and three of four risk statuses
  never appeared. The seeder now carries task progress, assignees, department ownership, RAID and
  quality rows and a fourth project, so the statused three read one red, one amber, one green
  against the deliberate no-data one. Same door as before: every row posts through the validated
  API and every date hangs off `--anchor`, no clock read. `tests/test_demo_web.py` pins it by
  rendering every page and reading the vocabularies off the model's own tuples. 70 rows, not 44.

- **A task board at `/projects/{id}/board`** — `Task.status` has always been a closed vocabulary
  and no view laid a project's work out by it. The columns ARE that vocabulary, not a list written
  into the page, so a status added to the model becomes a column with nobody editing markup (the
  test asserts the rendered set against the tuple, never against four names). A card carries
  workstream, assignee, percent and estimate; dates stay on the schedule and money on the hub. Every
  card prints its status as text, so **blocked** reads as blocked in greyscale. An empty column says
  which one it is, a project with no tasks renders the shared empty state, and the whole board is two
  statements at any task count. Linked from the project hub, beside Schedule.

- **`docs/admin-guide.md` — bare host to trusted instance in one walk**, which until now meant
  assembling `OPERATIONS.md`, `deploy/` and `bin/` in the right order: install, two users and their
  roles, per-user credentials, demo data, the readiness answers for a store current, behind and
  ahead, a verified backup, and rollback written as what it is — *restore the pre-upgrade dump*,
  since an image older than the applied migration refuses to start. `tests/test_docs_admin_guide.py`
  executes its blocks against a real app; the three no unit test can run (a host, TLS, `pg_dump`) are
  marked `manual` with **why**, counted rather than faked, and an unmarked fence still fails.

- **An agent can now drive the wizard's write side with its own token.**
  `POST /projects/{id}/wizard/apply` demanded a CSRF pair from a cookie session, so a client
  holding a per-user bearer token had no path to it — the documented workaround was
  `driftless wizard apply`, whose `change_log` row carries `actor=null`. The pair is now
  required only where forgery is possible: a cookie is *ambient* (a browser attaches it to
  whatever another origin causes), while a bearer token is attached deliberately and no
  cross-origin page can make a browser send one. The gate stamps which credential
  authenticated the request; a cookie still wins when both arrive, so a browser that also
  sends a header still pairs, every other form POST is unchanged, and a viewer's token is
  still refused the write. The guide now runs the token-driven apply and reads the
  `change_log` row back naming its owner.

- **`docs/agent-guide.md` — the loop a non-human client drives**, where integrating meant
  reading source: mint a per-user token, `wizard next`, write the output it names through the
  JSON API, export CSV, read the `change_log` row naming the token's owner. Every fenced
  block is extracted and run by `tests/test_docs_agent_guide.py` against a real app and a
  throwaway store, and an unmarked fence fails too, so no command reaches the guide unrun.
  Rough edge named: a CLI `wizard apply` writes `actor=null` (the entry above closed the other).

- **Signing out is now CSRF-protected**, closing the risk logged when sign-out began
  revoking every device: a forged `POST /logout` could sign a colleague out of every
  browser they used, not just drop one cookie. Protecting it meant a token on every
  page, since the sign-out form sits in every nav — so the seven per-router template
  environments became one (`driftless/web/templating.py`) rendering the token into every
  page and the cookie half onto every response, with no router minting by hand.

- A viewer who submits a web form now sees the designed refusal page instead of a raw
  JSON body in the browser. The role gate sits outside the app, so its 403 reached none
  of the HTML error handlers: a signed-in viewer posting the weekly status form was
  answered `{"detail":"writes need the contributor or admin role"}` on a blank page. The
  gate now decides from the app's own page routes — the same fact the error handlers key
  on, never an `Accept` header — and renders the shared refusal page, whose wording is
  its own: you are signed in as a viewer, ask an admin for contributor access. Every
  other surface is byte for byte unchanged, the JSON API refusal included, and a gate
  that cannot read the route table answers JSON rather than raising. The 401 is
  deliberately untouched on both surfaces.
- Audit rows now name the person: a write made by a signed-in user is recorded on the
  ChangeLog with their username as the `actor`, where every row previously carried
  `actor=None` and "who changed this?" had no answer. The credit is stamped at the one
  session dependency every route already takes, so no write site can forget it — the
  gate resolves the identity once per request and the flush listener reads it off the
  session. The gap is stated rather than papered over: a request authorized by the
  shared `DRIFTLESS_API_TOKEN` bearer resolves no user, so its writes stay
  unattributed, exactly like a CLI or migration write. That token is the bootstrap
  credential; per-user API tokens are their own unit, and nothing here invents a name
  for a row nobody signed.
- `OPERATIONS.md` now names the public paths of a gated deployment — `/health`,
  `/static/…`, `GET`/`POST /login`, `POST /logout`, and nothing else — which credential
  each surface takes, and that `DRIFTLESS_SESSION_SECRET` **must** be set or no session
  cookie ever authorizes (the cookie half fails closed; the bearer half runs open when
  its token is unset). The whole sign-in walk — refused, sign in, admitted by the cookie
  alone, sign out, the captured cookie refused — is now one suite test
  (`tests/test_auth_end_to_end.py`) instead of a hand check, because the gate and the
  login page each passed their own tests while the pair between them was broken.
- The request gate accepts a session cookie as well as a bearer token: with
  `DRIFTLESS_API_TOKEN` set, a signed-in browser is no longer refused 401 for
  carrying a cookie instead of an `Authorization` header. One gate, two credential
  kinds, and the resolved user is left on the request for role gating and per-user
  audit rows to read next. The two kinds default opposite ways on purpose — no token
  leaves the gate open (development), while no `DRIFTLESS_SESSION_SECRET` means no
  cookie can ever authorize, because an unsigned cookie is a forgeable login. A
  cookie whose user was deactivated, or whose session epoch has since been bumped,
  stops working immediately. `/health` and `/static` behave as before, and the login
  surface — `GET`/`POST /login`, `POST /logout` — joins them as public: a gate that
  hides the login page can never be signed into, so with a token set no cookie could
  otherwise come into being. Those paths are matched exactly, so a future
  `/login-admin` stays gated; nothing else opens, `/` included.
- CSV import: `bin/driftless-import.py rows.csv --csv tasks` (also `risks`, `costs`
  and `milestones`) posts one flat row per record through the same validated API
  the JSON mode uses — still never a second write path. Each kind's columns are
  declared once in the script, the parent is named by its id column
  (`workstream_id`, `project_id`), and an unknown column, a missing required
  column or a cell that will not coerce is refused with its row number *before*
  anything is posted; a blank optional cell is omitted rather than sent as `""`.
  `bin/sample-tasks.csv` is a worked example. JSON stays the default mode.
- Sign-in: `GET`/`POST /login` and `POST /logout` remember a user in an HMAC-signed
  `HttpOnly` cookie (`DRIFTLESS_SESSION_SECRET` is required to sign in;
  `DRIFTLESS_COOKIE_SECURE=0` for local HTTP), behind a CSRF-bound form with one
  message for every failure. The nav gains Sign in / Sign out; nothing is gated yet.
- Structured request log: one JSON line per HTTP request (timestamp, method,
  path, status, `duration_ms`, client host) on the `driftless.request` logger.
  Silent until an operator raises that logger to `INFO` — see "Request log" in
  `OPERATIONS.md`. Query strings, bodies and `Authorization` headers are never
  logged.
- `OPERATIONS.md` gained an **Upgrading** section: back up, pull, rebuild; the
  container migrates before it serves.
- Test-only hardening from the audit (no behaviour change): the guard refusing a
  baseline line a PATCH would slide into a *different* approved baseline is now
  executed directly, so deleting it can no longer ship silently; the two
  free-moving FK allowlist entries (`Person.department_id`, `Task.assignee_id`)
  now prove the move lands and persists instead of asserting nothing; and the
  CSV export/import round trip POSTs the importer's payloads through the real
  `/milestones` route, re-exports, and compares every column field by field.
- Three fallbacks the suite never walked are now pinned by tests, each through the
  surface it protects. The token gate answers a refusal in JSON, and warns, when it
  cannot read the app's page routes — a shape it does not recognise must not turn
  every later request into a 500, including the sign-in redirect a browser needs to
  recover. `render_document` raises and names a slug no document claims, so the CLI
  cannot write an empty report and exit 0. And an edit that does not move a program
  — a rename, or restating the portfolio it already lives in — is allowed while the
  program still has projects; only a genuine move is refused.
- Tests pinning evaluator verdicts that were previously unasserted: the amber
  risk score is pinned to its computed value (a mutated formula now fails the
  suite instead of sailing through), and procurement, stakeholder and resource
  each prove their populated healthy path — rows present, none problematic —
  returns a clean green rather than earning it from the empty-register early
  return.
- Tests: the Monte Carlo forecast is pinned to literal p50/p80/p90 dates for a
  fixed seed (a run-twice self-comparison proved only within-process agreement),
  and `assess_contingency`'s refusal of a contingency rate outside 0..1 is now
  covered.
- Report-document tests now prove isolation and row identity: every document
  fixture seeds a second project whose rows must never bleed in (charter,
  scope & baseline, forecast, weekly status, schedule, risk register,
  department), and the Cost/EVM test seeds nine pairwise-distinct figures and
  pins each table row — label and value together — so swapped rows cannot pass.
- **Surface tests now read values, not presence.** The business map's 49 cells are
  checked cell-for-cell against the rollup's own shares and share-band washes (an
  under-half share must wash `warn`); the gantt "Schedule as text" rows are matched
  row-for-row to the drawn bars and marks; the capacity heatmap proves a four-week
  80 h task books 20/20/20/20 rather than 80 up front, and that only the newest
  approved baseline version windows a task's hours; the EVM and status-trend
  polylines are parsed and matched point-for-point to their computed series; and
  the wizard's 422 for a kind it cannot produce is pinned.
- A change request now records which PMBOK process raised it: `origin_process_id`
  (nullable, validated against the live catalog) on `POST /change-requests`, filled
  in automatically by the wizard form and by `wizard apply --process <id>`.
- **Per-PR changelog fragments** — a PR now records its entry as one file under
  `changelog.d/` (`<PR#>.<type>.md`) instead of editing `CHANGELOG.md`, so two open PRs
  can no longer conflict over the same changelog lines;
  `bin/assemble-changelog.py --release <version>` folds the fragments in at release time.
- The project hub's completeness is now pinned to **the engine's own answer**, not to a
  hardcoded percentage: `tests/test_project_hub_completeness.py` walks
  `state.completeness` and `pages.area_completeness` for the seeded store *outside* any
  prefetch scope and requires the rendered overall figure and all ten area rings to match
  it exactly. Narrowing the hub's `state.prefetched` scope to the wrong project set made
  `mapping._rows` serve every resolver an empty row list — completeness and every ring
  fell to 0% while the page still returned 200 with the rings in place, and the whole
  suite stayed green (only the query guard moved, and it moved *down*). Both tests first
  assert the seed is part-done and its areas disagree, so an all-zero page cannot satisfy
  the equality, and no expected percentage needs editing when the seed grows.
- The process-map legend's completeness is now **derived, not asserted**: a test
  enumerates the states straight off `ProcessState`, the enum the state engine
  computes against, and checks `pages._LEGEND` names exactly that set. A state
  added to the engine and forgotten in the legend now fails this test instead of
  shipping a legend that silently omits a state the grid can render.
- The ten subsidiary management plans resolve against the store and the wizard can
  produce each one (prose required by construction). Plan Scope/Schedule/Cost/Quality
  Management, Plan Communications/Risk/Procurement Management and Plan Stakeholder
  Engagement become assessable — 18 of the 49 processes now have no tracked output,
  down from 26 — and a written plan body is what moves each of them to produced.
- The narrative store and the API boundary accept the fifteen prose artifact kinds —
  the nine subsidiary management plans, the stakeholder engagement plan, the project
  scope statement, requirements documentation, the team charter, basis of estimates,
  and team performance assessments — each stored under its catalog artifact name.
  None is tracked yet: the process map reports them untracked until a resolver lands.
- The catalog now declares PMBOK's conditional outputs (`Process.optional_outputs`):
  `change_requests` on its 22 emitters, `project_management_plan` on its five updaters,
  `approved_change_requests` on 4.6 and `closed_procurements` on 12.3. The state engine
  judges PRODUCED on required tracked outputs alone — a present optional output counts as
  activity (IN_PROGRESS) but can never demote a process out of PRODUCED, and a process
  whose only tracked output is optional is not assessable. All four kinds are untracked
  today, so no completeness figure moves; the change makes a future resolver for a
  conditional kind safe by construction.
- `bin/driftless-snapshot-pages.py` captures every page the app serves as rendered HTML
  from the demo store at a pinned `--anchor`, byte-identically, so a design review can
  diff the whole surface (38 pages today, written to `docs/page-snapshots/`, git-ignored
  like `reports/`). The page list is discovered from the router rather than written down,
  which picked up `/pmbok/{process_id}` — a page the route probe had been dropping.
- The plan-of-plans and the communications record resolve against the store, closing artifact
  coverage at 49 of 49 processes. `project_management_plan` rolls up the ten subsidiary plans;
  `project_communications` reads the note a status snapshot carries, so a number filed is not
  mistaken for a communication made. Both derived, so neither gains a wizard button.
- `change_log` now carries an index on `(table_name, row_id, changed_at)`, the shape the
  dated progress replay filters on. Without it the planner read the ENTIRE audit log to
  answer one project — on a 5,466-row log, `SCAN change_log` at 9.7 ms per read, versus
  1.4 ms searching the index — so every dashboard got slower as the trail grew rather
  than as the plan grew. Declared on the model and added by migration `d1c84b7e0a92`,
  which reverses on its own: an existing store gains it with `alembic upgrade head`.
- The scope statement, requirements documentation, team charter, basis of estimates and
  team performance assessments resolve against the store, and the wizard can produce each
  one. Collect Requirements, Estimate Activity Durations, Estimate Costs, Estimate
  Activity Resources and Develop Team become assessable — 13 of the 49 processes now have
  no tracked output, down from 18 — and Define Scope and Plan Resource Management each
  owe a written body they did not before.
- The task register answers for two more PMBOK outputs, derived rather than stored: a task IS
  the scheduled activity (healthy only when every one carries an estimate — an unsized activity
  cannot be sequenced or weighed against capacity) and `Task.assignee_id` IS the team assignment
  (healthy only when no task is unowned). Sequence Activities and Acquire Resources become
  assessable — 2 of the 49 processes now have no tracked output, down from 4 — and the read
  batches through the same prefetch scope every other resolver uses, joining `Workstream` for
  the project id a task does not carry.
- Every artifact kind now carries its recorded disposition: the 65 vocabulary kinds
  without a resolver each state, in `driftless.pmbok.mapping.UNTRACKED_DISPOSITIONS`,
  why they stay untracked and what the store consults instead — and a partition test
  makes a silently undispositioned kind unrepresentable.
- The work-performance chain resolves from the store, derived rather than stored: the reports
  a project files are the status snapshot series under the catalog's own name, and work
  performance information is an approved plan plus dated actuals, healthy while the newest
  actual is inside the reporting cadence. Nine monitoring processes become assessable — 4 of
  the 49 now have no tracked output, down from 13 — and neither kind is producible, having
  nothing of its own to write.

### Changed
- **A project now costs the dashboard nothing.** The last three per-project reads
  batched too — the resource evaluator's tasks (grouped through their workstream,
  people loaded on the same pass) and the communications evaluator's status lookup
  (the mapping layer's cache fills lazily per model, so opening it for one read
  costs one query) — and the threat board's own assessment pass now runs inside the
  same scope. `/` and `/threats` are flat in the project count: 9 and 18 statements
  per extra project became 0. On the release-gate store `/` fell from 162 statements
  to 114 and `/threats` from 139 to 47 — every page byte for byte as before.

- **The dashboard stopped paying a query bill per project.** Each of the nine
  evaluators read its rows one project at a time, so `/` charged ~47 statements per
  extra project — a 50-project store rendering in ~2,300 round trips to the database.
  Those reads now batch across every project in one query each, as does the threat
  sign-off ledger: `/` fell from 370 statements to 162 on the release-gate store, and
  the marginal cost of a project from ~47 to 9. Same rows, same figures — every page
  renders byte for byte as before.

- Eight helpers three modules already shared lost their leading underscore, which was
  simply untrue: the API's `fetch` / `insert` / `stamped_percent` (imported by the web
  pages and the wizard CLI) and the pages layer's `STATE_RANK` / `pct` /
  `area_completeness` / `evm_curve` / `threat_cards` (imported by the business map and
  the project hub). A `_`-name reads as "mine, safe to change", so the next refactor of
  `api/app.py` would have silently broken the web layer. Names nothing else imports stay
  private, and a source-walking test now fails any future cross-module import of a
  private name. Rename only — every surface renders byte for byte as before.
- The commercial-volume statement-slope guard now asserts a project's marginal
  cost is **exactly zero** statements, not `<= 1`. Statement counts are integers,
  so the slope has no wobble to tolerate, and the old ceiling waved through the
  exact N+1 the file exists to catch — dropping
  `selectinload(Project.milestones)` from `adapters.eager_project()` put `/` at
  slope 1.0 and the suite stayed green. Proven by mutation both ways: the
  tightened guard fails against that mutation and is green without it.
- The coverage floor is a floor again: `--cov-fail-under` moves from 80 to **99.2**
  against a measured 99.64% (4935 statements, 18 missed). At 80 roughly 950
  statements could go dark with CI green — deleting every test touching
  `api/app.py`, `web/pages.py` and `api/secure.py` still measured 82.1% and passed.
- The built distribution now carries `driftless/py.typed` (declared in
  `[tool.setuptools.package-data]`), so PEP 561 lets a downstream importer see the
  annotations that `mypy strict` already enforces instead of discarding them.
- `psycopg[binary]` is a runtime dependency rather than a `[dev]` extra:
  `deploy/entrypoint.sh` builds a `postgresql+psycopg://` URL, so `pip install .`
  had been producing a container that could not open its own store.
- `tests/test_packaging_metadata.py` holds all three to the repo: the floor is
  compared with the measurement, the marker must exist *and* be packaged, and every
  `dialect+driver://` URL the shipped entrypoint builds must name a declared runtime
  dependency — so a second backend cannot repeat the psycopg omission.
- **The page-performance ceilings can fail again, and a baseline that drifts now says so.**
  Every whole-store ceiling was sized at "measured plus one statement per project the call
  walks" — at six projects exactly what the cheapest defect they name costs, so a relapse
  adding one statement per project landed *on* the `<=` boundary and passed. Each is
  re-derived at measured + 1 or 2: `portfolio_nodes` 26, `top_threats` 21, `attention_feed`
  39, `threat_cards` 56, the home render 132, the report documents 19/9/19, the same at
  commercial volume (132/19/56) and on the `driftless report all` path (100/134/19).
  Recorded numbers kept drifting while living only in a comment — the `report all` path's
  three were stale by 2, 2 and 3, and the project hub's had reached its own ceiling exactly,
  so the next honest read would have failed as a mystery breach rather than as the drift it
  was. Every baseline now lives in a `MEASURED` dict its ceiling test re-measures on every
  run, so drift fails naming both numbers, and a further test fails when a recorded number
  is never re-measured — it caught the `report all` counts falling 107 -> 98 and 151 -> 132
  when the sign-off prefetch stopped being scoped per project. The ceilings are priced
  against the regressions they name, not argued: deleting the eager options costs 66
  statements against the 56 ceiling, 60 against the scoped 59, 112 against `/threats`'s 56
  at commercial volume and 108/156 against the report path's 100/134; deleting the hub's
  prefetch scope costs 476 against 87, and re-opening the map's nested scope 66 against 19.
- **CI stops spending runner time on questions it already knows the answer to.** The suite
  runs under `pytest -n auto` (6 workers on the shared runner host) instead of serially —
  the `PYTEST_XDIST_AUTO_NUM_WORKERS` cap that was already in the workflow had been dead,
  because `pytest-xdist` was not a dev dependency and the step invoked a bare `pytest`. The
  test job no longer waits on the lint job, which shares no artifact with it. `pip-audit`
  moved to its own workflow with a dependency-file path filter, so it starts only when an
  input it audits moved rather than starting on every pull request to compute its own skip.
  Scheduled and manually dispatched runs now get distinct concurrency groups, so a nightly
  and a hand-triggered run on `master` stop cancelling each other. Every job has a
  `timeout-minutes`, replacing GitHub's six-hour default. Dependabot arrives grouped and
  weekly (`.github/dependabot.yml`), one pull request per ecosystem, never automerged.
- The wizard now works out a step's `producible` outputs from the producer registry
  (`wizard.cli`) rather than from "every tracked kind", and `next_step` skips a process it
  can produce nothing for the way it already skips an unassessable one. The two sets are
  identical today, so no step, no walk and no completeness figure moves — what changes is
  what happens next: a *derived* artifact kind (one resolved from stored inputs, with
  nothing of its own to write) can now gain a resolver without a producer, and simply never
  appears as a button. Before, it would have been offered and then refused with `422`, which
  is why every wave so far had to ship a producer per resolver just to keep that quiet.

### Fixed
- **The audit-actor test no longer breaks when FastAPI moves.** It imported
  `get_flat_dependant` from `fastapi.dependencies.utils` — a private module — to walk
  each route's dependency tree. That import stopped resolving in FastAPI 0.140, and
  because `pyproject` declares `fastapi>=0.110` with no upper bound, any fresh resolve
  picked up the break: the module failed to import and took the whole test session with
  it. The pinned lockfile added in this release is what surfaced it, having resolved
  0.140.7 where the development environment still had 0.139.2. The tree walk is four
  lines, so the test now owns it rather than pinning the framework backwards to keep a
  private helper reachable. Verified against both versions.
- An earned-value snapshot no longer invents a progress measurement for a date it
  cannot answer. `Task.percent_complete` is an undated *current* reading, and the EVM
  adapter used to hand it to calc stamped with the as-of being asked about — so
  `?as_of=2025-06-01` printed EV 500 and "50% complete" seven months before the
  project started, and an as-of in a month the plan had not begun printed an SPI in
  the tens. An as-of before the plan's earliest planned start now returns the same
  no-plan empty state the product already renders — BAC/PV/EV 0, spend still real,
  ratios `n/a` — instead of a number. PV and AC are genuinely time-phased and answer
  every as-of unchanged, so the planned-vs-actual S-curves and burn sparklines are
  untouched.
- **A backdated status snapshot records the percent that was true on its own date.**
  `stamped_percent` read earned value through `gather.project_evm`, which holds no
  session and so reads `Task.percent_complete` — one undated *current* number that
  answers every as-of. A snapshot filed for `taken_on=2026-02-15` therefore stamped
  TODAY's completion, and because the status series is append-only (no PATCH or
  DELETE exists for it), the wrong figure was permanent and the trend chart plotted
  it. The stamp now reads through `adapters.project_snapshot`, whose ChangeLog
  replay dates each progress reading — reached from `POST /status-snapshots`, the
  weekly status form and the wizard alike, since all three share the one stamp.
- **A constraint conflict answers in the surface's own language.** Refiling the
  weekly status for an already-snapshotted date hits
  `uq_status_snapshot_project_date` through the form (which has no pre-check — an
  everyday PM action), and the `IntegrityError` handler answered raw JSON with no
  navigation; the wizard hit the same trap on `uq_narrative_project_kind`. The
  handler now keys on the surface the request matched, exactly as every refusal in
  `driftless.web.errors` does: a page surface renders the designed HTML 409 shell,
  and every API error body stays byte-for-byte what it was.
- **The backup's restore-verify counts rows, and the drill is actually run.** It compared
  `information_schema.tables` between the source and the restored copy, so a `--schema-only`
  dump — every table, not one row — matched and printed `restore-verify OK`. It now compares
  the row count of every table, refuses a set whose totals are zero, and records
  `N tables / M rows` in the manifest. Nothing had ever executed the script: a new drill
  (`tests/test_backup_script_drill.py`) runs it against stub `pg_dump`/`pg_restore`/`psql`
  on PATH, so a full dump verifies and a schema-only one fails, offline and without Postgres.
- **The backup set is no longer world-readable, and the timestamp cannot choose where it
  lands.** The dump is the whole database in the clear and the manifest names where the age key
  is escrowed; under a scheduler's default umask both were `0644`. The script now sets
  `umask 077` before it writes anything, as `deploy/entrypoint.sh` does. The timestamp argument
  is sanitised for the three file names it builds — it already was for the verify database name
  — so a caller's `date` format string can no longer write outside `$DRIFTLESS_BACKUP_DIR`.
- A failed import is now recoverable instead of silently half-done. `bin/driftless-import.py`
  creates one row per POST with no transaction spanning them, so a failure on row 3 of 5 left
  rows 1-2 in the store and re-running the file duplicated them — exactly the asymmetry the
  importer refuses an `id` column over. A mid-file failure now raises `PartialImport` naming
  what landed, the CLI prints that record (`landed: {"tasks": 2}`) and `--skip 2` re-runs only
  the rest, so recovering from a half-import cannot double a row.
- A JSON task now carries every field a `--csv tasks` row does. `percent_complete`, `status`
  and `assignee_id` were read from the file and dropped on the way to the API — the same
  asymmetry the CSV path refuses out loud — because the JSON walk hand-wrote a subset of
  columns. Both paths read one column set now, and a task field that is not an importable
  column, or a `workstream_id` the file's own nesting already names, is refused naming the
  task rather than dropped.
- A missing file, a file that is not JSON, or an unknown CSV column now exits 2 with one line
  on stderr, matching the `driftless` subcommands, instead of a raw traceback at rc 1.
- The two operator-run tools in `bin/` no longer destroy files they did not make.
  `driftless-snapshot-pages.py` clears `*.html` out of `--out`, so it now writes only
  into a directory it created (marked `.driftless-page-snapshots`) or an empty one, and
  refuses anything else instead of deleting a hand-written page under `--out docs`.
  `assemble-changelog.py` parses `--date` as a real date at the command line, before a
  release stamps the log and unlinks every fragment, and reports a changelog it cannot
  fold into rather than raising over it. The repo's no-secrets-in-a-document guard now
  reads tracked shell scripts too — `deploy/entrypoint.sh` and `bin/*.sh` were unscanned.
- Audit-trail guard: a multi-column update must log every moved column with its
  old/new values, and a same-value rewrite mixed into the same flush stays out.
  The base changelog tests only ever moved one column, so a regression that
  thinned `detail["changed"]` would have passed the whole suite (F-T21).
- **The migration chain is proved on Postgres, not only on SQLite.** SQLite takes every
  schema change through Alembic's copy-and-swap batch mode, which is the one path a
  deployment never runs — so the parity proof was green on a topology production does not
  have. `tests/test_migrations.py` is now parametrised over both dialects: point
  `DRIFTLESS_TEST_DB_URL` at a server and the whole chain is built, compared against the
  models (CHECK constraints included) and reversed there too. A new **Migrations
  (Postgres 16)** CI job does exactly that against a health-checked `postgres:16` service
  container. Unset — a developer's plain `pytest` — the Postgres half skips rather than
  fails, so no local server is needed. A guard test asserts the dialect proved is the
  dialect asked for, because the failure that matters is a Postgres run that quietly
  proves SQLite a second time.
- **CI runs least-privileged, on pinned actions.** Both workflows declare a top-level
  `permissions: contents: read`, so every job inherits a read-only token and only the
  alert jobs re-grant themselves `issues: write`. `actions/checkout` and
  `actions/setup-python` are pinned to full commit SHAs with the release named beside
  each: a floating `@v7` is a mutable pointer to somebody else's code, running on a
  runner that holds this checkout and the workflow token.
- **A database the CLI cannot read is now a sentence, not a stack trace.** `driftless
  assess`, `report all`, `user list`, `token list` and `wizard next` pointed at a store
  with no driftless tables printed a 20-line SQLAlchemy traceback; they now print
  `no driftless tables in the database (…) — run \`alembic upgrade head\`` and exit 2.
  A SQLite URL naming a file that does not exist is refused *before* anything connects,
  so a typo no longer leaves a 0-byte database file behind.
- **Two projects of the same name are refused instead of guessed.** `Project.name` has no
  unique constraint, so `driftless assess "Website Rebuild"` silently acted on the lower
  id when two existed. Every CLI that resolves a project by name now names both ids and
  exits 2; pass the id to choose.
- **A failed request now appears in the request log.** A route that raised returned 500
  and produced no `driftless.request` line at all — the one class of request an operator
  goes to the log for was the one class missing. The line is emitted whether the route
  returned or raised, carrying the status actually served.
- The real (Postgres) engine pool now covers Starlette's 40-token sync threadpool (was 5+10, so the
  16th concurrent request waited 30s and then 500ed), pre-pings so the first request after a database
  restart reconnects, and recycles half-hourly.
- Every foreign-key column not already leading a unique constraint is indexed (23 columns, migration
  `c8f3a1d47e29`), so per-parent reads stop scanning the whole child table.
- `app_user.session_epoch` carries its `0` server default on the model as well as in the migration,
  so both store topologies accept the same omitted-column insert.
- *Rolling back in place* (OPERATIONS.md) dumps the current state before `pg_restore --clean` drops it.
- `driftless demo seed` refuses a store that already holds businesses unless
  `--force` is passed — a second seed used to duplicate the demo, and the API's
  delete-integrity guards (approved baselines, parents with children) made the
  copies unremovable (F-D1). It also refuses an empty `--token` before touching
  the network, and reports unreachable or refusing APIs as a one-line message
  with a non-zero exit instead of a raw traceback (F-X15).
- The admin guide's bare-host runbook clones `Back-Road-Creative/driftless.git`
  (it said `workspaces.git` and a directory this repo does not ship), and its
  seed one-liner carries the `--force` its own walkthrough now needs (F-X1).
- The admin-guide doc test holds `manual` blocks to an exact allowlist with a
  substantive `why=`, so an excused command can no longer drift unnoticed —
  which is how F-X1's wrong clone line slipped through (F-T20).
- The public listener now sets the headers a browser needs to be told — a year-long
  `Strict-Transport-Security`, `nosniff`, `X-Frame-Options: DENY` and a
  `Content-Security-Policy` that pins the origin, none of which Caddy added itself
  to pages that render stored text. The policy is pinned to the templates, so a page
  that would violate it fails the suite rather than only a browser.
- Every container declares a memory ceiling (the app a CPU one too), so a login storm
  hashing at ~16 MiB per password is that container's bad minute, not the host's.
- A scheduled uptime check probes the deployed `/health` from outside the host and
  opens (or appends to) an alert issue when it stops answering. Docker's `unhealthy`
  restarts nothing and tells nobody, and the existing alarm only watched CI.
- `.sops.yaml` says what it is: replacing the placeholder age recipient is required
  before the first deployment, not a working default, and no encrypted secrets file is
  committed here — a test fails if one exists while the placeholder stands. It and
  `.pip-audit-ignore` also drop their pre-rename `pmhub` naming, and the audit list no
  longer claims this project declares no runtime dependencies.
- `driftless user add` now refuses a password shorter than 12 characters, before it is
  hashed and before the row is written. `deploy/entrypoint.sh` has always refused a
  machine secret under 24, while the one credential a human types could be a single
  character — the weakest thing the service would accept, on the account most likely to
  be an admin.
- README corrections. The demo store is 4 projects with baselines on the statused
  **three**, not 3 with two statused (`OPERATIONS.md` already read correctly, so the two
  documents disagreed); *Development* now says out loud that the `python3 -m venv .venv`
  recipe is for a fresh clone while the workspace box uses the venv provisioned outside
  the tree, which is what `CLAUDE.md` meant by "there is no `.venv` — don't look"; the
  weekly-status note no longer claims per-task progress history is not retained, since
  `progress_history` replays it from the ChangeLog; and the department drill, the demo
  seed's `--force`, the wizard's re-baseline refusal, the per-client login cap and the
  error shell's 422 are described as they now behave. README and `LIFECYCLE.md` no
  longer point at a pre-extraction build plan that stayed behind in the monorepo this
  repo was extracted from.
- The dated ChangeLog replay is the one source of truth for earned value. The
  assessment path already replayed task progress out of the log, but `snapshot_from`
  called without a progress series — every report and dashboard surface behind
  `gather.project_evm` — silently fell back to stamping today's percentage at
  `date.min`, so one store at one backdated as-of printed EV 800 / CPI 2.00 in
  `cost-evm.md` while the assessment said CPI 0.50 and rated the project red. An
  omitted series now resolves the replay through the project's own session, healing
  every caller at once; only a project attached to no session (no store, so no log
  to speak for it) keeps the undated current reading — the same answer the replay
  gives a task with no logged history. Three replay hardenings ride along: a logged
  delete truncates its row's replayed readings, so a SQLite rowid reused after a
  delete no longer hands a brand-new 0% task a dead task's earned value; the
  per-session replay memo is invalidated on the session's own flushes and rollbacks,
  so a session that writes progress and reads again is never served the pre-write
  replay; and a batched read for a project outside the open prefetch scope raises
  instead of fail-open answering "no rows", which read as green everywhere.
- The dashboard's swept charts no longer re-adapt every project's plan at every sample
  date: the baseline-to-value-object step (plan selection, line sort, list builds) is
  hoisted out of the per-sample loops behind the business S-curve and the burn
  sparklines, and runs once per project per request instead of once per sample — the
  request cost grew 12x as projects grew from 5 to 300 tasks. The rendered series are
  byte-identical, pinned against the canonical adapter at every date regime.
- A plan window shorter than the chart's sample count no longer repeats dates: 12
  samples over a 3-day span plotted 12 points on 4 distinct days, and the S-curve's
  accessible text twin repeated a row per duplicate. The shared sampling window now
  collapses duplicates — a short window sweeps one sample per calendar day, and the
  degenerate not-yet-started window is a single as-of sample rather than twelve copies
  of it.
- **The image installs the version set the audit scanned.** `requirements.lock` said it
  kept CI, `pip-audit` and the Docker image on one resolution, and two of the three were
  true: the `Dockerfile` passed no constraint and never copied the lock into the build, so
  with every dependency declared `>=` a green audit described whatever pip resolved on the
  runner that morning, not the artefact an operator runs. The image now installs under
  `--constraint requirements.lock`, and `tests/test_image_dependency_parity.py` fails if
  the constraint, the `COPY` that makes it resolvable, or a pin it relies on goes away.
- **No test tooling in the production image.** The install line asked for the `[dev]` extra,
  which put `pytest`, `pytest-xdist`, `coverage` and `httpx` in the shipped container as
  pure CVE surface with nothing to run them. It installs the runtime set instead, naming
  `psycopg[binary]` explicitly — the one runtime dependency the extra had been carrying.
- **The base image is pinned by digest.** `python:3.12-slim` moves on every upstream
  rebuild, so one commit built twice was two different images and the interpreter and
  system libraries the audit reasoned about were not the ones that shipped.
- **Login throttling survives the reverse proxy.** Behind `deploy/proxy.compose.yml`'s
  Caddy, uvicorn trusts `X-Forwarded-For` from `127.0.0.1` alone by default — which the
  proxy container never is — so every request arrived as one shared compose address and a
  per-address throttle would lock out every user at once. The `CMD` now passes
  `--proxy-headers --forwarded-allow-ips=172.16.0.0/12`: the private range compose
  allocates bridge networks from, never `*`, which would let a client forge an address.
- Sign-in throttling provably keys the client uvicorn *resolved* — the forwarded
  caller once the deploy passes `--proxy-headers`, never a raw header read — so one
  peer tripping lockout on a known username locks nobody else out, and a second
  per-client cap (30 failures per 15-minute window across all usernames) refuses a
  username-rotating flood *before* the scrypt verify instead of paying ~16.7 MiB
  and tens of milliseconds per free guess.
- A refused sign-in (400/401/429/503) re-renders the form with the typed username
  kept — escaped data, never markup — and focuses the field, instead of making the
  user retype it.
- The failure counter is mutation-proven to restart once its window rolls over, and
  the attempt store's expired-window eviction is now covered.
- Artifact resolvers now answer for the as-of date asked instead of "now". 14 of
  16 resolvers ignored `as_of`, so a baseline approved in 2026 read as present in
  2025 and the process map, per-area rings, business completeness, the
  low-completeness signal and `driftless report all` were byte-identical at every
  date. Every resolver over a dated row now filters by it — `Baseline.approved_at`,
  `ChangeRequest.raised_on`, `Issue.raised_on`, `NarrativeArtifact.updated_on` —
  while an undated row (a wizard-filed narrative) still counts.
- The batched-read cache refuses a project outside its open prefetch scope with a
  `LookupError` instead of answering "no rows" — an out-of-scope project used to
  read as "nothing to assess" and grade green.
- The wizard's apply form refuses to re-baseline a project that already holds an
  approved baseline (409, nothing written). One click — or one direct POST — naming
  `scope_baseline` or `schedule_baseline` used to file version N+1 as approved on the
  spot, irreversibly rewriting the BAC every EVM figure is measured against.
  Re-baselining is a change-control decision; first baselines still go through.
- A refused wizard apply re-renders the form with the typed prose still inside its
  textarea and names the refusal above it. A 422 used to answer with an error shell
  containing no form at all, destroying up to 100,000 typed characters with no
  history entry to go Back into.
- The weekly-status form validates through `StatusSnapshotIn` and files through the
  JSON route's own create, so a RAG outside the vocabulary or an oversize note
  answers 422 at the schema boundary — the posted values used to reach the ORM
  unvalidated, bouncing off a CHECK constraint as a 409 or slipping past a VARCHAR
  length SQLite never enforces.
- `earned_value` now builds a task-id → latest-fraction index in one pass over the
  progress readings instead of rescanning every reading once per baseline task. The
  per-task scan made EV quadratic — 0.34 ms at 100 tasks to 62.79 ms at 1,600 (185×) —
  and the dashboard computes EV for every project on every snapshot, so it was 23% of
  a 1.73 s five-project page. Per-task answers are byte-identical, ties included.
- `driftless report all` stops re-reading the store per document. The CLI's project
  query now carries the same `adapters.eager_project()` options every web route
  already applies — no more lazy `line.task` load per baseline line — and the whole
  document loop runs inside one `adapters.prefetched` + `state.prefetched` pair, so
  per-project evaluator and process-state reads batch across the store (measured on
  the guard's seed: 316 → 149 statements at four projects, bytes unchanged). The
  Process Map document now rides an already-open prefetch scope instead of re-scanning
  the whole sign-off ledger once per project, and both Jinja environments (web pages
  and report documents) set `auto_reload=False` — packaged templates change only with
  a deploy, so a warm render no longer pays an `os.stat` per template.
  `tests/test_perf_report_all.py` pins the ceilings and the byte-equality.
- The per-project document bodies stop re-reading the store. The Assessment Report
  computes its assessments once per render and derives both the knowledge-area rows
  and the top-threat feed (the nine evaluators used to run twice), the feed still
  filtered and ranked exactly as `assess.live_threats` answers. Charter, Schedule and
  Forecast batch milestone reads through `adapters.project_rows` — one IN-query per
  open scope, not one SELECT per (document, project) — bytes unchanged. The Department
  Report's blended labour rate is now capacity-weighted: the old head-average priced a
  5-hour specialist as a 40-hour supply (125.00 where the supplied hour costs 66.67).
- Rollup verdicts and scores stop lying at the edges (audit F-C5–F-C8): a
  childless branch rolls up `unknown`, so an empty portfolio or program no
  longer renders healthy on the heatmap; `on_track_share` excludes `unknown`
  projects from its denominator and returns `None` (rendered "n/a") when
  nothing is assessable, instead of printing "0% on track" for a store with no
  verdict at all; the schedule score expresses milestone slip as the slipped
  share of the milestone list — the same unit as 1 − SPI — so near-total
  schedule collapse no longer ranks below one slipped milestone; and the
  exposure engine carries the absolute contingency reserve through instead of
  a rate whose float round-trip read an exactly-covered reserve as a red
  breach at score 0.0 that a sign-off would suppress forever.
- **A CSV export can no longer carry a formula into a spreadsheet.** Cells were written
  verbatim, so a project named `=cmd|' /C calc'!A0` — or any name, description or vendor
  beginning `=`, `+`, `-`, `@`, a tab or a CR — ran as a formula the moment someone opened
  `?format=csv` from any list route or from search. Such a cell is now marked literal with
  a leading `'`; a value that parses as a number (`-42.5`) is untouched and still totals.
  A name that did start with one of those characters comes back through the CSV importer
  with the `'` still on it — drop it if you re-import that row.
- **A carriage return in a name can no longer break the calendar feed.** `/calendar.ics`
  escaped `\`, `;`, `,` and newline but not CR, so a CR inside a milestone or sprint name
  ended its `SUMMARY` line early and let the rest of the name become a property of its own
  in every subscriber's calendar. CR and CRLF now fold into the one line break RFC 5545
  can escape.
- The sign-off ledger is now bounded by the as-of being asked about: a decision
  recorded against a later assessment date no longer rewrites an earlier page, feed
  or trend point (a threat accepted this week used to vanish from
  `/threats?as_of=2020-01-01`; a row with no recorded assessment date still applies
  at every as-of). The process prefetch scope loads only the scope's projects'
  ledger rows, the threat scope is public (`assess.engine.threat_sign_offs`), and
  `completeness`'s nothing-to-assess-is-`None` contract is pinned mutation-proven.
- **The plan empty states name the order that actually works.** The schedule and
  weekly-status charts said "baseline the plan and approve it (`POST /baselines`,
  `POST /baseline-lines`)" — followed literally, that order hits the API's own 409,
  since an approved baseline refuses new lines by design. Each now walks draft →
  lines → approve and names `PATCH /baselines/<id>` for the approval, which no
  empty state did.
- **A page's 422 stops claiming an error was logged.** `web/errors.py` had no 422
  wording, so a refused form input fell back to "Something went wrong … the error
  has been logged" — nothing failed and nothing was logged. The page now says the
  input was refused and how to fix it, and still renders none of the detail.
- **The data-swap script does what its comment claimed.** No template set
  `data-target`, so every background submit rewrote the whole document with
  `document.write()`: focus destroyed, nothing announced, no history entry — and an
  offline fetch rejection had no `.catch`, leaving the page byte-identical with no
  word to anyone. The threat board's sign-off forms and the weekly-status form now
  name their fragment; the script lifts the fresh fragment out of the server's full
  response, moves focus to it, announces the outcome in a polite live region, and
  surfaces a failed fetch in that same region.
- **Threat trend badges read without hover or colour.** ▲/▼ were bare glyphs and
  "vs last week" lived only in `title=` — hover-only: no keyboard, no touch, no
  print. The glyphs are `aria-hidden` with their words in an `sr-only` span (the
  treatment the unchanged badge already had), and the threat board's pager landmark
  is named.
- **The treemap's verdict is no longer colour alone.** Each rectangle's RAG lived
  solely in its `--rag-*` fill; the `<title>` named the portfolio and budget but
  never the health, so greyscale, print and the accessibility tree all read "a
  portfolio worth N". The title now prints the RAG as a word (the rollup table's
  own vocabulary, "no data" for unknown), each SVG link takes `tabindex="0"`, and
  the home test that accepted base.html's own `<title>driftless</title>` as proof
  of rectangles now demands the real ones.
- **The home S-curve's two series survive greyscale.** Both polylines were
  `.s-line` with `stroke: currentColor` and no dash. The actual line now dashes —
  the EVM chart's own idiom — and the legend says "Planned (solid)" / "Actual
  (dashed)" in words.
- **The dashboard's plan empty states name the order that actually works.** Both
  chart slots said "baseline each project's plan and approve it (`POST /baselines`,
  `POST /baseline-lines`)" — followed literally, that order hits the API's own 409,
  since an approved baseline refuses new lines by design. Each now walks draft →
  lines → approve and names `PATCH /baselines/<id>`.
- **Rail trend badges read without hover or colour.** ▲/▼ were bare glyphs and
  "vs last week" lived only in `title=`. The glyphs are `aria-hidden` with their
  words in an `sr-only` span, the treatment the unchanged badge already had. The
  business jump nav is a named landmark, and a department page's two empty states
  carry distinct ids instead of rendering `id="empty-state"` twice.
- **The project hub and the department drill read their own scope.** Both are one-entity
  pages, but the hub's cost read was the store-wide `select(CostEntry)` grouped after the
  fact — every project's spend fetched to render one — and the department drill rebuilt
  the whole org's `department_rows` to find its own row: 53 statements at 8 departments
  where the scoped page costs 10, growing with every department the page never renders.
  The hub now reads `adapters.project_costs` scoped to its project; the drill computes its
  one row from the same engines the Department Report renders from (`gather.project_evm`,
  `adapters.eager_project`, costs batched across its own projects), with the agreement
  test still pinning screen to document. The guards now hold: the hub test fails on any
  other project's cost row in the session, and the drill's statement ceiling is re-derived
  on a store big enough (8 departments) that the org-wide walk can never again hide under
  it the way 23 statements hid under a ceiling of 24 at 3 departments.
- Three guard-holes in the same pages' tests are closed: the hub's SPI and EAC slots are
  pinned to their own computed values, pairwise-distinct by seed, so CPI printed into the
  SPI slot no longer passes; the department drill's People table is asserted as the
  rendered `<tr class="person">` row, which a table of zeros used to satisfy via the
  page header's own "40"; and both fixtures seed a SECOND project/department carrying its
  own RAID rows, milestones, people and projects, so a dropped `project_id ==` or
  department-scope clause fails loudly instead of passing against a store with nothing
  to bleed.
- The wizard refuses to produce a scope/schedule baseline while an approved one
  exists: the newest approved version IS the plan of record, so a wizard-seeded
  approved vN+1 silently replaced the plan every EVM figure reads and could not
  be repaired through the API. Re-baselining stays with change control; a draft
  does not refuse.
- A wizard baseline lands as one transaction — workstream, task, baseline and
  line on a single commit, ChangeLog rows included; a mid-write failure no
  longer leaves a committed partial approved baseline.
- **A list endpoint answers a bounded window, not the whole table.** Every generic list
  route loaded all of an entity's rows into memory, and `?format=csv` built the entire
  export as one string — so one ordinary request against a commercial store was an
  unbounded allocation. A list now answers at most 500 rows by primary key and takes
  `?limit`/`?offset`; `?limit` is clamped to 2000 rather than refused. Both
  encodings carry `X-Total-Count`, `X-Limit` and `X-Offset`, so a truncated list cannot
  be mistaken for a complete one. Single-row `/{id}` reads are unchanged.
- **Importing a `driftless.web` submodule first no longer fails.** `driftless.api.app`
  mounted the web routers at its own import and every web submodule imports helpers from
  it, so `import driftless.web.pages` in a fresh process raised a circular `ImportError`
  (eleven of the fourteen did), the suite staying green only because isort sorts
  `driftless.api` above `driftless.web`. The mount now stands down when it is reached
  from a web module still executing its own body, and the lifespan completes it before
  the first request. Every ordinary order still mounts at import, so the route table a
  bare import exposes is unchanged.
- The numbers in the prose are read back from the code that decides them.
  `tests/test_docs_numbers_are_measured.py` builds each stated figure from the live
  constant and fails naming the sentence to fix, so a moved constant can no longer
  leave a plausible wrong number in front of a reader. It caught four: README's
  performance floor claimed per-page statement counts several times the ceilings CI
  enforces (it now states the ceilings themselves, which are decisions rather than
  readings, and the measured counts are not restated at all); `CLAUDE.md` and the
  README each gave a coverage floor the setting had left behind, one of them at a line
  reference that had moved, and both now cite `--cov-fail-under` where it is set
  instead of copying it; `requirements.lock`'s header said pyproject declares neither
  uvicorn nor psycopg, when `[project.dependencies]` declares psycopg; and the user
  guide's sign-in throttle,
  capacity horizon and search cap are now checked against `driftless/web/login.py`,
  `driftless/web/heatmap.py` and `driftless/api/search.py`. The page-snapshot bundle's
  file count is deleted rather than corrected — no test can keep it honest, and every
  page mounted moves it. A list endpoint's query vocabulary is read off the router and
  looked for in the guides' prose, which caught `?limit`/`?offset` shipping
  undocumented — the user guide now gives the window, its default and its ceiling.
- `driftless report all` stops looking a threat sign-off up once per threat. The
  document loop already ran inside `adapters.prefetched` + `state.prefetched`, but
  `state.prefetched` caches PROCESS sign-offs only — so the Assessment Report's
  per-threat `assess.is_suppressed` calls each fell through to a
  `state.latest_sign_off` query, a cost that grew with the store (measured on the
  guard's seed: 10 lookups at 2 projects, 20 at 4, 40 at 8). The run now also opens
  `engine.threat_sign_offs`, the public scope that reads the THREAT ledger once,
  taking the render to 96 / 130 / 198 statements from 105 / 149 / 237. Pure cost:
  every rendered document is byte-identical, sign-offs included, and
  `tests/test_perf_report_signoff_scope.py` pins both — the per-threat lookups at
  zero and one ledger pass however many projects, plus byte equality against
  scope-free single renders with a real suppressing sign-off in the store.
- **`driftless pmbok show` sends its refusal to stderr, like every other command.** An
  unknown clause id printed `error: no process with id …` on *stdout*, so a caller
  redirecting the catalog to a file captured the error message as data instead of seeing
  it on the terminal. It now goes to stderr, leaving stdout empty on a refusal; the exit
  code was already 2 and is unchanged.
- A first `docker compose up` in a fresh checkout no longer creates a *directory* where
  the encrypted secrets file belongs. The app mounted `deploy/secrets.enc.env`, which no
  checkout carries — it is written on the deployment host — and Docker answers a missing
  bind source by creating an empty directory at it, after which the documented `cp` of
  the plaintext template lands inside that directory instead of failing. The mount is now
  `${DRIFTLESS_SECRETS_ENC:?…}`, so Compose refuses up front, names the variable and
  starts nothing. Export it beside `DRIFTLESS_AGE_KEY` before `docker compose up`; it is
  the same variable `bin/driftless-backup.sh` already reads, so one export serves both.
- `.gitignore` no longer tells readers an encrypted secrets file is committed here, which
  `git ls-files deploy/` refuted, nor that OPERATIONS.md has operators generate the age
  key in the checkout, when it puts it under `~/.config/driftless`. Both claims are now
  checked against the tracked file list rather than a pinned string, so a comment about a
  file this repository does not have fails the suite.
- OPERATIONS.md carries the export the run now needs, and no longer says the encrypted
  overlay is committed — `git ls-files deploy/` lists only the plaintext example, so a
  reader was told the file would be there and then had to make it anyway. The same claim
  is gone from `tests/test_docs_no_secrets_in_repo.py`'s docstring, which cited being
  committed as the reason the file needs no exemption; the actual reason is that no ignore
  file names it. A guard now reads each `${VAR:?}` out of the compose files and fails if
  this page does not hand the operator that export, so a new required variable cannot ship
  with Compose's error message as its only documentation.
- A **process** sign-off now has to carry the `as_of` it was judged at, refused with a
  422 naming the field when it does not. `as_of` is what bounds the ledger — a decision
  recorded against a later assessment date cannot rewrite an earlier page — and a row
  with no recorded date has nothing to compare, so it applied at *every* as-of. For a
  process that decision is the whole state of the cell, so one dateless JSON post
  silently re-scored every process map back to the store's first day, escaping the bound
  the previous release added. The browser form always stamped the date; the requirement
  now sits on `SignOffIn`, the one write path both routes go through. Threat sign-offs
  keep the field optional on purpose: theirs suppress only while the server-stamped
  `signal` holds, and a sign-off with no as-of to score at records no signal, so it
  suppresses nothing.
- **A sprint's length counts both of its endpoints, so the velocity band no longer
  finishes a day early per sprint.** The Forecast Report measured each completed sprint
  as `(end_date - start_date).days`, an exclusive difference: a 01-01 to 01-14 sprint
  reported thirteen days. Every other length in the product is inclusive — `calc.evm`
  accrues a baseline task over `(finish - start).days + 1`, and `calc.forecast.Sprint`
  itself defaults to a fourteen-day fortnight — so the band divided the remaining points
  by the right velocity and then multiplied by a window one day short, pulling best,
  likely and worst each one day earlier for every sprint still needed. Three 15-day
  sprints with 13 points left now finish 2026-04-15 / 2026-04-15 / 2026-04-30 rather than
  a day and two days sooner. The test that checked the band had copied the same
  arithmetic, so it agreed with the bug; it now states the seeded sprint length as a
  constant and pins the three dates literally, which is what an implementation change
  cannot carry along with it. A same-day legacy row is still skipped — one day carries no
  velocity information — and no stored figure changes.
- **The `sops` binary is verified before the image trusts it.** The build fetched the
  release binary over the network and `chmod`ed it unread, and `deploy/entrypoint.sh` runs
  exactly that binary to decrypt `DRIFTLESS_SESSION_SECRET`, `DRIFTLESS_API_TOKEN` and
  `POSTGRES_PASSWORD` at start — so a swapped release asset silently replaced the program
  holding every deployment secret. The build now pins the sha256 the release's own
  `sops-v<version>.checksums.txt` publishes and `sha256sum -c`s it *before* `chmod`: a
  mismatch fails the build instead of shipping, and a binary is never made executable
  ahead of being checked. `tests/test_image_dependency_parity.py` fails if the check goes
  away, moves after `chmod`, or the pinned digest becomes a placeholder.
- **No wizard producer invents a value its caller did not supply** — producing any
  non-prose kind used to substitute a hardcoded one: a stakeholder called `Sponsor`, a
  `Preferred Vendor` agreement, a `defect_rate` metric at 1.0/0.5, a `labour` budget line of
  1000, a `Wizard-seeded risk` at probability 0.2, a `Kickoff complete` milestone, a baseline
  whose planned cost — BAC, the figure every EVM number is measured against — was 1000. The
  presence checks are content-blind `bool(rows)`, so one substituted row marked that output
  produced for good and nothing asked for the real value again. Each producer now refuses
  instead (`MissingField`: `422` on the form, exit 2 on the CLI, no row written), as the
  narrative kinds already did for a missing body, and the browser's apply forwards the fields
  the chosen kind needs. Which fields those are is one table — `wizard.cli.required_fields`
  reads it for a form and `seed_fields(kind, as_of)` answers it for an unattended run.
- **The wizard's form collects the fields its outputs are made of** — the select offered a
  browser every kind the step could produce, but the only input under it was the prose
  textarea, so choosing a stakeholder register, a risk, a budget line or a milestone posted
  a body with no name, probability or amount in it. Now that the producers refuse rather
  than substituting a value, those clicks would each be a `422` a person could not answer.
  The form renders one input per field the offered kinds need, read off the same
  `required_fields` table the producers refuse against — a date input for a target date,
  a number for money and probability, a select drawn from the ORM's own vocabulary for a
  cost category or a RAG reading — and a refused post hands every typed value back, the
  contract the prose textarea already had.
- **An agent reading the API guide is told the list window exists.** `?limit`, `?offset` and
  `?q` reached the API without a line in the agent guide, and the guard that should have caught
  it was satisfied by either guide naming a parameter — so the user guide covered for it. The
  agent guide is the contract a machine reads and it has no other page to fall back to, which
  made this the one reader most likely to page through a list and least able to notice it had
  been truncated. Section 4 now states the window, the clamp and the `X-Total-Count` header to
  compare against, with both numbers derived from `LIST_LIMIT` and `LIST_LIMIT_MAX`; the guard
  now requires the agent guide specifically.
- **The shipped task sample exercises `actual_effort`.** `bin/sample-tasks.csv` omitted the
  column from its header, so the worked example never touched a field the importer has always
  accepted — one row now carries 52.5 hours against a 40-hour estimate and the others leave it
  blank, covering the "a blank optional cell is omitted, never posted as empty" path too.
- **The Dockerfile no longer claims psycopg comes from the `[dev]` extra.** It moved to
  `[project.dependencies]`, so `.` installs it and naming it on the install line is
  belt-and-braces rather than load-bearing. The line stays until an image build has actually
  been watched — no docker daemon has been available here, so nothing about the image has been
  proven against a real build.
- **The business map no longer teaches two vocabularies for one wash.** Its single
  legend explained the four `.st-*` washes as share buckets — `st-ok` is "half+" — while
  the project badges directly under it painted the same washes with a process *state*
  word, so `st-ok` read "Produced" a few lines below a legend saying it meant "half+".
  Each vocabulary now carries its own legend beside the badges it explains, and the
  listing's is built from the very predicate that filters its rows, so it can neither
  name a state no row can carry nor omit one that a row does.
- **An empty process listing says why it is empty.** "No applicable projects." bypassed
  the shared empty state and named no reason, no command and no link — yet it was equally
  true of three different causes a reader could not tell apart. The listing now names
  whichever one holds: no output of the process is a kind the store tracks (with a link
  to what it produces), every project has waived it (each waiver named and linked), or
  there are no projects yet (`POST /projects`). The three are exhaustive by construction,
  since an assessable process on an unwaived project is a listed row.
- **A person's capacity is theirs, not one project's slice of it.** The Resource evaluator
  summed a person's remaining hours *on this project* and divided by the whole of their
  `capacity_hours`, so nobody could ever be flagged over capacity: the demo seed's two
  people carry **150 %** and **135 %** of a capacity three surfaces label `Capacity
  (hrs/wk)`, and the project holding the only work one of them was assigned rendered green
  with "No live threats". Every project only ever saw its own slice. It now weighs the
  store-wide total `person_task_loads` already prints beside that capacity on the
  department page and the capacity heatmap — one summation, not a second one — and raises
  the threat on **every project holding some of those hours and on no other**: each of
  those is a cause and can level its own share, while a project the person holds no open
  work on is neither. The threat carries both figures, `peak ratio 1.50 — 60 h in all,
  40 h of it on this project`, so the ratio reconciles against the project's own board
  instead of reading as an error. Resource scores rise wherever someone's work spans
  projects, so a sign-off recorded against the old, smaller score stops suppressing its
  threat and needs re-signing — which is the point: it was signed against a figure that
  was never the person's real load.
- The demo seed spreads its work over two part-time contractors rather than putting
  everything on the two leads. One person over the line now turns every project they
  hold work on red, and with two people holding all eight tasks the demo dashboard
  folded to red-and-no-data — a rollup all one colour, which the seed exists to avoid.
  Theo (40 h against a 30 h week) and Nadia (24 h against 20 h) carry the over-capacity
  story on the two projects that can hold it; Dana and Priya come back under, so Archive
  reads amber on its own cost and change signals and Fleet reads green.
- The weekly-status S-curve no longer separates planned (PV) from actual (AC) by colour
  alone. The two solid strokes were a computed **1.14:1** apart in light and **1.08:1** in
  dark — about 1:1 in greyscale, so on a printed or photocopied status pack a reader could
  not tell which line went above which where they cross. AC is now a **dashed** `--ink`
  stroke against PV's solid `--muted-ink` (3.03:1 / 2.33:1), the budget reference keeps its
  own dash rhythm, each legend key is drawn exactly as its series is, and the whole curve is
  repeated as a **table** in plot order — the `scroll.wide` text-twin idiom the Gantt and the
  dashboard S-curve already use. AC also stops borrowing `--rag-red`, so a project under
  budget no longer draws its actual cost in the alarm colour.
- The Gantt's planned window is edged in `--gridline` (3.23:1 / 3.38:1) instead of `--rule`
  (1.45:1), so a task at 0% complete — which has no progress fill at all — is no longer a
  ghost. `--rule` is exempt from every contrast floor as a decorative box edge; a new gate
  keeps that exemption out of `<svg>`, where the geometry *is* the content.
- **The dashboard's charts stay legible, and say when they have nothing to draw.** The cost
  S-curve anchored both end labels at the same `x`, so two series finishing within a few
  percent of each other — the healthy case — printed their figures 7.1 units apart under an
  11.2px glyph box, on top of each other. The lower label is now pushed a full line height
  clear (the pair cannot invert or leave the box) and the actual-series label moved inside
  the RAG-tinted group, so each figure belongs to a line. With no approved baseline anywhere
  the curve's whole slot used to vanish while the treemap kept its own beside it; the shared
  empty state now takes it and names the next step, as the Gantt does. The portfolio treemap
  splits on weight across each rectangle's **longer** side instead of claiming a share of the
  remaining rect along an alternating axis: 20 equal portfolios ran to 30.7:1 with a 10.5-unit
  edge and 1 of 20 named, now under 3.5:1 with every rectangle named. `treemap_layout` places
  the labels itself against real geometry — name and budget, name, or a truncated name,
  whichever fits — so the landscape-only `w > 70 and h > 26` gate can no longer drop a name
  from a tall rectangle nor overflow a long one out of a narrow box. Each burn sparkline's
  budget reference buys the same 1.15 headroom the S-curve has: under budget it sat on `y = 0`
  with half its stroke clipped by the viewBox, reading as a box edge or as absent.
- **The attention rail prints its severity.** Each card's 6px stripe was the only carrier,
  and the four RAG tokens sit 1.01–1.44:1 apart from *each other* — red beside amber, green
  beside unknown — so the stripe said "a severity" and never which one. The rail now renders
  the same severity badge the threat board does, off the same closed vocabulary. A card whose
  class comes from the data must print that word: `login.html`'s literal `sev-red` error alert
  is outside the rule by construction, not by an exemption a fix could be added to.
- **The dashboard's "unchanged" trend badge says unchanged.** It shipped as a bare en dash with
  the whole meaning in a `title=` — hover only: no keyboard, no touch, no print, and not
  announced on a non-interactive span. The glyph is now `aria-hidden` with the words beside it
  in an `sr-only` span. The guard that already covered the threat board named `home.html` as
  owed and skipped it, so the one file still failing was the one file certified; the exemption
  is gone and the rule is total.
- **A figure is spelled the same way in the label as on the page.** The burn sparkline announced
  `Actual 800.0 of budget 1000.0` while its own row printed `800` and `1,000`, and the cost
  S-curve announced `1000`. Both go through `{:,.0f}` now, and the page walk reads every
  `aria-label` back, so a raw float or an unseparated thousand cannot reach a reader's ear.
- **The portfolio treemap's links are reachable.** The SVG claimed `role="img"`, which tells a
  reader it is a single graphic and prunes its subtree: both portfolio-rollup links inside it,
  and the `<title>` naming each one, were unreachable rather than merely unlabelled. The role is
  dropped — the `aria-label` still names the graphic — so the treemap reads as what it is, a set
  of named portfolio links. No `role="img"` SVG may hold a link.
- The department drill page's statement ceiling can **fail on the N+1 it names** again:
  `_MAX_DETAIL_STMTS` sat at 28 while the page measured 23, so the per-person regression the
  comment exists to catch — swapping the batched `person_task_loads` for one
  `person_task_load` per person shown — cost three statements, landed at 26, and the whole
  file stayed green with the N+1 live. Five statements of slack against a three-statement
  defect, the same shape as `MAX_PROJECT_HUB_STMTS` before it was re-derived. Both pages were
  re-measured rather than trusted (list 21, drill 23 — the recorded figures held) and the
  drill ceiling is now 24, measured + the one statement `tests/test_perf_n1.py` allows a call
  whose defect is priced in the unit it walks one of. Reintroducing the N+1 now fails it at 26
  against 24. The list ceiling is left at 27: its two named regressions were measured at 81
  (lazy baseline hierarchy) and 57 (per-project cost read), both an order of magnitude clear
  of it, so it was already a guard rather than decoration. Every measurement is recorded
  beside the constant so the next reader re-derives nothing.
- A process-map cell now drills into **this project's** reading of the process, not
  the theory page: `/pmbok/{id}?project={id}&as_of={date}` carries the project and the
  pinned as-of through the hop and adds the live status of every artifact its ITTO
  names (`mapping.resolve`), the project's computed process state, and the knowledge
  area's assessment with the live threats and recommended actions attached — then links
  back to the map the reader came from instead of the theory grid. A kind the store
  holds no data for reads *not tracked* rather than *absent*, and a process with no
  tracked output says so in words, so the nine Monitoring & Controlling cells that read
  "not started" forever finally reach the evaluator that is shouting about them.
  Without `?project=` the page is the stateless reference it always was.
- A process the catalog **never tracked** stops reading as work not started. 26 of the 49
  processes name no output the store holds a resolver for, so the state computed for them is
  `not_started` about the STORE — there is nothing to look for, so nothing is ever found —
  and every project's map printed that in 26 of its 49 cells as a verdict on the *project*:
  work it owes and has not begun. Nothing is owed on any of them. Those cells now read
  **Not Tracked**, in the grid and in the sign-off picker beneath it, the same word an
  artifact with no resolver already reads on the drill page. It is a word rather than a sixth
  mark, so it needs no legend chip to be read in greyscale or in print, and `ProcessState`
  keeps the five members the rollup, the wizard, the report and the API count on. A recorded
  decision still outranks it: waive or sign off an untracked process and its cell shows the
  decision that was signed.
- A page template that names something no route passed now **raises** instead of
  rendering the empty string. `report/engine.py` was made strict; the ~22 HTML page
  templates rendered through `web/templating.py` kept Jinja's default `Undefined`, so
  misspelling `{{ as_of }}` as `{{ as_off }}` on the department list printed
  `As of <strong></strong>` — the date gone — and the page still answered 200 with the
  web suite green. The shared environment is now built here rather than by Starlette's
  `directory=`, with `undefined=StrictUndefined`, so a missing or misspelt name stops
  the render and says which name, for all 22 templates at once and for pages not
  written yet. No template needed a fix: every route already passes every name its page
  uses, proven by walking every GET page the app registers against two stores — one
  with work under every row, and one with the rows bare, which is the only way an
  empty-state branch renders at all.
- The Process Map **document** now pins its completeness and its grid to **the engine's own
  answer**, not to the presence of a label. `tests/test_report_itto_docs.py` asserted only that
  the string `Completeness:` appeared — and the template prints that label unconditionally, so
  the test passed whether the figure read `9%`, `0%`, `n/a`, or nothing at all. Dropping the
  `* 100` in `report/documents/process_map.py` rendered `0%` and the file stayed green;
  typo'ing the template variable rendered the label with **no value** and the whole suite
  stayed green, because the report Jinja environment leaves an undefined name empty rather
  than raising. The test now walks `state.completeness` and `state.project_process_states`
  itself and requires the rendered percentage to match, and all 49 table rows to match id,
  name, group, area and state in catalog order — after first asserting the fixture is
  part-done and its states disagree, so a flat or blank document cannot satisfy either
  equality, and no expected figure needs editing when the fixture grows.
- A **waived process no longer looks exactly like an untouched one**. The process map
  drew all five states in colour alone — and two of them, `waived` and `not_started`, in
  the *same* neutral wash, so the legend shipped two identical grey chips under two
  labels for a distinction the grid never drew (a waiver drops a process from every
  completeness figure; not-started counts against it). Each state now also carries a
  visible **mark** — `○` not started, `◐` in progress, `●` produced,
  `✓` signed off, `—` waived — printed both in the cell and on the legend chip
  that names it, so the state reads in greyscale, in print and to a colour-blind reader,
  with colour only reinforcing it. The off-screen word and the hover title stay; neither
  was ever visible. On the business-wide map each cell now **prints its share** as a
  figure instead of carrying it only as a wash and a `title=`.
- Earned value is read at the date it is asked for, so an EV-derived trend can finally
  say "better" or "worse". `Task.percent_complete` is one undated *current* number and
  the EVM adapter stamped it with the as-of being asked about, so EV came out identical
  at any two as-ofs inside the plan window and every arrow comparing them could only
  read "flat". The series was never missing — the append-only ChangeLog has held it all
  along — so the assessment path replays it instead of inventing one. No new table, no
  migration. A logged change counts for an as-of on or after its own UTC date; a task
  reads as entered before its first dated change; and a reading the log cannot date — a
  task's creation, or a store written without the audit listener — answers every as-of,
  so no existing store starts reading zero.
- A report template that names something no document passed now **raises** instead of
  rendering the empty string. Under Jinja's default `Undefined`, misspelling
  `{{ completeness }}` as `{{ completness }}` made the Process Map print
  `**Completeness:** ` with no figure — and the whole suite still passed, because a
  vanished number looks like nothing at all. `report/engine.py` now sets
  `undefined=StrictUndefined`, so the render stops and names the missing variable, for
  every document at once and for templates not written yet, rather than one pinned
  assertion per document catching its own symptom after the fact. No template needed a
  fix: every document already passes every name it uses, proven by rendering all eleven
  for every seeded project across six as-of dates.
- **Risk threat scores are now one unit, so any two are comparable.** The score was
  a share of contingency when a reserve existed and raw dollars when none was held
  (a $1 denominator floor guarding the division), so a $600 uncovered exposure scored
  600.0 and outranked a $45,000 one scoring 29.0 on `/threats`, the dashboard attention
  rail and `assessment.md`. It is now the uncovered exposure as a share of the budget
  left to spend, in every case. **Every risk threat score changes**, so a threat
  sign-off recorded against the old number no longer suppresses it — re-sign the ones
  you still accept.
- A project with no approved plan, and any project asked about an as-of before its plan
  began, no longer reads red on risk. With no budget there is no reserve to fall short
  of, so the evaluator answers "nothing to assess" (green) — the same answer the cost
  evaluator already gives at BAC 0 — instead of reading every open risk as uncovered.
- The dashboard's business S-curve now takes its date range from the approved plan,
  like every figure drawn on it. It read the newest baseline of any status, so drafting
  a re-baseline that started earlier stretched the chart back over months the plan had
  not begun — months that earn nothing — and the curve filled with zeroes that looked
  like reported figures. A project whose only baseline is an unapproved draft now reads
  as unbaselined, the same empty state it shows everywhere else.
- A threat sign-off now records the score the server computed at that as-of, instead of
  the `signal` the caller posted. An arbitrarily large posted value used to mute a threat
  permanently — no live score could ever climb past it, so the promised re-arm on a
  regression silently never fired. The field is gone from `SignOffIn` and from the
  `POST /sign-off` form handler, so there is nothing left for a caller to influence; a
  sign-off whose subject is not a currently-scored threat (a process decision, or a threat
  that is not live) records no signal, and a signal-less sign-off never suppresses.
- **The weekly-status trend stops hiding a reading in a tooltip.** Each dot carried a
  `<title>` with its date and percent, inside an SVG marked `role="img"` — a role that makes
  the whole chart one node and prunes everything beneath it, so that string reached a mouse
  pointer and nobody else while reading, in the source, like the text alternative it is not.
  It was also a duplicate: the axis names both dates and the table twin beside the chart
  already prints date, percent **and** RAG for every snapshot, which the tooltip never
  carried. The tooltip is gone rather than the role — neither chart on this page holds a
  link for `role="img"` to prune, so the role is doing its job, and the label plus the twin
  are the alternative it promises.
- **A weekly status with no cost baseline names the next step.** The planned-vs-actual slot
  fell back to one italic line that named no command and no link, so the reader was told the
  curve was missing and left to guess how to get it. It now renders the shared empty state
  every other surface uses, naming `POST /baselines`, `POST /baseline-lines` and
  `POST /cost-entries`, and linking the wizard that walks them in order. The empty-state walk
  reaches `/projects/{id}/status` now, so a slot on this page cannot go back to saying
  nothing.
- The weekly-status trend plots **elapsed time**, not row number. Every point sat at
  `34 + index / span * 274`, so three readings taken a day apart and a fourth taken three
  months later drew as four evenly spaced points and the slope between them reported a rate
  of progress the dates never supported. Nothing enforces a weekly cadence — the only rule
  on the series is one row per project per **date** (`uq_status_snapshot_project_date`) and
  the form writes at whatever `as_of` it is posted. Each point now carries its position
  along the real span, computed in `pages.trend_series`, and the axis ends name the two
  dates it is drawn between. (The dashboard S-curve, burn sparkline and EVM curve stay
  index-plotted, honestly: their samples come from `gather.sample_dates`, evenly spaced by
  construction. This series is stored rows at operator-chosen dates, so it cannot.)
- Each snapshot's RAG is **readable as a word**. It was carried by the dot's fill (adjacent
  RAG values sit 1.01–1.31:1 apart, and each dot contrasts 1.06:1 with the line it sits on)
  and a hover-only `<title>` inside an SVG marked `role="img"`, which prunes it — so the RAG
  history was reachable by nobody but a mouse user with normal colour vision. The trend now
  carries a text twin: date, percent and RAG per snapshot, in the `scroll.wide` idiom the
  S-curve twin already uses.
- **A weekly status with no readings names the next step too.** The trend slot fell back to
  one italic line that named no command and no link — the same defect its planned-vs-actual
  neighbour had just been fixed for, left standing because converting it exposed the fixture
  hole below. It now renders the shared empty state, linking the snapshot form at the foot of
  the same page and naming `POST /status-snapshots`, and says why one reading draws no slope.
  The two slots empty independently and are filled by different actions, so the empty-state
  walk now pins both ids rather than accepting whichever one happens to render.
- **The weekly-status trend chart is walked for accessibility at all.** The a11y and
  responsive walks share one fixture, and it seeded no `StatusSnapshot` — so the trend drew
  its empty branch, which carried no `empty-state` class, so the page did not read as blank
  and nothing complained. Every rule both walks apply — one `<h1>`, scoped and captioned
  tables, no raw float in an `aria-label`, a named and focusable scroll box around each wide
  table — had therefore never once been applied to that chart's markup. The fixture seeds two
  dated snapshots a quarter apart, so the line, both axis ends and the table twin are rendered
  and walked; all four rules already held.
- **Severity is styled for the whole vocabulary, not for the two values that reached a
  card.** `base.html` declared `.sev-red` and `.sev-amber` only, so a `green` or
  `unknown` severity — the attention rail's data-signal items are `unknown` — drew no
  stripe at all, making "no severity shown" read exactly like "not a severity we style",
  and its severity badge inherited no fill: white ink on the white page, 1.00:1, the
  word invisible. All four RAG statuses now carry a stripe and a rated badge fill, and
  the test walks `calc.rollup.RAG_SEVERITY` rather than a hand-kept list, so a new
  member of the vocabulary cannot reach a card unstyled.
- **The "unchanged" trend badge says unchanged.** On the threat board it was a bare en
  dash with the whole meaning in a `title=` — hover only: no keyboard, no touch, no
  print, and not announced on a non-interactive span. The glyph is now `aria-hidden`
  with the words beside it in an `sr-only` span, the shape the process map already uses.
  (The same badge on the dashboard rail is still `title=`-only.)
- **Completion rings no longer borrow an all-clear.** Both process maps drew the arc in
  `--rag-green` at every level, so 5% complete was painted the colour reserved for
  "green status". The arc is now `currentColor` — the same ink the ring prints its own
  percentage in — over the unchanged 15%-opacity track.
- **The portfolio treemap is readable, and no longer claims an area it is not drawing.**
  Every label was painted in `--ink` over its own RAG rectangle — 2.66–3.48:1 in light and
  1.74–2.51:1 in dark, with the `.8`-opacity budget line down to 2.37:1, so all eight
  pairings sat under the 4.5:1 WCAG AA floor for 10.4px text. Labels now take
  `--badge-ink`, the token that exists to sit on a RAG fill (5.00–6.54:1 light,
  5.93–8.56:1 dark), and carry no opacity. Separately, a store with portfolios but no
  approved baseline anywhere drew every portfolio as an equal slice of the canvas under a
  heading and an `aria-label` that both promise area proportional to BAC; with no budget
  to divide there is no honest area, so the chart is replaced by the shared empty state
  naming the next step (`POST /baselines`) — the answer the Gantt already gives for the
  same missing input.
- The Weekly Status Report no longer prints cost variance `0.00` and schedule
  variance `0.00` for a project with no approved plan. A variance is a distance
  from a plan, so with no plan both now read `n/a` — the same answer CPI, SPI and
  EAC already gave in the same table, instead of a zero that read "exactly on
  budget, exactly on schedule" for a project with neither. Projects with an
  approved baseline are unchanged.
- **The wizard's producer no longer writes prose nobody typed** — `driftless wizard apply
  --kind assumption_log` (or any narrative kind) with no `--field body=` used to file
  `(seeded by the onboarding wizard)` as the project's own assumption log. It now refuses,
  the way the browser form already answers `422`: a message on stderr and exit 2. The
  request schema never caught this — `body` defaults to empty there — and the row that
  landed read *absent* to the process-state engine anyway, so the wizard reported an output
  every completeness figure still counted missing. The placeholder moved to
  `wizard.cli.seed_fields`, the seeding side that means it, so an unattended onboarding run
  still converges with nothing typed.

### Security
Both entered late — written off the code as it stands, newest first.

- **The operator's age private key cannot enter the image, and no deployment file points at one
  inside the build context.** `docker compose up --build` sends the whole repository to the daemon,
  and an image layer is permanent: `docker save` recovers a file copied in even after a later step
  deletes it. The `Dockerfile` did `COPY deploy ./deploy` while `OPERATIONS.md` had operators run
  `age-keygen -o deploy/age-key.txt`, so a build on the operator's own machine baked the key that
  decrypts `deploy/secrets.enc.env` — `DRIFTLESS_SESSION_SECRET` (forge any user's cookie),
  `DRIFTLESS_API_TOKEN`, `POSTGRES_PASSWORD` — into the image beside the encrypted overlay.
  `.gitignore` named the key and did nothing; git's ignore rules have no effect on a build context.
  Robust first: the image copies `deploy/entrypoint.sh` by name, so the key cannot enter even with no
  `.dockerignore` at all. `.dockerignore` is the second lock, the docs now generate the key at
  `~/.config/driftless/age-key.txt` outside the checkout, and the compose mount is
  `${DRIFTLESS_AGE_KEY:?…}` with no fallback — the old default pointed back at `./deploy/age-key.txt`,
  a value nobody typed aimed at the one directory a build would bake. `tests/test_docker_build_context.py`
  derives all three checks from `.gitignore`'s own secret section, so a pattern added there fails the
  suite until `.dockerignore` and the compose file learn it too.

- **The sign-off ledger records the signer the gate resolved, not the one the request claimed.**
  `signed_by` was an ordinary request field on both write paths, so any contributor could POST
  `signed_by="CFO"` — or edit the hidden input on the threat board's form — and append a permanent,
  un-deletable approval in somebody else's name, which is the one thing the ledger exists to prevent.
  Where the gate resolved a principal the server now stamps that username and discards the request's
  claim, the shape `StatusSnapshot` already used for its stamped percent; discarded rather than
  refused, because both browser forms post the field on every sign-off, and the 201 body carries the
  name actually stored. The on-behalf-of write survives and is now pinned by a test: the shared
  `DRIFTLESS_API_TOKEN` bearer resolves no principal by design, so an importer or an agent recording a
  decision a named human made offline still supplies the name — the only path that can.
- **The dependency audit runs. It never had.** `pip-audit` installed itself with the
  runner's system `pip`, which PEP 668 refuses (`externally-managed-environment`), so the
  step died before the tool existed — and a gate step skipped it on every pull request that
  did not touch a dependency file, which is nearly all of them. Of the 44 runs since this
  repository was extracted, 43 skipped the audit and the one scheduled run that reached it
  failed there. It now pins its interpreter with `actions/setup-python` and installs
  `pip-audit` into its own virtualenv, so nothing it does can touch a system Python.
- **The audit scans what the image ships.** A new `requirements.lock` records the resolved
  version of every dependency and is used as a *constraint* file by both the test job and
  the audit, so the two of them and the Docker image no longer resolve "latest" three times
  independently. The audit installs `uvicorn` alongside `.[dev]` because the image's own
  install line does, and a green audit that omitted the web server said nothing about it.
- **A red nightly now has a reader.** A scheduled run that fails opens a GitHub issue and
  comments on that same issue thereafter, so a week of red nights is one thread rather than
  seven — or, as before, nothing at all. That silence is why the broken audit above went
  unnoticed from extraction until an audit went looking for it.

### Docs
- `OPERATIONS.md` and `docs/admin-guide.md` now describe the health probe as the route
  became: one `SELECT 1` behind the container healthcheck, open to an orchestrator because
  it discloses only whether the store answered. The guide runs the probe rather than
  asserting it, and a new `tests/test_docs_health_truthfulness.py` fences the old prose
  against the route's real behaviour. The request-log section names the shipped
  `deploy/logging.json` the image already passes to uvicorn, instead of describing a
  document an operator has to author.
