# svc-driftless — Operations

Running the token-gated API against a hardened Postgres 16, with SOPS-managed
secrets, verified backups and a data import path. Companion to `README.md`
(which covers the application itself). Everything here lives in
`docker-compose.yml`, `deploy/` and `bin/`.

This file is the reference. `docs/admin-guide.md` is the **path** — bare host to
trusted instance, once, in order — and its commands and answers are executed by
`tests/test_docs_admin_guide.py`, so what it tells a first-time operator cannot
quietly stop being true; a step no unit test can run is marked `manual` with why.

## Security posture

- Both containers run with `no-new-privileges` and all Linux capabilities
  dropped (`cap_drop: ALL`; the database re-adds only the five it needs to
  initialise its data directory).
- Ports are published on `127.0.0.1` only — the API (`:8000`) and Postgres
  (`:55432`) are unreachable from other hosts until a reverse proxy fronts them.
- The API container is `read_only` with `tmpfs` for `/run/secrets` and `/tmp`,
  so a decrypted secret never lands on a writable layer.
- Every request must carry a credential except on the four public paths below
  (`driftless/api/secure.py`). With `DRIFTLESS_API_TOKEN` unset the server refuses
  to start at all, unless `DRIFTLESS_ALLOW_UNAUTHENTICATED=1` opts in explicitly —
  that is development mode, and it warns once so open is never quiet.

### Public paths, and what counts as a credential

With `DRIFTLESS_API_TOKEN` set, exactly these answer without a credential —
**everything else is refused**, `/` included:

- `GET /health` — the container healthcheck's probe: one `SELECT 1`, reporting only whether
  the store answered. Saying no more than that is what keeps it safe to leave uncredentialed.
- `/static` and `/static/…` — the stylesheet and script; no identity is looked up.
- `GET` / `POST /login` — a gate that hides the sign-in form can never be signed into:
  a browser would be turned away at the form — now, redirected to it in a loop — so no
  cookie could ever come into being. The form's CSRF pair, its one refusal wording and
  its rate limit are the protection — not hiding it.
- `POST /logout` — clears a cookie and redirects; with no session it grants nothing.

Matched exactly, never as a prefix, so a future `/login-admin` (or `/static-export`)
stays gated.

The refusal splits by **surface, not by `Accept`**. A request that presented *nothing*
at one of the app's page addresses answers **`303` to `/login`**, so a signed-out
browser lands on the sign-in form instead of a JSON dump at an address a person typed.
Every other address — the JSON CRUD, `/health/ready`, anything a script calls — answers
**`401 {"detail":"missing or invalid bearer token"}`**, unchanged to the byte. So does
any request that *did* present something and was rejected: a wrong token, a forged
cookie, or a cookie whose epoch `user disable` has moved past. The redirect answers "you
presented nothing", never "what you presented is no good". The target is the fixed string
`/login` and there is deliberately **no `?next=`** — a return path taken from the request
is an open redirect, and validating one properly costs more than the click it saves.

Three credential kinds satisfy the one gate:

- `Authorization: Bearer $DRIFTLESS_API_TOKEN` — the **shared bootstrap** credential:
  scripts, `bin/driftless-import.py`, curl. It names nobody, so it is not role-gated
  and its writes are audited as `actor=None`.
- `Authorization: Bearer dfl_…` — a **per-user** token (see below). It resolves to the
  same identity its owner's cookie would, so it carries their role and their name onto
  every ChangeLog row. This is what an agent or a long-running script should hold.
- the `driftless_session` cookie a browser gets from signing in — **no bearer header
  needed**, which is what keeps the web UI usable behind the gate.

A request presenting both a cookie and a bearer is answered as its **cookie**: attaching
a header can never drop a browser's identity.

`DRIFTLESS_SESSION_SECRET` **must** be set, or no cookie ever authorizes and a browser
is refused even after the right password: the cookie half fails **closed**, and so
now does the bearer half — a forgotten token stops the process rather than opening the
API, and running open takes a second variable set on purpose. The
whole walk — refused, sign in, admitted by the cookie alone, sign out, refused again —
is asserted end to end by `tests/test_auth_end_to_end.py`, because each half of it
passed its own tests while the pair was broken.

### Roles in practice

Every account carries one of three roles (`driftless user` sets it; the column
defaults to the least-privileged). **`viewer`** reads every surface — pages, reports,
JSON — and writes nothing. **`contributor`** reads the same and may create, edit and
delete. **`admin`** is contributor plus the operator's own account by convention;
nothing is admin-only today, because user management is the CLI rather than a route.

The split is by **HTTP method at the one gate**, not per route: `GET`/`HEAD`/`OPTIONS`
are reads, anything else is a write, so a write route added later is gated whether or
not anyone remembers to ask. A refused write answers `403
{"detail":"writes need the contributor or admin role"}` **before the route runs** — it
never reaches the store, so there is no partial row to clean up. Sign-in, sign-out and
`/static` are decided before the role check, so a viewer is never locked out or trapped
in a session. A whole viewer walk — sign in, read, refused, sign out — is asserted in
`tests/test_auth_end_to_end.py`.

The role travels with the **identity**, not with the kind of credential: a viewer's API
token reads every surface and is refused every write, exactly as their cookie is, and
`GET`/`POST` to `/login` and `/logout` stay reachable regardless.

A request carrying `Authorization: Bearer $DRIFTLESS_API_TOKEN` is deliberately **not**
role-gated: it is the bootstrap/admin credential, and it keeps full write access — which
is what lets `bin/driftless-import.py` load data before anyone has an account. Hand it
out accordingly; anything that should be read-only gets a per-user token (below) or a
`viewer` login, not the shared token.

### Retiring the shared credential

Once every client holds a per-user token, set `DRIFTLESS_REQUIRE_USER_AUTH=1` and remove
`DRIFTLESS_API_TOKEN` from the SOPS overlay. The gate then admits **only** a cookie or a
`dfl_…` token, so there is no longer any credential whose writes land `actor=None` — every
row names who wrote it. Mint a service account for whatever held the shared one:

```sh
echo "$A_LONG_PASSWORD" | driftless user add --username importer --role contributor \
  --db-url "$DRIFTLESS_DATABASE_URL"
driftless token add --username importer --label nightly-import \
  --db-url "$DRIFTLESS_DATABASE_URL"
```

Setting both `DRIFTLESS_REQUIRE_USER_AUTH=1` and `DRIFTLESS_API_TOKEN` is **refused** at
startup, by the entrypoint and again by the app: the two say different things about what
authorizes, and quietly honouring one would leave you wrong about which.

**One behaviour changes with it.** `POST /sign-offs` lets the shared credential supply
`signed_by` itself, because it resolves nobody — that is how a decision a named human made
offline gets recorded. A service account *does* resolve, so its `signed_by` is overwritten
with the account's own name, exactly as it is for any other identity. If you need
on-behalf-of sign-offs, keep the shared credential rather than retiring it.

## Per-user API tokens

For anything that is not bootstrapping — an agent, a cron job, a colleague's script —
mint a token against an account instead of sharing `$DRIFTLESS_API_TOKEN`. The holder
then gets that account's role, and every row they write says who wrote it:

```sh
driftless token add --username jp --label ci --db-url "$DRIFTLESS_DATABASE_URL"
driftless token add --username jp --label laptop --expires-in-days 90 \
  --db-url "$DRIFTLESS_DATABASE_URL"                            # optional: dies on its own
driftless token list --db-url "$DRIFTLESS_DATABASE_URL"        # id, user, label, state, expiry
driftless token revoke 3 --db-url "$DRIFTLESS_DATABASE_URL"    # by the id `list` prints
```

`add` prints the token — `dfl_…` — on **stdout alone** (the "store it now" reminder goes to
stderr), so it pipes safely to a secret store. Only its SHA-256 digest is stored, so this
is the **one and only** time the
plaintext exists: lose it and you mint a replacement, because nothing can recover it. The
`dfl_` prefix is there so a token leaked into a log or a repo is greppable.

Present it exactly like the shared one:

```sh
curl -fsS -H "Authorization: Bearer dfl_…" http://127.0.0.1:8000/projects
```

What the holder then does with it is walked end to end in `docs/agent-guide.md`, whose every
command and payload is executed by `tests/test_docs_agent_guide.py`, not trusted to stay true.

Four things stop a token dead: `token revoke` on that id (immediate); its own
`--expires-in-days` deadline, if it was minted with one, lapsing on its own; `driftless user
disable` on its owner (immediate, and kills **every** token they hold, as it does every
cookie); or setting the owner's role to `viewer` (immediate), which leaves reads working and
refuses writes. A caller cannot tell revocation from expiry apart — both answer the same
`401` — but `token list` shows an operator which one a given token is in.

## Email digest (SMTP)

`driftless notify digest --as-of D` emails the same attention list `/` renders
to every `EmailSubscription` due a send, as text and HTML, over stdlib
`smtplib` — no paid mail service is required or assumed. The recipient is
`User.email` when set (`driftless user email <username> --address …`); a user
with no email but an `@`-shaped username falls back to that, and a user with
neither is skipped and named in the command's output rather than silently
dropped. The relay is an operator choice, read from environment variables:

- `DRIFTLESS_SMTP_HOST` — **required**; with it unset the command refuses
  rather than silently skipping every subscriber.
- `DRIFTLESS_SMTP_PORT` — default `25`.
- `DRIFTLESS_SMTP_FROM` — default `driftless@localhost`.
- `DRIFTLESS_SMTP_STARTTLS` — `1` to upgrade the connection before sending;
  default off, which is fine for a relay on `localhost` or a private network.
- `DRIFTLESS_SMTP_USER` / `DRIFTLESS_SMTP_PASSWORD` — optional; supplied
  together, the command authenticates before sending.

The free default is a relay already on the host — local Postfix or Exim
listening on `127.0.0.1:25` — which needs none of the optional variables set.

```sh
DRIFTLESS_SMTP_HOST=127.0.0.1 driftless notify digest --as-of 2026-03-31 \
  --db-url "$DRIFTLESS_DATABASE_URL"                             # sends, advances each cursor
DRIFTLESS_SMTP_HOST=127.0.0.1 driftless notify digest --as-of 2026-03-31 \
  --dry-run --db-url "$DRIFTLESS_DATABASE_URL"                   # prints the digest, sends nothing
```

A subscription's `last_sent_as_of` cursor only advances once `smtplib` reports
the message accepted, so a failed send resends the same as-of on the next run
rather than skipping it. `--dry-run` never sends and never advances a cursor.

## Revoking a session

Sessions are signed cookies, not server-side records, so revocation is a counter
on the row (`app_user.session_epoch`) that every cookie carries a copy of:

```sh
driftless user disable jp --db-url "$DRIFTLESS_DATABASE_URL"   # revokes immediately
driftless user enable  jp --db-url "$DRIFTLESS_DATABASE_URL"   # they sign in again
echo "$NEW_PW" | driftless user passwd jp --db-url "$DRIFTLESS_DATABASE_URL"   # revokes AND rotates
```

`disable` clears `is_active` **and** increments the counter, so every session
already issued to that user stops resolving — no waiting for the cookie to
expire. It is **irreversible for those cookies**: `enable` restores the login but
never lowers the counter, so the holder must sign in again. `passwd` increments
the same counter for the same reason: a suspected-leaked password is not fully
handled until the sessions it could still authenticate are dead too, so rotating
it is a revocation, not just a write. All three writes are audited through the
ChangeLog like any other.

`POST /logout` bumps the same counter, so a user can revoke themselves without an
operator: signing out on one device ends the session on **all** of them. Expect
support calls of the "my phone signed itself out" shape after somebody signs out on
a laptop — that is this behaviour, not a fault.

Needs the `session_epoch` column, added by revision `b46ef0a1c9d3` — run
`alembic upgrade head` (the release entrypoint does it; see *Upgrading*).

## Health probes

Two different questions, two routes. Both ask the store; what separates them is what
they **disclose**:

- `GET /health` — *can this instance serve?* One `SELECT 1` on a connection the pool
  already holds, answering `{"status":"ok"}` or a 503 `{"status":"unhealthy"}` and
  nothing else — no row read, no revision named. This is the probe
  `docker-compose.yml`'s healthcheck calls, so a process that is up but cannot reach
  Postgres reports unhealthy in `docker compose ps` rather than green. Nearer readiness
  than liveness, deliberately: it answered from a byte literal for one release and
  stayed green straight through an outage. It stays **outside** the token gate — an
  orchestrator needs no credential — and costs that one statement per `interval`, forever.
- `GET /health/ready` — **readiness**: the database answers *and* its
  `alembic_version` equals the revision this image requires
  (`driftless/db/schema_version.py`). It is **inside** the token gate on purpose — a
  revision number is exactly what `/health` withholds in order to stay open to anyone
  who can reach the port.

```sh
curl -fsS -H "Authorization: Bearer $DRIFTLESS_API_TOKEN" \
  http://127.0.0.1:8000/health/ready        # {"detail":"ready"}
```

Any other answer is a 503 with one of three phrasings and nothing else — no DSN,
no credentials, no driver text: `schema behind` (run the migration; a restart does
it), `schema ahead` (see *Rolling back*), `database unreachable`.

### An image older than the applied migration refuses to start

`schema ahead` is the one state no forward migration repairs, so the process does
not serve it at all. Before the first request, the app reads `alembic_version`;
if the stamped revision is not one this image knows, it exits instead of reading
and writing a schema it does not understand, and an orchestrator holds the failed
image out of rotation. What you will see in the log:

```
refusing to serve — the database is stamped with revision d9b71c04e5aa, which this
image has never heard of; it requires c8f3a1d47e29, and no forward migration
repairs that. Deploy the image that matches, or restore the pre-upgrade dump
(OPERATIONS.md, Rolling back). DRIFTLESS_ALLOW_SCHEMA_AHEAD=1 starts anyway, for a
rollback whose compatibility you have verified.
```

Only *ahead* is fatal. A store that is **behind** starts normally — deploy the
code, then migrate is the ordinary order — and so does one never stamped at all (a
`create_all` dev store). A database that will not answer does not stop the boot
either: that is an outage, readiness reports it, and a crash loop would be worse.

**The escape hatch.** `DRIFTLESS_ALLOW_SCHEMA_AHEAD=1` (exactly `1`; any other
value still refuses) starts the image anyway and logs a warning naming the stamped
revision on **every** start. It is the right call for a deliberate rollback whose
migrations you have read and found additive — a new table, a nullable column — and
which you need in service now. It is the wrong call as a way to leave a rolled-back
image running: a column the old code never writes, or a type it reads differently,
corrupts data quietly and the dump you would have restored gets further away every
hour. Unset it the moment the store and the image agree again.

## Secrets (SOPS → tmpfs)

Secrets are stored encrypted with [SOPS](https://github.com/getsops/sops) and
age, and decrypted into a tmpfs at container start — never committed or written
to disk in the clear.

1. Generate an age key for the deployment — **outside the repository**:

   ```sh
   mkdir -p ~/.config/driftless
   age-keygen -o ~/.config/driftless/age-key.txt    # private key
   chmod 0600 ~/.config/driftless/age-key.txt
   ```

   Put the printed **public** key into `.sops.yaml` as the recipient — and, in the
   same sitting, the **private** key into an escrow off this host (a password
   manager, offline media), named in `DRIFTLESS_KEY_ESCROW`. Nothing automated may
   copy it afterwards (*Restoring*): a host loss with no escrow is a shelf of
   verified dumps and a service that aborts at `sops -d` forever.

   **The path matters.** `docker compose up --build` sends the whole repository to
   the Docker daemon as the build context, and a file copied into an image layer
   stays there for good — `docker save` recovers it even if a later step deletes
   it. `.gitignore` keeps the key out of *git* and has no effect on that, so a key
   at `deploy/age-key.txt` would be built into an image alongside the encrypted
   overlay it decrypts. Two things stop that now — the `Dockerfile` copies
   `deploy/entrypoint.sh` by name instead of the whole directory, and
   `.dockerignore` excludes the key patterns — and a key kept outside the
   repository needs neither. `tests/test_docker_build_context.py` fails if either
   lock is removed or if a new secret pattern reaches only `.gitignore`.

2. Create the encrypted overlay from the template and fill in real values:

   ```sh
   cp deploy/secrets.env.example deploy/secrets.enc.env
   sops-edit deploy/secrets.enc.env          # all three keys below
   ```

   Three keys, all **required** — `POSTGRES_PASSWORD`, `DRIFTLESS_API_TOKEN` and
   `DRIFTLESS_SESSION_SECRET`. The entrypoint refuses to start without any one of
   them, naming the key and this file, rather than serving an instance nobody can
   sign into: the session layer fails closed, so an absent signing key would take
   browser sign-in, roles and the CSRF-bound forms down with it and say so only in
   a log line. Changing the signing key signs every open session out.

   Only `deploy/secrets.env.example` is committed, and it carries no real values.
   `deploy/secrets.enc.env` is written here, on this host, by the two commands
   above — no checkout arrives with it (`git ls-files deploy/`), which is why the
   variable below has to name it.

3. Point Compose at the private key and give Postgres its password for the run
   (sourced from the same SOPS file, kept in the shell only):

   ```sh
   export DRIFTLESS_AGE_KEY="$HOME/.config/driftless/age-key.txt"
   export DRIFTLESS_SECRETS_ENC="$PWD/deploy/secrets.enc.env"
   export POSTGRES_PASSWORD="$(sops -d --extract '["POSTGRES_PASSWORD"]' deploy/secrets.enc.env)"
   docker compose up -d --build
   ```

   `DRIFTLESS_AGE_KEY` is required and has **no fallback**: `docker-compose.yml`
   writes the mount source as `${DRIFTLESS_AGE_KEY:?…}`, the same shape as
   `POSTGRES_PASSWORD` above it, so leaving it unset makes Compose refuse to
   interpolate — it names the variable and the remedy and starts nothing at all,
   rather than bringing a container up that dies later on a failed decrypt. The
   default it used to carry pointed inside the build context, which is the one
   place the key must not sit, and it was a path no operator had typed.

   `DRIFTLESS_SECRETS_ENC` is required the same way and for a sharper reason: a
   bind mount whose source is missing is not an error Docker reports — it creates
   an empty *directory* at the path, and step 2's `cp` then lands the plaintext
   template inside it. `bin/driftless-backup.sh` reads the same variable, so one
   export serves the run and its backups.
   `tests/test_deploy_mount_sources.py` fails if a compose file starts requiring a
   variable this page does not hand the operator.

The API's `deploy/entrypoint.sh` then decrypts the overlay into `/run/secrets`
(tmpfs), assembles `DRIFTLESS_DATABASE_URL` from the parts, runs `alembic upgrade
head`, and starts `uvicorn driftless.api.secure:secured`. Sourcing the overlay
makes its keys *shell* variables; only the names on that script's one `export`
line become the server's environment, so adding a key to the overlay is half the
job. `tests/test_deploy_env.py` reads the package's own `os.environ` lookups and
fails if any of them is neither exported there nor listed with a reason it is not
needed in the container — the check that would have caught `DRIFTLESS_SESSION_SECRET`
being decrypted and then dropped.

## Database URL

`DRIFTLESS_DATABASE_URL` is the **canonical** environment variable naming the
store, read by the web dashboard, the API, `alembic`, and the `report` /
`assess` / `wizard` CLIs alike — they all resolve it through the single
`driftless.db.config.database_url()` helper, so one exported value points every
surface at the same database. Two **deprecated aliases** are honoured for one
deprecation cycle, in this order: `PMHUB_DATABASE_URL` (the pre-rename
canonical) and `PMHUB_DB_URL` (the CLIs' historical name); each applies only
when every name above it is unset. Set `DRIFTLESS_DATABASE_URL`; set several
and the canonical one wins. Each CLI's `--db-url` flag still overrides the
environment for that invocation. The API token behaves the same way:
`DRIFTLESS_API_TOKEN` is canonical and `PMHUB_API_TOKEN` from an existing SOPS
file keeps working for the same cycle.

**In-container CLI runs need the URL passed in.** `docker compose exec` starts a
new process from the *image*, inheriting nothing the entrypoint assembled, so a
bare `docker compose exec driftless-app driftless report all` finds no database.
The supported form passes it explicitly — and that is the design, not a gap: the
assembled URL carries the password, and keeping it inside one process is what
keeps it out of the image, the compose file and `docker inspect`.

```sh
export DRIFTLESS_DATABASE_URL="postgresql+psycopg://driftless:$POSTGRES_PASSWORD@driftless-db:5432/driftless"
docker compose exec -e DRIFTLESS_DATABASE_URL="$DRIFTLESS_DATABASE_URL" driftless-app sh
```

Pass it once into a shell and run several commands there, rather than repeating
`-e` per command: every `docker` argv is world-readable through `ps` on the host.

## Backups (with restore-verify)

`bin/driftless-backup.sh` dumps the database **and proves the dump restores** — it
loads the dump into a throwaway database and refuses to keep a backup whose
restored row counts, table by table, do not match the source. It then writes the other file a
restore needs, and a manifest naming the set. The timestamp is an argument, so a
scheduled run is reproducible:

```sh
export DRIFTLESS_AGE_KEY="$HOME/.config/driftless/age-key.txt"
export DRIFTLESS_KEY_ESCROW="<your password-manager entry for the age private key>"
export PGPASSWORD="$(sops -d --extract '["POSTGRES_PASSWORD"]' deploy/secrets.enc.env)"
bin/driftless-backup.sh "$(date +%FT%H-%M-%S)"        # writes ./backups/driftless-<stamp>.*
```

A non-zero exit means the backup did not verify and must be investigated. Before
dumping anything it decrypts the overlay with `$DRIFTLESS_AGE_KEY`, so no run
certifies a database whose secrets nobody can open any more — see *Restoring*,
the only reason to keep the dump.

### Scheduling the backup

`deploy/driftless-backup.{service,timer}` run it daily; `bin/driftless-backup-run.sh`
is what the unit executes, because a unit-file one-liner cannot be tested and this
one decrypts a password, picks the stamp and decides the exit code. Both unit files
assume the checkout is at `/opt/driftless` — a checkout elsewhere edits
`WorkingDirectory=` and `ExecStart=`, and nothing else.

`/etc/driftless/backup.env` holds the same settings the manual run exports above —
it names where the age key *is* and never contains the key:

```sh
sudo install -d -m 0755 /etc/driftless
sudo tee /etc/driftless/backup.env >/dev/null <<'ENV'
DRIFTLESS_AGE_KEY=/root/.config/driftless/age-key.txt
DRIFTLESS_KEY_ESCROW=<your password-manager entry for the age private key>
DRIFTLESS_BACKUP_DIR=/opt/driftless/backups
DRIFTLESS_BACKUP_LOG=/opt/driftless/backups/backup.log
ENV
sudo chmod 0600 /etc/driftless/backup.env
sudo cp deploy/driftless-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now driftless-backup.timer
systemctl list-timers driftless-backup.timer    # NEXT/LEFT — prove it is armed
sudo systemctl start driftless-backup.service   # run once by hand: blocks for minutes,
tail -3 /opt/driftless/backups/backup.log       # and is where a bad path shows up
```

**Failure is visible twice, on purpose.** The runner re-raises the script's exit
code, so a bad backup marks the unit failed instead of logging a problem and
reporting success; it also appends `<timestamp> driftless-backup stamp=<stamp>
exit=<rc>` to `$DRIFTLESS_BACKUP_LOG` for a watcher to scan. Anything but `exit=0`
is a backup that did not happen. **Nothing here reads that log** — wiring it to a
watcher is a step outside this service.

### Recovery objectives (RPO/RTO)

**RPO — acceptable data loss: 24 hours, once the timer is installed.**
`deploy/driftless-backup.timer` runs the backup daily at 03:00 local time with
up to 15 minutes of jitter, so the most that can be lost is a day's edits.
`Persistent=true` is what makes that a period rather than a hope: a host asleep
or powered off at 03:00 catches the run up on its next boot instead of skipping
the day in silence. **The units ship here; installing them is a step an
operator takes** (*Scheduling the backup*, below) — until then RPO is still the
gap since whoever last ran the script by hand.

**RTO — time from "database gone" to "serving again": untimed.** The steps
live in *Restoring → From a bare host*, below, but nobody has run that walk
end to end with a stopwatch. `docs/admin-guide.md`'s doc-runner excuses every
restore command as `manual` (`tests/test_docs_admin_guide.py`, its
`MANUAL_BLOCKS`) because it needs a live Postgres and Docker that CI does not
have — the only automated proof is that the *dump* restores clean, not that a
human can execute the *procedure*. Until someone runs and clocks a bare-host
drill, budget for "however long a paged operator takes to type *Restoring*
correctly, on the first try."

**Frequency: daily at 03:00, from `deploy/driftless-backup.timer`.** Change the
timer's `OnCalendar=` and this paragraph together — a schedule the documentation
disagrees with is how an operator ends up believing in backups that are not
being taken.

**Retention: none enforced.** The script never deletes an old set —
`$BACKUP_DIR` (default `./backups`) grows by three files every run, forever.
Pruning, and how many sets to keep, is a manual call this repo does not
automate.

**Storage: `$DRIFTLESS_BACKUP_DIR`, on whatever host ran the backup — no
offsite copy ships here.** Same host as the database means losing the host
loses the backups with it, the opposite of the "shelf of verified dumps"
*Secrets*, above, assumes a lost host still leaves; copying the set to a
second host or off-host storage, by hand, is what makes that assumption true.
The dump is age-encrypted to the escrowed key, so that copy can go somewhere
you do not fully control without handing the database over with it — the
remaining exposure is the key, which has never been in the set. Encryption
does not make an off-host copy exist; it only removes the reason not to make
one.

**"Restore-verified" certifies the dump, not the procedure.** Every run
restores its own dump into a throwaway database and keeps nothing unless
every table's row count matches the source
(`tests/test_backup_script_drill.py` proves this against a stubbed Postgres)
— that is a statement about the *file*. The bare-host walk that turns a
certified file into a running service has never been run as a drill;
recording one, timed, is what would give RTO a number instead of a guess.

## Restoring

A restore needs **three** artefacts, and the backup job writes only two of them:

| artefact | written by | holds |
|---|---|---|
| `backups/driftless-<stamp>.manifest` | `bin/driftless-backup.sh` | the code tag, the stamped revision, where the key is |
| `backups/driftless-<stamp>.dump.age` | `bin/driftless-backup.sh` | the database, encrypted and restore-verified |
| `backups/driftless-<stamp>.secrets.enc.env` | `bin/driftless-backup.sh` | the overlay **as it stood at the dump** |
| the age **private** key | **you, by hand, once** | both files above decrypt with it — without it the set is noise |

**The rule for the key: two copies, neither of them here.** One live at
`~/.config/driftless/age-key.txt` (`chmod 0600`), one escrowed off this host — a
password-manager entry or offline media — made by hand when you generated it.
Nothing automated may ever write it into `backups/` or the checkout: it decrypts
the overlay sitting beside the dump, so a copy in the backup set turns one stolen
archive into every secret this deployment has, and a copy in the checkout is one
`docker build` from a permanent image layer `docker save` recovers.
`DRIFTLESS_KEY_ESCROW` records the *location*, never the key, and the backup
refuses to run without it — so at 3am "where is the key?" is read, not recalled.

### From a bare host

The database service alone first, on purpose: the whole stack would run `alembic
upgrade head` against an empty store and build a current-head schema you then
restore over.

```sh
cat backups/driftless-<stamp>.manifest         # code tag, revision, where the key is
mkdir -p ~/.config/driftless                   # then paste the escrowed key in
chmod 0600 ~/.config/driftless/age-key.txt
export DRIFTLESS_AGE_KEY="$HOME/.config/driftless/age-key.txt"
export SOPS_AGE_KEY_FILE="$DRIFTLESS_AGE_KEY"
git checkout <the manifest's code tag>         # this checkout, at the dump's release
cp backups/driftless-<stamp>.secrets.enc.env deploy/secrets.enc.env
export POSTGRES_PASSWORD="$(sops -d --extract '["POSTGRES_PASSWORD"]' deploy/secrets.enc.env)"
export DRIFTLESS_API_TOKEN="$(sops -d --extract '["DRIFTLESS_API_TOKEN"]' deploy/secrets.enc.env)"
docker compose up -d driftless-db              # creates the `driftless` database, nothing else
export PGPASSWORD="$POSTGRES_PASSWORD"
age -d -i "$DRIFTLESS_AGE_KEY" <backups/driftless-<stamp>.dump.age \
  | pg_restore -h 127.0.0.1 -p 55432 -U driftless -d driftless --clean --if-exists
```

The dump is decrypted **into** `pg_restore` rather than onto disk: a cleartext copy
written here to be restored a moment later is one more file to remember to delete,
on the one host you least want it left on. The key is the same one the overlay
needed two commands ago — if that worked, this will.

Then prove it, because `pg_restore` exiting 0 says the file parsed, not that the
rows arrived:

```sh
psql -h 127.0.0.1 -p 55432 -U driftless -d driftless -tAc \
  'select version_num from alembic_version'    # the manifest's revision, exactly
psql -h 127.0.0.1 -p 55432 -U driftless -d driftless -tAc \
  'select count(*) from app_user'              # non-zero: rows, not an exit code
docker compose up -d --build                   # the entrypoint migrates forward, then serves
curl -fsS -H "Authorization: Bearer $DRIFTLESS_API_TOKEN" \
  http://127.0.0.1:8000/health/ready           # {"detail":"ready"}
```

`/health/ready` answers only when the store is reachable **and** stamped with the
revision this image requires. `schema behind` means the app has not migrated yet —
it does that at start, so restart it once; `schema ahead` means the dump is newer
than the code you checked out (*Rolling back*).

### Rolling back in place

The host is fine and the store has run ahead of the image you want. Same restore,
one dump older, and the app stopped so nothing writes during it:

```sh
docker compose stop driftless-app
export PGPASSWORD="$(sops -d --extract '["POSTGRES_PASSWORD"]' deploy/secrets.enc.env)"
bin/driftless-backup.sh "$(date +%FT%H-%M-%S)"   # step 1: bank what pg_restore is about to drop
age -d -i "$DRIFTLESS_AGE_KEY" <backups/driftless-<stamp>.dump.age \
  | pg_restore -h 127.0.0.1 -p 55432 -U driftless -d driftless --clean --if-exists
psql -h 127.0.0.1 -p 55432 -U driftless -d driftless -tAc \
  'select version_num from alembic_version'    # must be one the old image knows
git checkout <previous-tag> && docker compose up -d --build
```

## Request log

`driftless/api/logging.py` emits one JSON line per request — `ts`, `request_id`,
`method`, `path`, `status`, `duration_ms`, `client` — on the `driftless.request`
logger.

`request_id` is the token that ties a line to the response the caller held: it is
read off an inbound `X-Request-ID` header when the caller sends one, generated
otherwise, and echoed back on the response, so a user reporting a failure can
quote the id an operator greps for. An inbound header is untrusted, so one
outside a bounded alphanumeric shape is **replaced** rather than escaped and
logged — a newline or a quote in an echoed id would forge a second log record.
A route that raises is answered by the error handler *above* this middleware
(`driftless/web/errors.py`), not by this module directly — but that handler reads
the same id off `request.state`, stashed there before the route ran, so the 500 it
answers carries the id on the response header exactly as the log line does. Only a
request that never reached this middleware at all has no id to stamp, and the
handler omits the header rather than raise trying to read one.

The module only emits — it never calls `basicConfig` and never sets a level — so
it stays **silent until the process's logging configuration raises that one
logger**, and raising it makes nothing else noisier:

```python
import logging
logging.getLogger("driftless.request").setLevel(logging.INFO)
```

Anything that configures `logging` before the server starts serves, and the image
already does: `deploy/logging.json` is a `logging.config.dictConfig` document
raising `driftless.request` to `INFO` on stdout, and the `Dockerfile` `CMD` passes
it — `uvicorn … --log-config /app/deploy/logging.json`. Nothing to author, nothing
to mount. It also holds uvicorn's own access logger at `WARNING`, because that line
is built from the raw request target, query string included, where
`driftless.request` logs the path alone.

Query strings, request/response bodies and the `Authorization` header are
absent from the line by construction — a log is copied to places the database
is not, so there is nothing in it to redact. It is an operational stream, not
an audit trail: who changed what stays the ChangeLog's job.

## Metrics

`GET /metrics` (`driftless/api/metrics.py`) answers Prometheus text-exposition:
`driftless_http_requests_total` and `driftless_http_request_duration_seconds_sum`,
each labelled `method`, `status` and a low-cardinality route *template*
(`/projects/{project_id}`, never the raw path with an id in it), plus
`driftless_process_uptime_seconds`.

**Deliberately NOT one of the public paths above.** A scraper endpoint is
conventionally left uncredentialed; here that would disclose portfolio scale —
the same class of leak the Request log section refuses to carry, so `/metrics`
is held to that same rule and takes an ordinary authenticated `GET` — a
scraper points its `bearer_token_file` at a per-user or the shared token, the
same as any other script.

## Upgrading

A release is: back up, pull, rebuild. The migration ordering is not the
operator's to remember — `deploy/entrypoint.sh` runs `alembic upgrade head` and
only then `exec`s uvicorn, so **the schema is always upgraded before the new
image serves its first request**, and a failed migration exits the container
instead of serving against a stale schema.

```sh
export PGPASSWORD="$(sops -d --extract '["POSTGRES_PASSWORD"]' deploy/secrets.enc.env)"
bin/driftless-backup.sh "$(date +%FT%H-%M-%S)"   # pre-upgrade: a verified restore point
git pull
docker compose up -d --build                     # rebuild; entrypoint migrates, then serves
```

Verify before walking away:

```sh
docker compose ps                                # driftless-app reports healthy
curl -fsS http://127.0.0.1:8000/health           # {"status":"ok"}
docker compose logs --tail 50 driftless-app      # `alembic upgrade head` ran clean
```

### The published image

A tag pushed to the **public** repository publishes the image it was built
from — `ghcr.io/back-road-creative/driftless:<version>`, and `:latest`, built
from that tag's own tree by `.github/workflows/docker-publish.yml`
(`docs/release-publishing.md`). Until that tag exists there, there is nothing
to pull: as of this writing `Back-Road-Creative/driftless` has no tags, no
releases and no such package. What exists today is GitHub Releases for v0.4.0,
v0.2.0 and v0.1.0 on the private archive — notes only, no image, and not the
public repository this section is about.

The procedure above still rebuilds, and will until `docker-compose.yml` gives
`driftless-app` an `image:` — it has a `build:` and no `image:`, so
`docker compose up -d --build` builds from the checkout whatever the registry
holds. Which versions are in the registry is the `Back-Road-Creative` Packages
tab and the Releases page of `Back-Road-Creative/driftless`; read those rather
than this paragraph, which any new tag would silently outdate.

Once a public tag exists:

```sh
docker pull ghcr.io/back-road-creative/driftless:<version>   # a version those pages list
```

### Rolling back

Roll back by checking out the previous tag and rebuilding. An image whose code
predates a migration that has already run **will not start**: the entrypoint only
ever upgrades forward, so the stamped revision is not in that image's
`KNOWN_REVISIONS`, and the startup check exits rather than serving a schema the
code was never written against (*An image older than the applied migration refuses
to start*, above). Recovery is the **pre-upgrade dump**, because the schema does
not walk backwards on its own: the commands are *Restoring → Rolling back in
place*, and the old image starts clean once the store is stamped at a revision it
knows. `DRIFTLESS_ALLOW_SCHEMA_AHEAD=1` is the override, for a rollback you have
read the migrations for and found compatible. `CHANGELOG.md` names what moved
between releases.

## TLS (production profile)

The app never terminates TLS — `deploy/proxy.compose.yml` adds a Caddy reverse
proxy that does, and `deploy/Caddyfile` points it at `driftless-app:8000` over
the compose network. The app's only host-published port stays `127.0.0.1:8000`,
so the proxy is the single public listener; certificates are issued and renewed
automatically over ACME (port 80 must reach the proxy) and kept in a named volume
so a restart does not re-issue.

```sh
export DRIFTLESS_PUBLIC_HOST=driftless.example.com   # must resolve to this host
docker compose -f docker-compose.yml -f deploy/proxy.compose.yml up -d
curl -fsS https://$DRIFTLESS_PUBLIC_HOST/health      # {"status":"ok"} over TLS
```

Omit the second `-f` and you get the loopback-only deployment unchanged — the
right shape when an existing nginx or a cloud load balancer already fronts the
API. Either way the bearer token still gates every request; TLS is what stops it
crossing the network in the clear.

## Demo data

`driftless demo seed` fills an empty instance with the store every screenshot is taken from,
through the same validated API as an import below — never raw SQL:

```sh
driftless demo seed --base-url http://127.0.0.1:8000 --token "$DRIFTLESS_API_TOKEN"
```

`--anchor YYYY-MM-DD` fixes every date (default 2026-07-01); every offset hangs off it and
nothing reads the clock, so two seeds at one anchor produce the same store and a page pinned
to that as-of is byte-identical. The four projects are deliberately one verdict each, because
a rollup where every row is the same colour reads as a broken import rather than a portfolio:
**Season 4 Rollout** red (risk exposure past contingency, a missed milestone, quality out of
tolerance), **Archive Digitization** amber (CPI 0.95, an approved change never re-baselined),
**Fleet Modernization** green, and **Route Optimization Pilot** with no baseline, milestones
or status at all — an *unknown* RAG, not a false green. Every page has something on it and
every closed vocabulary a viewer meets has a row behind it; `tests/test_demo_web.py` asserts
both off the model's own tuples, so a new page or a grown vocabulary fails there.

## Importing real data

`bin/driftless-import.py` loads a business → portfolio → project → workstream → task
hierarchy from JSON **through the API** (so every row is validated and audited),
carrying the bearer token:

```sh
bin/driftless-import.py bin/sample-import.json \
  --base-url http://127.0.0.1:8000 --token "$DRIFTLESS_API_TOKEN"
```

`--csv KIND` reads one flat record per row instead, for the four kinds people
already keep in spreadsheets — `tasks`, `risks`, `costs` and `milestones`:

```sh
bin/driftless-import.py rows.csv --csv tasks \
  --base-url http://127.0.0.1:8000 --token "$DRIFTLESS_API_TOKEN"
```

Column names mirror the API's request schemas exactly (`bin/sample-tasks.csv` is a
working header), and the parent is always named by its **integer FK column**
(`workstream_id` for tasks, `project_id` for the other three) — never by name, so a
sheet carries the ids its author already has. A blank optional cell is omitted
rather than posted as `""`, leaving the API's default the only default. The whole
file is coerced before the first POST goes out, so an unknown column, a missing
required column or an uncoercible cell fails naming the spreadsheet's own row
number and imports nothing. Same door as JSON: validated and audited.

## Exporting data

Every list endpoint answers `?format=csv` as well as JSON — one parameter on the
single registration point all of them share, so an entity added later exports
without anyone wiring a second route:

```sh
curl -H "authorization: Bearer $DRIFTLESS_API_TOKEN" \
  'http://127.0.0.1:8000/tasks?format=csv' -o tasks.csv
```

The columns are that endpoint's own response fields in declaration order, header
row first: dates ISO, an unset field an empty cell, no index column. `format=json`
is the default and is byte for byte what the endpoint always returned; anything
other than `json` or `csv` is a 422.

**Drop the `id` column before importing an export back.** Exports carry `id` and
no import kind accepts it, so `bin/driftless-import.py` refuses the file naming
that column rather than ignoring it: the importer only ever *creates* rows, so a
file re-imported with its ids would duplicate every row it named instead of
updating it. Minus `id`, the columns of `/tasks`, `/risks`, `/cost-entries` and
`/milestones` are exactly what `--csv tasks|risks|costs|milestones` reads, so an
export edited in a spreadsheet loads straight back as new rows.

## Teardown

```sh
docker compose down                 # keep the data volume
docker compose down -v              # also remove driftless-pgdata (destroys data)
```
