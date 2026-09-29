# Testing and quality gates

Continuous integration, the page-snapshot bundle, the static showcase
generator, the performance, accessibility and responsive floors, and the
sample-reports bundle moved out of [`README.md`](../README.md) here — the
*Development* section there still covers building the venv and running
`bin/driftless-gates.sh`.

## Continuous integration

CI enforces ruff (lint + format), mypy in strict mode, detect-secrets,
pip-audit, and the coverage floor `pyproject.toml` sets in
`[tool.pytest.ini_options] addopts` — read `--cov-fail-under` there rather than
here, which is how this line came to name a floor CI had already left behind.
Runtime dependencies are declared by the phase that first imports them, so an
unused dependency never becomes CVE surface.

Three workflows, on pull requests to `master` plus a nightly re-validation of
`master` (there is no per-merge push trigger — the pull-request gate is the gate,
and the nightly bounds post-merge drift at 24h):

| Workflow | Runs when | What it does |
|---|---|---|
| `.github/workflows/ci.yml` | every PR, nightly, manual | **Quality** (ruff, detect-secrets, mypy strict), **Tests**, **Migrations** — the alembic chain run against a real Postgres service container, so the schema is proven where it ships and not only on SQLite — and the **Docker image build**, which builds the image and pushes nothing, because every other gate that mentions the Dockerfile only reasons about its text: as four independent jobs, none waiting on another |
| `.github/workflows/pip-audit.yml` | PRs that touch `pyproject.toml`, `requirements.lock` or `.pip-audit-ignore`; nightly; manual | audits a clean venv holding exactly the shipped dependency set |
| `.github/workflows/scheduled-failure-alert.yml` | called by the two above, on a failed **scheduled** run | opens one deduped GitHub issue and comments on it thereafter |

Here, every job runs on the organization's **self-hosted** runners: the org buys
no GitHub-hosted minutes, so a hosted job in a private repository is refused in
seconds. The same workflows are published with the rest of this tree to the public
repository, which no org runner group admits, so there each job either runs
GitHub-hosted (free for a public repository) or does not run at all. `ci.yml`,
`pip-audit.yml`, `docker-publish.yml` and the alert workflow name their runner per
repository; `release.yml`, `browser.yml` and `uptime-check.yml` skip the public
repository. `tests/test_deploy_hardening.py` fails any job that would ask the
public repository for a self-hosted runner, or this one for a hosted one, and any
job or `runs-on:` it cannot read, so a new shape fails the test instead of passing
it unchecked.

That reverses an earlier decision, so the reasoning is worth keeping. Every job
used to run GitHub-hosted on the grounds that a pull request is code anyone may
submit, and a self-hosted runner would execute it on a machine the maintainer
owns. That is right wherever anyone can open a pull request. It does not bind
here: this repository is private and single-maintainer, with no outside
collaborators, so no untrusted party can start a workflow at all. A sibling
private repository in the same organization already runs its CI this way, on the
same runners.

**The condition that would make it wrong again:** if this repository gains an
outside collaborator or becomes public, plain `pull_request` on a self-hosted
runner becomes exactly the code-execution path the old rule described, and this
has to be revisited. The public repository this tree is published to is that
case, which is why no job runs self-hosted there: a pull request there is code
anyone may submit, and the runner groups would refuse the job anyway, leaving its
check queued for good. `tests/test_deploy_hardening.py` records the precondition
for this repository, asserts it for the public one, and still fails the suite for
`pull_request_target` on a self-hosted runner —
that trigger runs in the base repository's context with access to its secrets
while checking out the fork's code, which is dangerous in any repository,
private or not.

**The probe runs on the pool too.** `uptime-check.yml` asks for the `quick`
label, so a one-request probe never queues behind a heavy suite. A probe sharing a
box with the service it watches goes quiet during the very outage it exists to
report; the workflow says so where the next reader will see it, since only an
outside probe covers that case.

`bin/driftless-gates.sh` mirrors all four `ci.yml` jobs, not just Quality and
Tests: `--migrations` starts a `postgres:16` container itself (same image
reference as `docker-compose.yml`'s `driftless-db`, same `POSTGRES_USER`,
`POSTGRES_DB` and trust auth as the Migrations job — an ephemeral, throwaway
container has no credential to leak), publishes it to whatever free host port
Docker assigns rather than assuming `5432`, waits on `pg_isready`, then runs
`tests/test_migrations.py` against it exactly the way the Migrations job does.
Unset locally, `DRIFTLESS_TEST_DB_URL` makes that module skip its Postgres half
and prove the migration chain only on SQLite, which takes Alembic's
copy-and-swap batch path — the one path production never takes; the stage
exists so a local run proves the chain the way it actually ships. `--docker-build`
runs a plain `docker build` of the repo, the same as the `docker-build` job —
nothing pushed, no registry, no cache. Both need Docker and fail loudly, never
skip quietly, if it is unavailable; both are part of the default full run
(`bin/driftless-gates.sh` with no stage flags), the same as `--quality`,
`--tests` and `--samples`, so a plain run answers the same question CI would
have. `tests/test_local_gates_cover_ci.py` reads `ci.yml`'s job list and fails
if a job appears with no matching stage, so a fifth CI job added later shows up
as a red test here rather than a silent gap; it reads `pip-audit.yml`'s job
list the same way, which is what covers the paragraph below.

`--audit` is the fifth stage, and the odd one out: it mirrors `pip-audit.yml`,
a whole second workflow rather than a `ci.yml` job, and it is the only stage
that touches the network on **every** invocation — the others hit the network
once, to install a tool, and then run offline. It builds two throwaway venvs
fresh each time, the same split the workflow uses: a tool venv holding only
`pip-audit`, and a deps venv holding *exactly* what the workflow audits —
`requirements.lock` as a constraint plus `.[dev]` and `uvicorn`, the same
install line `requirements.lock`'s own header documents (`uvicorn` because the
Dockerfile installs it and `pyproject.toml` never declares it; `.[dev]` because
the image installs the smaller, runtime-only half of that set, so the audit is
a deliberate superset of what ships and never a different one). `.pip-audit-ignore`
is applied identically to the workflow: one CVE id per line, comments and
blanks skipped, each turned into `--ignore-vuln`. A transient PyPI network
error gets three bounded retries with the same backoff `pip-audit.yml` uses;
anything else — a real finding included — fails the run loudly.

It is part of the default full run (`bin/driftless-gates.sh` with no stage
flags), because the alternative is the exact failure this stage exists to fix:
`pip-audit.yml`'s own nightly schedule no longer runs at all now that Actions
is dead, so an opt-in-only flag nobody remembers to pass would mean dependency
CVE scanning still happens on no cadence, just with a different missing switch
than before. Naming a single other stage explicitly (`--quality`, `--tests`, …)
leaves audit out on purpose, so a fast local iteration loop never pays its
network cost; `--audit` forces it back on alongside a named stage, and
`--no-audit` is the declared, printed opt-out for a run that is genuinely
offline (a plane, a flaky connection) — never a silent skip.

`--browser` is the sixth stage and the only opt-in one that is not in the default
run at all. It installs `.[browser]` plus Chromium and loads the dashboard,
project hub, scorecard, configuration and status pages at 1280px and 390px,
asserting that neither overflows sideways and that no page script raised. It
exists because every other web gate reads HTML as text — `test_web_responsive`
says so in its own docstring ("no test here renders a viewport") — so where the
flex rows wrap and whether a page fits a phone were eye checks and nothing more.

`tests/browser/test_display_audit.py` renders those five beside the eight the
list originally skipped — `/map`, `/process-map`, `/projects/{id}/flow`,
`/projects/{id}/gantt`, `/org/heatmap`, `/projects/{id}/assist/cost`, `/methods`
and `/pmbok/proof`. Those were the pages a static gate could say least about,
because on most of them the content *is* a drawing: the template emits an
`<svg>`, the structural checks confirm the element exists, and whether it came
out full-width or thumbnail-sized, labelled or bare, was answered nowhere. A
thumbnail method map and an empty flow page both shipped green that way.

Each render also writes an **audit record** — viewport, `scrollWidth` against
`clientWidth`, the box of the largest SVG, how many SVG text labels actually
came out visible, and everything the page logged — as JSON under
`reports/browser-audit/` (already git-ignored, like every other regenerable
report; `DRIFTLESS_BROWSER_AUDIT_DIR` moves it so CI can upload it). The record
is evidence, not a gate. What the module *asserts* is only what no page may do:
answer with something that is not HTML, raise in the browser, come back with an
empty body, or overflow the document sideways — so a blank or errored render is
red on its own, without anyone opening a screenshot.

It deliberately asserts nothing about how much data a page drew. The seeded
fixture is thin and leaves flow and gantt sparse; an "at least N bars" check
here would be a test of the fixture, not the product, so the counts are recorded
and never fail the run.

Its first run found one, and the register is empty again because of how that
entry had to end. `/process-map` pushed the document 475px sideways at 1280 and
1357px at 390 even though `_scroll.wide()` **was** in the template — so
`test_web_responsive` saw a declared scroll container and passed it, while the
laid-out page showed the overflow reaching the document anyway. The cause was
not the container failing to constrain its table: `.sr-only` is
`position: absolute`, and an absolutely positioned box lays out against its
nearest *positioned* ancestor — with none, the initial containing block, which
no intermediate overflow box clips. The grid's fifty off-screen spans therefore
sat outside the scroll box's clip and stretched the document to the widest one's
right edge, while the box itself measured a correct 1232px and scrolled its own
2026px internally. `.scroll-x` is `position: relative` now, which makes it the
containing block for every wide surface, and `tests/test_web_business_map.py`
pins that one declaration at the static tier so a sheet that drops it is red
without the opt-in tier having to run.

The entry was a `strict=True` xfail naming the defect, which is what made the
fix delete it: an unexpected pass turned the run red the day the layout worked.
A non-strict marker would have stayed green either way and outlived the bug.

`tests/browser/test_preferences.py` adds the three settings a rendering engine
honours and a text gate cannot see: a dark colour scheme (the body's computed
background must actually move, not merely be mentioned in a rule), a keyboard
with no pointer (the first Tab must land on the skip link AND bring it back
on-screen from `left: -9999px`), and a request for less motion (the dashboard's
KPI figure must be final at first paint rather than counting up). Each was
checked by mutation before it landed — breaking the media query, the `.skip:focus`
rule and the `prefers-reduced-motion` guard each turns the matching check red.

It **supersedes nothing**. `bin/driftless-snapshot-pages.py`'s header argues
against a browser dependency on the grounds that its only new information is
font rasterization; that judgement stands for the required floor, and the
byte-diffable snapshots remain it. This tier runs beside them, from the Actions
tab or the nightly `browser.yml`, and is deliberately not a required check: a
flake in a rendering engine must never block a merge. `browser.yml` is
registered in `tests/test_local_gates_cover_ci.py` like `ci.yml` and
`pip-audit.yml`, so it cannot quietly stop running the way pip-audit once did.

The suite runs under `pytest -n 4` (pytest-xdist): the three self-hosted runners
share one twelve-core host, so a fixed four per job keeps three concurrent jobs
inside it. It is xdist-safe as a property of the suite, not an assumption: every
test builds its own store, and the serial and parallel runs are checked to give
the same count at the same coverage. Every test's store is a file-backed sqlite
database under pytest's `tmp_path`, so CI passes `--basetemp` pointing into
`/dev/shm` (beside the coverage data files already there): on the host's
rotational disk those writes held the run at 40–54 minutes and, with two staging
barrier runs alongside, past the job's 60-minute timeout (2026-09-04). Locally the
same flag gives the same speed-up: `.venv/bin/python -m pytest --basetemp=/dev/shm/driftless-tmp`.

`requirements.lock` is the resolved version of every dependency, used by both the
Tests job and the audit as a **constraint** file — pyproject.toml still decides
*what* is installed, the lock decides *which version*. Without it the two jobs and
the Docker image each resolved "latest" independently, so a green audit was not a
statement about the shipped image. Regenerate it whenever a dependency changes;
the command is in the file's own header. Dependabot does not maintain it (see
`.github/dependabot.yml`), so a dependency bump has to carry the regenerated lock
in the same pull request.

**Merging.** A pull request lands only on a **complete green** CI run — red,
pending and incomplete all refuse, and nothing merges an unfinished run. Merging
is a human decision: no workflow and no bot here merges anything, which is also
why `.github/dependabot.yml` configures no automerge.

## Page snapshots

`bin/driftless-snapshot-pages.py` writes every page the app serves to
`docs/page-snapshots/` as rendered HTML — one file per page it finds, from the
demo store seeded through the validated API at a pinned `--anchor`. How many that
is moves whenever a page is mounted, so the count is not written down here. Every chart is inline
SVG rendered server-side and nothing renders in the browser, so the response is
the whole visual truth and no headless browser is involved. The page list is
discovered from the router, so a page mounted tomorrow is captured without anyone
editing a list. The bundle is regenerable output like `reports/` — git-ignored,
never committed — and it regenerates byte-identically:
`tests/test_page_snapshot_bundle.py` runs the generator twice and fails on any
byte that moves, which is what lets a design review diff one bundle against the
next and see only what the design changed. Regenerating means clearing the
directory first, so `--out` is **refused** unless the directory is empty or
carries the `.driftless-page-snapshots` marker the tool writes there — `--out
docs` or `--out .` can no longer glob away HTML it did not create. A
`docs/page-snapshots/` left from before that change carries no marker: delete it
once, and the tool manages it normally from then on.

```bash
.venv/bin/python bin/driftless-snapshot-pages.py --anchor 2026-07-01
```

## Static showcase

`bin/driftless-showcase.py` turns that deterministic page walk into the portable,
read-only demo published by Headless Mode. The page set is **router-derived, not
hand-maintained**: every `GET` page route the app mounts is exported unless it is
named in `EXCLUDED_ROUTES`, a short table of `{route: reason}` (currently only
`/login`, whose form is dropped from the bundle entirely). A route's path
parameter is filled from every id/slug the demo seed or a frozen catalog offers
(so the whole PMBOK/technique/artifact/method reference library ships), except
the deep single-project flow/RAID/assist walkthrough and one department's assist
workspace, which stay pinned to the row the demo's story is told through, and the
three project pages the dashboard itself links to (`hub`, `status`, `wizard`),
which ship for every project a dashboard reader can click to. A test
(`tests/test_showcase_route_coverage.py`) fails whenever a newly mounted page
route is neither exported nor named in `EXCLUDED_ROUTES`, so the hand-written
list this replaced cannot silently drift out of sync with the router again. It
removes every script, sign-in and form, and rewrites links between captured pages
**extensionless** (`href="page"`, `./` for the index) — the file on disk still ends
in `.html`, but Cloudflare Pages 308s a `.html` request to the extensionless path,
so the emitted link answers in one hop instead of round-tripping through the
redirect. `driftless.css` and `map.css` ship once each as sibling files, the same
way `bin/showcase-map.js` does, with every page's `<link rel="stylesheet">`
rewritten to point at them, instead of inlining a copy into a `<style>` block on
every page. It adds a fixed fictional-data/as-of banner that links back to
`headlessmode.com/driftless` (override with `--site-url`) and `noindex`, and writes
`manifest.json` with the source version, the complete file list, the page count,
the sibling script and stylesheet lists, and a `sha256` map of every shipped
file's bytes. Every export replaces the whole destination directory, clearing any
file a prior run left behind (not only `*.html`), so a renamed or dropped asset
never survives as an orphan. `--source` defaults to the checkout's short commit
SHA, or to `v<version>` only when HEAD carries that exact release tag; the command
prints which one it chose.
Read-only means the bundle cannot write, not that it cannot be explored. Exactly one
script is re-admitted, on the two map pages alone: `bin/showcase-map.js`, shipped into the
bundle as a relative file (the deployment's CSP allows `'self'` scripts but no inline
one) and listed in `manifest.json`. It lights a node's name and its ties on hover,
keyboard focus and click, and opens that node's summary, reading only the markup already
rendered — no network request, no storage, no form, nothing that writes. Its bytes are
pinned by a sha256 in `tests/test_showcase_demo.py`, which also proves no other script
survives anywhere in the bundle; regenerate that hash deliberately, never to make a run
pass. Both map pages still read correctly with the file absent, and the map's copy is
rewritten on export so it promises only what a static bundle delivers — no filter strip,
and no link to a project wash, which stays a read of the live product. The whole-graph
read does not: `?view=all` ships as `map-all.html`, captured under a name of its own
because `snapshot_name` drops the query, so both reads of `/map` would otherwise be the
same file. Every `?focus=` link — "See it on the map" from a process, technique or
artifact page, and the two per node on the map pages themselves — is rewritten to
`map-all#node-<node id>` instead of flattening to the process overview, which draws no
technique and no artifact at all and pins nothing. The anchor is that node's own entry in
the lists under the drawing, and the export opens those lists, so the link lands on
something a reader with no JavaScript can see; `showcase-map.js` lights the shape and its
ties as well when it runs. Every shape still links onward to its own
process/technique/artifact page, since every one of those ships in the export too.
The destination must be empty or already carry a `manifest.json` with `"kind":
"driftless-static-showcase"`, because regeneration replaces the whole bundle.

The exported `index.html` opens with a short intro naming the fixed demo (the seeded
project count, measured off the bundle's own hub pages, and the one project the deep
walkthrough is told through) and links into the Method pages. Any page a reader can
reach whose links include one the export could not carry (`.showcase-unavailable`)
gets one explanatory sentence saying so, generated once per page rather than once per
inert link.

```bash
.venv/bin/python bin/driftless-showcase.py \
  --out ../site-headlessmode/static/demo/driftless \
  --anchor 2026-07-01 --source "$(git rev-parse --short HEAD)"
```

The demo remains generated output: change Driftless first, regenerate it, then commit
the refreshed bundle in the site repository. Never edit a generated page by hand.
Both snapshot commands enter the app lifespan against their throwaway store, so the
startup schema guard cannot reach or wait on a deployment database during generation.

## Performance floor

The release gate on page performance is a **statement count, never a wall-clock
budget**. How many SQL statements a page issues is a property of the code;
milliseconds are a property of whichever machine ran the suite — and in-process
SQLite hides the per-statement round trip a networked Postgres charges, so a
green stopwatch there proves nothing about production.

The floor is therefore *invariance in the row count*: the same page rendered
over a commercial-volume store (5 portfolios, 6 projects, 300 tasks, 300
baseline lines, 60 risks) must issue **exactly** the number of statements it
issues over a store a tenth the size. Both stores share one topology and one set
of aggregate signals — only the row counts differ — so the expected difference
is zero and any extra statement is a per-row query, i.e. an N+1. The measured
counts are deliberately **not** restated here: one moves whenever an honest read
lands, so a number retyped into prose is stale within the week — this paragraph
claimed counts several times the ceilings CI was enforcing. The ceilings are
stated, because a ceiling is a decision rather than a reading, and each is
derived from a measurement the suite re-takes on every run: `/` 168,
`/process-map` 29, `/threats` 62
(`MAX_HOME_STMTS`, `MAX_BUSINESS_MAP_STMTS`, `MAX_THREATS_STMTS` in
`tests/test_perf_commercial_volume.py`). `tests/test_docs_numbers_are_measured.py`
reads those three constants and checks this sentence against them, so moving a
ceiling edits this line in the same commit. A regression that inflates both
volumes equally still fails, and each page must render seeded content (not an
empty state) to count. Cost per *project* is a different, bounded thing with its
own ceilings in `tests/test_perf_n1.py`.

```bash
.venv/bin/python -m pytest tests/test_perf_commercial_volume.py tests/test_perf_n1.py
```

## Accessibility floor

Every rendered page is usable by keyboard and screen reader: one `<h1>` and a
`lang`, a skip link ahead of the nav with a focus ring nothing removes,
`aria-current` on the active nav link — or on the destination the current page
sits under, so a nested page still says where it is — a name a screen reader can
read on every nav group, a programmatic name on every control (a
placeholder is not a label), `<th scope>` plus a caption on every data table, and
status never on colour alone. `tests/test_web_a11y.py` enforces both halves: it
*computes* the WCAG contrast ratio of every text token pair in `static/driftless.css`,
light set and dark, and walks every GET page the app registers — so a page added
later is checked the day it is mounted, and a token with no dark twin fails.

A walk is worth only what it renders, so the fixture behind it is asserted
non-empty: every page it requests must come back with seeded content, and the
pages empty **by design** are pinned as an exact set (`EMPTY_BY_DESIGN`,
currently empty), so a page that quietly goes blank fails rather than passes.
`/org/heatmap` and `/search` were being walked on their empty states — nobody
assigned an hour-estimated task, and no search term — which left every rule both
walks apply passing on markup that held nothing; the fixture now assigns the
seeded task in hours to a person with capacity and carries a matching `q` on
every request. The weekly-status trend was the quietest case of the same hole and
invisible to that assertion: its empty branch carried no `empty-state` class, so the
page never read as blank while the chart's own markup — line, axis ends, table twin —
had never been walked once. The fixture seeds two dated snapshots a quarter apart, so
it is. `tests/test_web_responsive.py` walks the same pages through the
same helper, so every wrapped table it finds is covered by the same assertion. The number
of them is not written down here, for the reason the performance floor gives above: it moves
whenever a table is added, and a count retyped into prose is stale by the next page.

That ratio gate is **total**, because the palette is closed. The two `:root`
blocks in `static/driftless.css` are the only place a colour literal may be
written — every other template says `var(--token)`, and the gate
fails any file that spells a hex or an `rgb()`, naming the file and the literal.
A second check pairs the two: every declared token must carry a contrast floor
(4.5:1 text, 3:1 for the focus ring and for a chart line the legend names) or sit
in an explicit `DECORATIVE` list. So a colour cannot reach a page without a
computed ratio, and cannot be tokenised out of the gate's reach either. This
closed two defects page-local hexes had hidden: chart labels and the PV line at
3.54:1 in light mode, and tile labels at 3.18:1 in dark mode — both page-local
colours with no dark twin.

The stylesheet owns the shared *shape* on the same terms it owns the palette:
layout (`tests/test_web_responsive.py` fails a page-local `<style>` declaring
`display:flex/grid`, `flex`, `overflow` or a `min-`/`max-width`) and, since that
gate reaches containment only, the rollup table's alignment and indents as
`.rollup`. The dashboard and the portfolio/program drill render the same rollup,
so they apply that one class rather than keeping a copy of the rules each — the
drill page now carries no `<style>` at all.

## Responsive floor

The surface holds together down to a tablet on **one** width breakpoint —
`@media (max-width: 60rem)`, 960px, declared once in `static/driftless.css` and argued
there. That width was measured off the dashboard's own content rather than
picked off a device list: the command split is 36rem of heatmap + 18rem of rail
+ a 1.5rem gap = 55.5rem, which stops fitting inside the 2rem body gutters at
59.5rem of viewport, so 60rem is where the desktop reading genuinely ends. A
landscape tablet (1024px) still gets the two-column desktop layout; a portrait
one (768px) gets the wrapped layout, with the gutters narrowed and reclaimed for
content. A second breakpoint would need its own argument; the test pins there
being one.

Below it every wide surface has an answer, and **none of them is hiding
something**. A table too wide for the viewport scrolls sideways instead of
clipping (`.scroll-x` — a table narrower than the box still fills it, so the
desktop rendering is untouched, while a wider one keeps readable columns and
moves). The flex rows wrap rather than clip: board columns break to the next
line, a card still reading at 12rem, and so do the KPI tiles, the chart pair and
the command split. The inline-SVG charts scale on their `viewBox`, and their
figures stay text at any width — the Gantt repeats every bar and mark as a row
of the table beneath it, the curves print their own end figures. Dropping a
column is how someone ends up deciding without the number that mattered, so no
width drops one.

A scroll box is written one way and one way only — `_scroll.html`'s
`wide(label)` macro — so it always carries `tabindex="0"` (a keyboard can scroll
it) and a named `role="region"` (a reader announces both that it scrolls and
which surface it holds). Mouse-only is not something review has to catch,
because it cannot be written.

**What the tests prove is structure, not appearance.**
`tests/test_web_responsive.py` walks every GET page the app registers for the
viewport meta tag (without it a tablet renders at a lied-about ~980px and every
breakpoint below is inert) and for every `<table>` sitting in a scroll container
that takes focus and carries a name; statically, it pins exactly one width
breakpoint and no page-local re-declaration of a layout property. No test here
renders a viewport, so column widths, where the flex rows choose to wrap,
whether a scrolled table reads well under a thumb, and whether the Gantt's bars
stay legible once the SVG scales are **eye checks nothing covers**.

## Sample reports

`docs/samples/` holds real generated documents, so deciding whether this is worth
installing does not require installing it. They come from the shipped demo store —
fictional businesses, projects and people built by `driftless/demo/data.py` from a
fixed anchor by fixed offsets, with no wall clock and no randomness anywhere in the
payload — rendered by `driftless report all` at that anchor as the as-of.

```bash
.venv/bin/python bin/driftless-sample-reports.py --out docs/samples --anchor 2026-07-01
```

Committed generated output normally rots, which is why `reports/` and
`docs/page-snapshots/` are git-ignored instead. These do not, because the Tests job
reruns that command on every pull request and diffs every tracked sample byte for
byte: a template or figure change refreshes the bundle in the same change or the run
goes red. `report all` renders the whole store, so a local run writes every document
for every project while only some are tracked so far — the rest land a project at a
time, and the gate picks each up as it is committed. Stage the samples deliberately
rather than with `git add -A`.

`method-map.svg` lands in the same bundle, lifted out of `GET /map`. It is selected by
its `aria-label` rather than by being the first `<svg>` on the page: the legend draws a
swatch per shape and per knowledge area above the graph, so the positional read committed
a 153-byte chip for as long as the file existed, and the drift gate stayed green over it
the whole time. That is the limit of a gate built this way — rerunning the generator and
diffing the bytes proves the generator is *deterministic*, never that it captured the
right thing, so a stable wrong answer reads exactly like a right one.
`tests/test_sample_reports_method_map.py` asks the question the gate structurally cannot,
of both the generated and the committed file: does it carry the graph's own label and
viewBox, and a node for at least every process in the catalog — properties no legend chip
can hold.

The same limit applies to every other file in the bundle: rerunning the generator and
diffing the bytes proves it is deterministic, never that a report says anything. A
generator that started emitting a one-line stub for every document would be green the
moment the stub was committed. `tests/test_sample_content.py` covers the rest of the
bundle — each committed markdown report, keyed by report type, against the headings it
actually renders and a minimum size read off the current file with a margin (so a small
future edit does not itself become a drift failure), plus a structural floor on
`method-map.svg`'s element counts.

## Technique coverage

The technique library is held total the same way the walks above are held total: by walking
the population rather than sampling it. `tests/test_technique_totality.py` reads every
`TT_CATALOG` member out of the live registry and fails on the first one missing any
explanation field — and the field list is derived from `TechniqueContent`'s own dataclass
fields, so a field added to the record is demanded of every technique the moment it exists,
with no second list to keep in step.

The clause citation is the one field a technique may honestly lack, so it has its own
**self-invalidating exemption set**: `driftless/pmbok/reasons.py:UNCITED_EXEMPTIONS`
maps each uncited technique to the reason PMBOK-6 gives it no numbered clause. The reasons
are not all alike and this page does not restate them — the dict is where each one is
written, beside the technique it excuses, so there is no second list here to fall behind it
the way an enumeration in prose always does. The set is asserted
**exactly equal** to the uncited set, so it fails in both directions: a technique that ships
uncited without an entry, and an entry that stays behind after its technique gains a
citation. An exemption cannot outlive the gap it covers, which is what stops the list
becoming the hand-maintained allowlist that every such list turns into. A citation that is
present must also look like a clause reference, so an exemption can never be dodged with a
plausible-looking sentence in the field.

Leaving a citation blank is a decision, not an omission: an invented clause number is worse
than a missing one, because a reader cannot tell it from a real one. `docs/user-guide.md`
says so on the surface where a reader meets it.

```bash
.venv/bin/python -m pytest tests/test_technique_totality.py tests/test_technique_definitions.py
```

## Knowledge-area end-to-end walk

`tests/test_e2e_knowledge_areas.py` parametrizes over every `KnowledgeArea` crossed with
every `Project.delivery_mode` (predictive, agile, hybrid), plus one department. Each walk
seeds its own project through the public surfaces only — the API resource registry over a
`TestClient`, and the wizard's own `driftless.services.wizard_writes.produce` — never
`session.add`: it files the area's producible inputs in lifecycle-group order, opens the
assistant page(s) `assess.model.ASSISTANT_ROUTES` routes its techniques to, records one
`TechniqueRun` (`driftless.services.technique_runs.record_run` — no page yet POSTs one, so
this is the write path's own boundary, exercised directly), and — for Scope and Schedule,
the two areas whose baseline-shaped output resolves through the project's one `Baseline`
row — raises a `ChangeRequest` and approves it through the draft-then-PATCH boundary that
produces a new version.

Every process in the area is then read back three ways that must agree — the computed
state (`pmbok.state.process_state`), the `/pmbok/{id}?project=` drill page, and the
business-wide rollup cell (`pmbok.rollup.business_process_cells`) — one state rule seen
from three surfaces, cross-checked again against the figures the Process Map and
Assessment report documents render. A process the wizard can fully produce must read
PRODUCED or SIGNED_OFF; one with no producer of its own (a "derived" process — every
catalog process today is one or the other, never a bare unassessable "reference" step,
which the suite's own sanity test pins) shows whatever the store honestly computes, never
a forced PRODUCED. Risk and Schedule additionally round-trip their producible rows through
`bin/driftless-import.py`'s CSV import — the only two areas whose wizard-produced kind is
also one of the importer's four. Each walk closes by proving the as-of read is not
decorative: the day before its last write reads a different process state than the day of.

```bash
.venv/bin/python -m pytest tests/test_e2e_knowledge_areas.py
## Assistant totality

Every routed technique gets a runnable assistant page eventually, and every one of
those pages owes the same six gates. `tests/test_assistants_totality.py` derives the
assistant set rather than naming it: `assess.model.ASSISTANT_ROUTES`' route templates
are compared against every GET the app mounts under `/assist/`, so a technique promised
a launcher with no router included, or a page mounted with no technique's route naming
it, fails the moment it happens. `tests/test_launcher_totality.py` carries the mirror
check against the live app's own route table.

For every page the two sides agree on: it renders real content under the shared seeded
fixture, never only an empty state; it is deterministic (two same-as-of renders are
byte-identical, and an earlier as-of never shows a fact the store dates after it — proven
by actually injecting a later-dated row, so the check cannot pass on nothing); its
statement count sits under a ceiling derived from a live measurement, the same
`MEASURED`/`assert_recorded` convention the [performance floor](#performance-floor)
carries; every `<svg>` its template draws carries a print/no-JS text alternative; a
viewer reads it and only a contributor or admin could write it (`test_web_csrf`'s gated
app); and any row kind it can write round-trips through the CSV export and
`bin/driftless-import.py`. No routed assistant draws a chart or writes a row today, so
the last two gates hold on an empty walk — wired against the live template and route
registries rather than pinned to that fact, so the day one changes, the walk includes it
with no edit to this test.

```bash
.venv/bin/python -m pytest tests/test_assistants_totality.py tests/test_launcher_totality.py
```

## Plain-language gate

`driftless/pmbok/plain_language.py` holds one rule for a registry's reader-facing summary
sentence (`ARTIFACTS.plain_summary`, `PROCESS_DEFINITIONS.plain_summary`, `TECHNIQUES.summary`):
exactly one sentence, at most 25 words, no raw snake_case identifier, no acronym at all — even a
glossary-defined one. `tests/test_artifact_totality.py`, `tests/test_process_totality.py`, and
`tests/test_technique_totality.py` all call it rather than each restating a private regex. A
technique's other explanation fields (`when_to_use`, `steps`, `worked_example`, ...) stay fuller
prose and may keep the technique's own terms of art and acronyms, but every technique field is
still checked for a leaked identifier.

## The totality proof

Every totality suite above answers one narrow question — is every technique explained, is every
artifact kind explained, does every `TT_CATALOG`/`ARTIFACT_KINDS` member connect to a process or
carry a documented exemption, is every technique launchable or excused, does every Scrum/Kanban
practice crosswalk to PMBOK or say why it cannot, does every Monitoring & Controlling process
appear in every tailoring profile. `driftless/pmbok/proof.py` does not re-derive any of those
rules — it reads the same live registries each one already reads
(`tt.py`, `artifacts.py`, `mapping.UNTRACKED_DISPOSITIONS`, `reasons.GUIDE_ONLY_REASONS` /
`UNTRACKED_REASONS`, `methods.METHODS`, `crosswalk.EQUIVALENCES` / `NAMED_MODELS` /
`NO_EQUIVALENCE`, `tailoring.PROFILES`, `assess.model.ASSISTANT_ROUTES`,
`wizard.cli.producible_kinds`) — and reports them together as one `Proof`, so THE closure
evidence for §4 of the plan is one command:

```bash
driftless pmbok proof
```

which prints `Everything is accounted for.` when every named count — orphan, unexplained,
unlaunchable, uncrosswalked, skipped — is zero, or the offending members under whichever count
is not. `GET /pmbok/proof` renders the same `Proof` as a page. `tests/test_totality_proof.py`
asserts every count is zero on this tree and is the one place a future gap in any of the
underlying registries surfaces as a single, named failure rather than eight separately-run
suites. It also holds the reader-facing wording closed over the counts: `proof.GAP_SHAPES` is
pinned field by field to `Proof`, so a thirteenth count reaches neither the page nor the command
until someone words what it checks.

`Proof.skipped_processes` is the fifth count, and it is asserted EMPTY exactly like the other
four: every catalog process now resolves to a `form`, `derived` or `reference`
`WizardStep.kind` (`wizard.engine.next_step` no longer treats "nothing producible" as a dead end
to skip), so the only process `next_step` could still pass over entirely is one the store cannot
judge at all — `not state.is_assessable(process)` — a static, store-free fact this module reads
without a session. `tests/test_totality_proof.py` proves that against a real store too, by
importing `tests/test_wizard_totality.py`'s own lifecycle-order/waive strategy rather than
copying it, so the two suites cannot silently name two different orders or two different
meanings of "waived".

```bash
.venv/bin/python -m pytest tests/test_totality_proof.py
```
## Launcher and totality gates

Support is asserted as a **total, partitioned set**, never sampled: `tests/test_launcher_totality.py`
walks the whole `TT_CATALOG` and asserts every technique is either named in
`assess.model.ASSISTANT_ROUTES` (it launches) or in `driftless/pmbok/reasons.py:GUIDE_ONLY_REASONS`
(it explains why not) — the two partition the catalog exactly, so a technique cannot sit in
neither (an assistant nobody built and nobody explained) or in both (a route that never got
promoted out of guide-only). The same shape runs over `ARTIFACT_KINDS` against
`wizard.cli.producible_kinds()` and `UNTRACKED_REASONS`. `tests/test_wizard_totality.py` proves
the companion property for the wizard itself: waiving every process ahead of one in lifecycle
order and asking `next_step` for the next one lands on exactly that process, whatever kind of
step it turns out to be — a process is never silently skipped as a dead end. `driftless pmbok
support` prints the same coverage as a live count over the whole catalog, so "how much of this
does the product help with" is a command anyone can run rather than a number retyped into a
document, which is why none of the totals are restated here.

## Propagation manifest

A native write is not "done" once its own model validates — the same fact has to reach
process state, the rollups, the report documents, the assessment engine and the export/import
surface, or one of those five families is now silently stale. `driftless/pmbok/consumers.py:CONSUMERS`
names which families a given change kind is expected to reach; `tests/test_propagation_manifest.py`
drives a real change of each kind and asserts every named family actually differs afterwards —
or, if it structurally cannot, that the kind is listed in
`driftless/pmbok/consumers.py:UNAFFECTED_BY_CHANGE` with the reason. A family missing from both is what the test catches: a consumer nobody thought
to check, rather than a silent gap nothing notices.

## Hybrid tailoring

Which controls read against a fixed plan and which read against the team's own current
commitment is a property of the project's delivery mode, not a per-page decision, so it is
pinned the same total way: `tests/test_pmbok_tailoring.py` asserts every Monitoring &
Controlling process is mapped in every one of the three profiles (`driftless/pmbok/tailoring.py:PROFILES`)
exactly once, and that the one change-and-approval boundary — `ChangeRequest` → `Baseline` —
never moves off the fixed plan whatever the rest of the project's controls are tailored to.

## Executable docs

`docs/user-guide.md`, `docs/agent-guide.md` and `docs/admin-guide.md` are not written and then
left to rot: `tests/test_docs_user_guide.py`, `tests/test_docs_agent_guide.py` and
`tests/test_docs_admin_guide.py` each open every fenced `driftless:run` block in order, against
a real app and a throwaway store, and fail the moment a screen, a status code or a printed
value stops matching what the prose says it is. An unmarked fence fails too, so no example can
sit in a guide undescribed and unexecuted. This is the same end-to-end shape `tests/test_auth_end_to_end.py`
uses for the sign-in seam — walking the real surface in order catches what no single unit's
test can, because the defect lives in how two things compose rather than in either alone.
