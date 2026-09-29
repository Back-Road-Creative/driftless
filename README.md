# svc-driftless

## Purpose

Business, portfolio, program and project management for Back Road Creative —
built so information is entered **once** and everything else is computed.

There is a single normalized store. Dashboards, rollups and generated
documents are *queries over it*, never stored copies, so they cannot drift out
of step with each other. If a "reconciliation" or "sync check" job ever looks
necessary, the schema is wrong — fix the schema instead.

Two consequences worth knowing before you add anything:

- **Generated documents are never hand-edited.** Any report can be deleted and
  regenerated identically from live data. Human narrative is a first-class
  field on the record (e.g. a project's `status_note`), so it survives
  regeneration.
- **Every report takes an explicit as-of date.** Templates never read the wall
  clock; that is what makes "generate twice, get byte-identical output" a
  property we can test.

## Owner

@joepetjr — see `LIFECYCLE.md` for the service state declaration and review date.

## Status

Driftless is in service and feature-complete against its own scope: the full
hierarchy, delivery records, an append-only audit trail, RAID and money
records, the org/sign-off/quality/procurement layer, one validated API write
path over the whole store, a server-rendered dashboard, the PMBOK ITTO catalog
and assessment engine, an onboarding wizard, and a deterministic demo store.

**[`docs/architecture.md`](docs/architecture.md) is the inventory** — every
part, and the invariant each one holds. `CHANGELOG.md` plus the fragments in
`changelog.d/` are the record of what actually shipped.

## Users and roles

Logins live in `app_user` (`driftless/models/auth.py`), apart from `person`: a
user is a credential, not a resource. After `alembic upgrade head`:

```bash
printf '%s' "$ADMIN_PW" | driftless user add --username jp --role admin
driftless user list   # username, role, state, created — never the digest
driftless user disable jp   # deactivate AND revoke every cookie already issued
driftless user enable  jp   # reactivate; the cookies disable revoked stay revoked
printf '%s' "$NEW_PW"  | driftless user passwd jp   # rotate AND revoke every cookie the old one issued
```

Roles are `admin`, `contributor`, `viewer`; passwords are stdlib-scrypt digests
read from stdin, never argv (`driftless/auth/passwords.py`). One shorter than **12
characters is refused** before it is hashed or stored (`MIN_PASSWORD_LENGTH`,
`driftless/auth/cli.py`) — lower than the 24 `deploy/entrypoint.sh` demands of a
machine secret, because a person has to remember this one, but not absent: scrypt
only buys time against a stolen digest, and a password short enough to guess is
guessed before the KDF costs anyone anything. `disable` clears
`is_active` **and** increments `app_user.session_epoch`, the counter every cookie
carries a copy of; bumping it is what revokes a session nothing stores (details in
`OPERATIONS.md`, *Revoking a session*). `enable` never lowers it back. `passwd`
bumps the same counter for the same reason — a rotated password is a revocation,
or every cookie the old one issued would keep resolving.

`/login` remembers a user in an HMAC-signed `HttpOnly`, `SameSite=Lax`, `Secure`
cookie (`driftless/auth/sessions.py`) stamped with that epoch, so a revoked cookie
stops resolving without waiting to expire; the form is CSRF-bound and every refusal
reads the same. `DRIFTLESS_SESSION_SECRET` signs it — **unset means nobody can sign
in**, and it warns: unlike `DRIFTLESS_API_TOKEN` (open when unset) this one grants
identity, so falling open would mean forgeable logins. `DRIFTLESS_COOKIE_SECURE=0`
develops over plain HTTP. Five failures for one username from one client inside 15
minutes are answered `429` for the rest of that window (an in-process counter, no
new dependency; a correct password clears it) — keyed on both halves so no one can
lock a colleague out, and counted for absent usernames too so the `429` never
reveals that a login exists. A second cap counts every failure from one client
**whatever username it named**, so cycling usernames no longer buys a fresh five
each time. `POST /logout` **revokes as well**: it bumps the epoch,
so signing out ends the session on every device, not just this browser.

A signed-out browser is **sent to that form**: the gate answers `303 /login` when a
request presented no credential at all *and* its address is one of the app's page
routes. Everything else keeps `401 {"detail":"missing or invalid bearer token"}` byte
for byte — the JSON API, `/health/ready`, and every request that *did* present
something and was rejected (a wrong token, a forged cookie, a cookie `user disable`
revoked), because a form cannot fix a bad credential and a disabled account redirected
to one would loop. Ordinary expiry still lands on the form: the cookie's `max-age` is
the session TTL, so the browser has dropped it before the signature goes stale. The
target is the fixed string `/login` — no `?next=`, which would be an open redirect.

**API tokens** are the non-browser half of the same identity — one per user, per holder,
so an agent's writes carry a name rather than the shared `DRIFTLESS_API_TOKEN`'s anonymity:

```bash
driftless token add --username jp --label ci  # printed ONCE, to stdout alone
driftless token add --username jp --label laptop --expires-in-days 90  # optional deadline
driftless token list      # id, user, label, live/revoked/expired, created, expiry — never the digest
driftless token revoke 3  # by the id `list` prints
```

`user add` first — a token belongs to a login. Only a SHA-256 digest is stored
(`api_token`, `driftless/auth/tokens.py`), so a lost token is re-minted, never
recovered; not scrypt, because 256 bits of `secrets` randomness needs no slow KDF.
A token minted with no `--expires-in-days` never expires, which is also what every
token minted before that flag existed keeps meaning. Both revocation and expiry bite
the same way — `tokens.resolve` answers `None` for either, so a caller cannot tell
them apart — and `user disable` stops every token its owner holds too, because
resolving reads the owner's row back. Only `token list` shows an operator which of
the three a given token is. Present it as
`Authorization: Bearer dfl_…`: the gate resolves it to the **same** `Principal` a cookie
yields, so the role table below and the per-user audit actor apply to it unchanged.

**What a role may do** is enforced in exactly one place — `TokenGate` in
`driftless/api/secure.py`, not per route, so a write route added later is gated
whether or not anyone remembers to ask:

| Role | Reads (`GET`, `HEAD`, `OPTIONS`) | Ordinary writes | The sign-off ledger (`POST /api/v1/sign-offs`, `POST /sign-off`) |
|---|---|---|---|
| `admin` | yes | yes | yes |
| `contributor` | yes | yes | **403** — a sign-off is a governance act, not an edit |
| `viewer` | yes — every surface | **403 before the route runs**, so no row is ever written | same 403 as any other write |

The floor is by method, never by path, and a method outside the read set counts as a
write: unknown fails closed. `secure._PRIVILEGED_PATHS` narrows that floor further for
the two addresses above — both append the SAME row through one service rather than
assembling their own (`driftless/services/sign_offs.py:create_sign_off`), so
gating only the JSON route would leave the form open. The role check runs **after**
`/health`, `/static…`, `/login` and `/logout` are decided, so a viewer can always sign
in, sign out and load the CSS. A request carrying only the shared `DRIFTLESS_API_TOKEN`
resolves no user and is therefore *not* role-gated — that token is the bootstrap/admin
credential, so it carries the sign-off tier too. A signed-in viewer is refused even
with no token configured; no credential and no token stays open, as in development
today. `tests/test_secure.py` pins the method set, the sign-off path set as an exact
match against the live route table, and that ordering.

Every web form POST is CSRF-bound the same way, minted and checked in one place
(`driftless/web/csrf.py`): a random token into a hidden `csrf_token` field and into
the `driftless_csrf` cookie, both required back, compared constant-time. It covers
`POST /sign-off`, `POST /projects/{id}/wizard/apply` and `POST /projects/{id}/status`
— unpaired is refused **403 before any read or write** — and the token is reused
from the cookie the browser holds, so two tabs never invalidate each other. **Signing
out is bound too**, because it revokes every device — and no router has to remember: all
seven render through the one `Jinja2Templates` in `driftless/web/templating.py`, whose
context processor puts the token in every context and whose `TemplateResponse` attaches
the cookie half, so the sign-out form in every nav carries a pair. That one environment
is also **strict** (`undefined=StrictUndefined`, the same setting `report/engine.py`
carries): a name no route passed — a misspelt `{{ as_off }}`, a field only an
empty-state branch mentions — raises at render time instead of printing the empty
string, so a figure cannot quietly leave a page while the page still answers 200.
A body not matching the cookie half is a forgery on a live pair: **403
before the store**; a POST carrying no `driftless_csrf` cookie was never handed a pair
and gets only the half that grants an attacker nothing — its own cookie dropped, **no
epoch bump**. `tests/test_web_csrf.py` walks the real app, so a POST with no check, a
form with no field, or a page rendering no token, fails there.

The pair is required **only where forgery is possible**: a cookie is *ambient* — a browser
attaches it to whatever another origin causes — while a bearer token is attached
deliberately and no cross-origin page can make a browser send one. So the gate stamps which
credential authenticated the request, and `POST /projects/{id}/wizard/apply` skips the pair
for a bearer one. That is what lets an agent drive the wizard loop end to end
(`docs/agent-guide.md`); the other two form POSTs already have JSON API routes
(`/sign-offs`, `/status-snapshots`) and keep the pair either way. A cookie **wins when both
arrive**, so a browser that also sends a header still pairs — otherwise one added header
would bypass CSRF — and role gating is untouched: a viewer's token is refused the write.

## Releases

`CHANGELOG.md` is the record of what shipped, in Keep-a-Changelog shape. Every
user-visible change ships its entry **in the same PR** as the change — never
"later", because an entry written from memory is written wrong — but as a
fragment file `changelog.d/<PR#>.<type>.md` (see `changelog.d/README.md`), never
as a direct edit to `CHANGELOG.md`, so two open PRs cannot collide on the same
changelog lines. At release time `bin/assemble-changelog.py --release <version>`
folds the fragments into `CHANGELOG.md` under the new version heading and
deletes them. That is the whole of what the tool does: the version it stamps is
read off the argument, so `pyproject.toml` and `driftless/__init__.py` are the
files that decide it and are bumped by hand before the fold. Once the fold has
merged, tag the merge commit `v<version>` — the changelog says what shipped and
the tag says which commit it shipped from, and a release with only one of the two
cannot be checked out. Pushing that tag is also what publishes the release:
`.github/workflows/release.yml` reads the dated section for that version out of
`CHANGELOG.md` and creates the GitHub release from it, failing without publishing
anything if there is no such section. `OPERATIONS.md` covers upgrading a running
deployment (back up, pull, rebuild; the container migrates before it serves) and
the request log.

**What a release provides.** Notes always; a pullable container image only once
a tag exists on the **public** repository — `.github/workflows/docker-publish.yml`
builds that tag's own tree and pushes `ghcr.io/back-road-creative/driftless:<version>`
alongside `:latest` when that version is the newest one published, so a public tag is what turns "pull it" into a true
sentence. As of this writing `Back-Road-Creative/driftless` has no tags, no
releases and no `ghcr.io/back-road-creative/driftless` package — that step has
never run. Which versions exist is the Releases page of
`Back-Road-Creative/driftless` and that organisation's Packages tab, never a
sentence here: a tag is what would make such a sentence wrong, and a tag is the
one event this file ships inside. Pulling is not the same route as deploying,
either — `docker-compose.yml` gives `driftless-app` a `build:` and no `image:`,
so `docker compose up -d --build` builds from the checkout, and pointing it at
a published image is the step after this one. A release is cut per
`docs/release-publishing.md`: development history stays in a private archive and
the tag, the release object and the image are all made on the public repository.

## Exit Condition

This service is retired when Back Road Creative no longer runs its portfolio,
program and project management from it — either because the business stops
needing centralized PM, or because the store is migrated to a replacement that
takes over the same single-source-of-truth role. Until then it stays ACTIVE;
there is no fixed end date.

## Layout

| Path | What lives there |
|---|---|
| `driftless/` | The service package |
| `driftless/cli.py` | The `driftless` command — dispatches `report`, `pmbok`, `assess`, `wizard`, `demo` and `import`, each registered by its own domain |
| `driftless/interchange/` | `driftless import msproject <file.xml> --project P` and `driftless import xer <file.xer> --project P` — bring a Microsoft Project XML (MSPDI) or Primavera P6 XER schedule's tasks and dependencies into a new workstream, through the same validated write path (`api.schemas` + `api.records.insert`) the API uses; `driftless import viva-goals <file.csv> --project P [--dry-run]` brings a Viva Goals (retired 2025-12-31) OKR CSV export's objectives and key results into the project's business scorecard, same write path; `driftless export msproject --project P [--as-of D]` writes the approved baseline back out as MSPDI XML to stdout, round-tripping through the same importer |
| `driftless/api/` | FastAPI app and the Pydantic schemas that validate every write |
| `driftless/demo/` | `driftless demo seed` — a deterministic demo store through the validated API |
| `driftless/calc/` | Pure calculation core — EVM, rollups, forecasts, schedule network (`network.py`, including `network_disagreements`, which flags a baseline whose stored dates fall outside its own network's window). No I/O. |
| `driftless/db/` | Declarative base, engines, sessions, SQLite FK pragma, and the ChangeLog audit trail (`changelog.py`) |
| `driftless/models/` | ORM models — `hierarchy.py` (business → … → task), `delivery.py` (baselines, milestones, sprints), `records.py` (RAID + cost), `people.py` (departments, people), `governance.py` (`sign_off`), and `narrative.py` / `quality.py` / `procurement.py` |
| `driftless/web/` | Server-rendered dashboard — a router plus Jinja2 templates. Every server-rendered chart (the dashboard's business-wide S-curve, the cost workbench's cash-flow S-curve, the portfolio treemap, each project row's burn sparkline) draws through the one shared `templates/_chart.html` partial: S-curves scale to their column at a fixed 16:7 aspect with gridlines and x/y ticks, the treemap draws real area-proportional rectangles, and each chart's data table sits behind a closed-by-default `<details class="figures">` toggle rather than printed open underneath it. Each project row carries a small inline-SVG burn sparkline: cumulative actual cost `AC(t)` climbing against the flat budget `BAC`, swept in-memory from one grouped cost query (drift-free, stores nothing new), plus a **status-freshness** column showing the date of each project's most recent `StatusSnapshot` (or `never`), from one grouped max query — no N+1 |
| `docs/architecture.md` | What the service is built out of and the invariant each part holds — the capability inventory this README's `## Status` used to carry inline |
| `docs/balanced-scorecard.md` | Decision record for the non-financial scorecard lenses, configuration journey, website Scorecard view, and delivery sequence |
| `docs/temporal-model.md` | Decision record for as-of determinism, effective vs. recorded time, record classification, and the two baseline-selection breaks that block historical reproducibility |
| `docs/decisions-superseded.md` | Verdicts on four earlier in-code decisions — pagination, admin tier, HTML snapshots, no-JS pages — against what Driftless does today |
| `docs/testing-and-quality-gates.md` | Continuous integration, the page-snapshot bundle, the static showcase generator, the performance/accessibility/responsive floors, and the sample-reports bundle |
| `docs/pmbok8-crosswalk.md` | An editorial crosswalk from the catalog's 49 PMBOK 6 processes to the 40 PMBOK 8 processes, per two secondary sources — not PMI's own text |
| `tests/` | Test suite |

`driftless/calc/` is imported by both the dashboard and the report engine, which
is why a number on a screen and the same number in a document cannot disagree.

## Development

`bin/driftless-gates.sh` builds the environment and runs the gates CI runs, at
the versions CI runs them at — it reads every pin out of `.github/workflows/`
rather than restating one, so a bump in CI is a bump here with no second edit:

```bash
bin/driftless-gates.sh                # the default run: env, then every stage below
                                      #   except --browser, plus pip-audit
bin/driftless-gates.sh --quality      # ruff + ruff-format + detect-secrets + mypy
bin/driftless-gates.sh --tests        # the suite, at the coverage floor pyproject sets
bin/driftless-gates.sh --samples      # sample-report drift
bin/driftless-gates.sh --migrations   # the Postgres-16 job; starts the container itself
bin/driftless-gates.sh --docker-build # `docker build`, nothing pushed
bin/driftless-gates.sh --browser      # opt-in: Chromium renders five pages (see below)
bin/driftless-gates.sh --audit        # force pip-audit on beside a named stage
bin/driftless-gates.sh --no-audit     # skip pip-audit on a run that would include it
bin/driftless-gates.sh --no-env       # reuse .venv as it stands
bin/driftless-gates.sh --print-pins   # the versions it read
bin/driftless-gates.sh --help         # the script's own usage header
```

A plain run is the whole thing: `--quality`, `--tests`, `--samples`,
`--migrations` and `--docker-build` all run, and pip-audit runs with them, so
what a merge is graded on is what a bare invocation answers. `--migrations` and
`--docker-build` need Docker and pip-audit needs the network on every
invocation; all three fail loudly rather than skipping quietly when what they
need is missing. `--migrations` sets nothing up by hand — it starts its own
`postgres:16`, waits for it, and hands the suite the URL, so there is no
environment variable to export first.

Naming any stage narrows the run to the stages you named and leaves pip-audit
out, so a fast single-stage loop never pays its network round trip; `--audit`
and `--no-audit` override that in either direction, and `--no-audit` says out
loud that it skipped. `--browser` is the one genuinely opt-in tier: never part
of the default run, never a required check. `docs/testing-and-quality-gates.md`
carries the same account at length.

The environment is part of the gate rather than a precondition of it. A shared
interpreter drifts from `requirements.lock`, and a suite run against drifted
dependencies answers a question CI never asked, so the `env` stage rebuilds
`.venv` under the lock's constraints the way every install step in the
workflows does.

By hand, a clone builds its own venv — none is committed:

```bash
python3 -m venv .venv
.venv/bin/pip install ".[dev]"
.venv/bin/python -m pytest
```

Invoke through `python -m` rather than the console scripts in the venv's `bin/`:
a venv that has been moved or copied leaves their shebangs pointing at a path
that no longer exists and they exit 127, which reads like a missing dependency
and is not one.

Keeping the venv **outside** the checkout is a supported second setup, and the
right one wherever this repo is mounted inside a larger tree as a submodule — a
venv inside it does not survive the parent's next `submodule update --init`.
There is then no `.venv/` here to find, and every `.venv/bin/…` line in this
README reads as that interpreter's own path instead.

### Testing and quality gates

Continuous integration, the page-snapshot bundle, the static showcase
generator, the performance, accessibility and responsive floors, and the
sample-reports bundle are documented in
[`docs/testing-and-quality-gates.md`](docs/testing-and-quality-gates.md). CI's
coverage floor is `pyproject.toml`'s `[tool.pytest.ini_options] addopts` — read
`--cov-fail-under` there rather than here.
