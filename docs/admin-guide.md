# Running an instance

Bare host to an instance you would trust: install, the people, their credentials, data, the answers,
a verified backup, upgrade and rollback. **Every fenced block carries a `<!-- driftless:run … -->`
marker and `tests/test_docs_admin_guide.py` runs it**: an answer that stops being true fails there,
an unmarked fence fails too, and `manual` marks a step no unit test can run, with its reason.

## 1. Install and start

Docker Engine with the Compose plugin, a DNS name pointing at the box, ports 80 and 443 reachable
(ACME issues over 80). The SOPS overlay holds `POSTGRES_PASSWORD`, `DRIFTLESS_API_TOKEN` and
`DRIFTLESS_SESSION_SECRET` (`deploy/secrets.env.example`); create it with `age-keygen` and
`sops-edit` as *OPERATIONS.md → Secrets* sets out. The age **private** key goes to
`~/.config/driftless/age-key.txt`, `chmod 0600` — outside the checkout, so no build context can
copy it into an image layer that outlives the key. The second `-f` is the TLS profile: Caddy
terminates, the app still publishes only `127.0.0.1:8000`.

<!-- driftless:run manual why="needs a host, Docker, a real Postgres and ACME over 80/443" -->
```sh
git clone https://github.com/Back-Road-Creative/driftless.git && cd driftless
export DRIFTLESS_AGE_KEY="$HOME/.config/driftless/age-key.txt"
export DRIFTLESS_PUBLIC_HOST=driftless.example.com
export POSTGRES_PASSWORD="$(sops -d --extract '["POSTGRES_PASSWORD"]' deploy/secrets.enc.env)"
docker compose -f docker-compose.yml -f deploy/proxy.compose.yml up -d --build
```

You never run `alembic` by hand: `deploy/entrypoint.sh` decrypts the overlay to tmpfs, runs `alembic
upgrade head`, then `exec`s uvicorn, so a failed migration exits the container rather than serving a
stale schema. Sourcing the overlay only makes shell variables, so what reaches the server is what
that script `export`s — `DRIFTLESS_DATABASE_URL`, `DRIFTLESS_API_TOKEN` and
`DRIFTLESS_SESSION_SECRET`. A missing secret is a named boot failure telling you the key to add and
the file to add it to, never a container that starts and cannot be signed into; and
`tests/test_deploy_env.py` reads the package's own environment lookups, so a variable added later
cannot go unexported without failing there.

The gate repeats that refusal one layer down, for anyone who runs `uvicorn
driftless.api.secure:secured` outside the entrypoint entirely: with `DRIFTLESS_API_TOKEN` unset
it refuses to build the app rather than serve it open. `DRIFTLESS_ALLOW_UNAUTHENTICATED=1` is the
local-dev-only override, kept out of the SOPS overlay for the same reason
`DRIFTLESS_ALLOW_SCHEMA_AHEAD` is — a value baked into an encrypted file is invisible, and a
forgotten one there corrupts quietly.

## 2. Two users, and their roles

The CLI ships in the app image, so run the rest from inside it — `docker compose exec -e
DRIFTLESS_DATABASE_URL="postgresql+psycopg://driftless:$POSTGRES_PASSWORD@driftless-db:5432/driftless"
driftless-app sh`. The `-e` is not optional and not a workaround: `exec` starts a new process from
the image, inheriting nothing from the entrypoint that assembled the URL, which is exactly why no
credential lives in the image or in `docker inspect`. Passing it once into a shell then keeps it out
of each command's argv — argv is world-readable through `ps`, which is also why the password below
arrives on stdin. Roles are `admin`, `contributor`, `viewer` — all three
read, and anything that is not `GET`/`HEAD`/`OPTIONS` needs contributor or admin, decided at the one
gate before the route runs.

<!-- driftless:run cli exit=0 -->
```sh
echo "$ADMIN_PW" | driftless user add --username jp --role admin --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run cli exit=0 -->
```sh
echo "$OPS_PW" | driftless user add --username ops --role viewer --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run cli exit=0 -->
```sh
driftless user list --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run text -->
```text
ops                  viewer       active
```

`user list` prints username, role, state, email and creation date, never the password digest.
`user email <username> --address …` sets the address the email digest sends to (`--clear`
unsets it); unset, the digest falls back to an `@`-shaped username, and skips a user with
neither rather than guessing. `disable` deactivates
a login **and** revokes every cookie and token it holds; `enable` restores it, never those cookies.
`passwd` rotates a password the same way — the new digest replaces the old one and the same
revoke happens, so a compromised password stops working the moment it is changed rather than
staying valid until whoever holds a cookie happens to sign out.

<!-- driftless:run cli exit=0 -->
```sh
echo "$NEW_PW" | driftless user passwd jp --db-url "$DRIFTLESS_DATABASE_URL"
```

## 3. Credentials

`$DRIFTLESS_API_TOKEN` is the bootstrap credential: full write access, no role, writes audited with
no actor. Mint per-user tokens for everything else — the holder gets that account's role and every
row they write carries their name. `add` prints `dfl_…` on stdout alone, keeping only its digest.

<!-- driftless:run cli exit=0 capture=JP_TOKEN -->
```sh
driftless token add --username jp --label ci --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run http status=201 -->
```http
POST /api/v1/businesses
Authorization: Bearer $JP_TOKEN

{"name": "Back Road Creative"}
```
<!-- driftless:run sql -->
```sql
SELECT table_name, operation, actor FROM change_log WHERE table_name = 'business'
```
<!-- driftless:run text -->
```text
"actor": "jp"
```

A viewer's token reads every surface and is refused every write, body unread:

<!-- driftless:run cli exit=0 capture=OPS_TOKEN -->
```sh
driftless token add --username ops --label reporting --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run http status=403 -->
```http
POST /api/v1/businesses
Authorization: Bearer $OPS_TOKEN
```

Revocation is immediate, by the id `token list` prints beside its owner, label and state. A
token minted with `--expires-in-days` lapses on its own instead — both land as the same
`401`, and only `token list` (never a caller's response) tells the two apart:

`token list` also prints when each token was last used, or `unused` if it never has been —
the column to read before revoking, since a token nobody has spent in months is one whose
holder is gone. It is deliberately **coarse**: a use restamps it at most once a quarter hour,
so it answers "is this credential still live?" and not "when exactly was the last call?".
Stamping it is not an audited write and files no `change_log` row — otherwise every read
through a token would bury the trail of who changed what.

<!-- driftless:run cli exit=0 -->
```sh
driftless token revoke 1 --db-url "$DRIFTLESS_DATABASE_URL"
```

### Agent actors

A `Person` may be an **agent** — a non-human actor bound to one of the tokens above —
rather than a human: `POST /people` with `"kind": "agent"` and `"agent_token_id"` naming
the token it writes through (`PersonIn`, `driftless/models/people.py`). Every write that
token makes is still credited exactly as any other token's is (§3); `kind` and
`agent_token_id` change nothing about authentication or the audit trail.

What it changes is the sign-off ledger. `POST /sign-offs` (and the browser form behind
it) refuses a decision made through an agent's token with `403` by default — `driftless
demo seed` and every other agent-token write are unaffected, only sign-off is gated.
Set `DRIFTLESS_ALLOW_AGENT_SIGNOFF=1` to let an agent's token append to the ledger; unset
or any other value keeps it refused. There is no CLI or API surface for the flag itself —
it is read from the process environment the same way `DRIFTLESS_ALLOW_UNAUTHENTICATED`
and `DRIFTLESS_ALLOW_SCHEMA_AHEAD` are (§1), so it is set the same place those are, before
the image starts. A sign-off that lands carries `signed_by_kind: "agent"` in its response
body, and the org heatmap (`GET /org/heatmap`) marks an agent's row with `(agent)` beside
its name — both are read-only markers, not a second write path.

### OIDC sign-in

`/auth/oidc/start` and `/auth/oidc/callback` let a login arrive from an external
identity provider — Keycloak, Authentik, Entra ID, Google, or any other OIDC-conformant
IdP — instead of a password. Mapping is closed-world: nothing is auto-provisioned. An
admin binds the IdP's `sub` claim to an existing local account first:

<!-- driftless:run cli exit=0 -->
```sh
driftless user oidc-subject jp --subject "auth0|64f2b1" --db-url "$DRIFTLESS_DATABASE_URL"
```

`--clear` unbinds it. A `sub` already bound to another user is refused by the store's own
uniqueness, not a racy pre-check; an inactive user is refused at sign-in even if bound.

The routes are configured entirely through the process environment, the same place
`DRIFTLESS_ALLOW_AGENT_SIGNOFF` (§3) is set — there is no CLI or API surface for it:

- `DRIFTLESS_OIDC_ISSUER` — the IdP's issuer URL; `<issuer>/.well-known/openid-configuration`
  must resolve. Must be `https://` unless it is a loopback address (local testing only).
- `DRIFTLESS_OIDC_CLIENT_ID`, and either `DRIFTLESS_OIDC_CLIENT_SECRET` or
  `DRIFTLESS_OIDC_CLIENT_SECRET_FILE` (a path, for a secret mounted rather than exported) —
  a confidential client registered with the IdP.
- `DRIFTLESS_OIDC_REDIRECT_URI` — must exactly match the redirect URI registered with the
  IdP, ending in `/auth/oidc/callback`.

Until all of the above are set, both routes answer `404` — there is no half-configured
state to probe. On success the flow issues the same session cookie password sign-in does
(`driftless.auth.sessions`); on failure (bad `state`, a `nonce` mismatch, a wrong or
expired token, or an unbound `sub`) it refuses without ever creating a session.

The ID token's signature is deliberately **not verified** — the token arrives over the
same TLS-authenticated connection the code was exchanged on (OIDC Core §3.1.3.7 item 6
permits skipping signature validation for exactly this reason), so trusting that
connection is trusting the token. What *is* validated: `iss` matches the configured
issuer, `aud` contains the client id, `exp` has not passed, and `nonce` matches the one
this login started with. No signing-key fetch or JWKS cache is needed, which is also why
this integration needs no new dependency — the whole flow is standard library only.

## 4. Demo data

Posted row by row through the validated API; `--anchor` fixes every date, so two seeds match. A
store that already holds a business is refused — the demo rows could never be deleted out again
(approved baselines freeze, parents with children refuse) — so `--force` is you saying the store
is disposable. Here it acknowledges the business §3 created:

<!-- driftless:run cli exit=0 -->
```sh
driftless demo seed --base-url http://127.0.0.1:8000 --token "$DRIFTLESS_API_TOKEN" --force
```

## 5. Does it answer?

`GET /health` asks the store one `SELECT 1` and reports only whether it answered — this is what the
container healthcheck calls, so an outage turns `docker compose ps` red instead of leaving it green.
Saying no more than that is what lets it answer without a credential:

<!-- driftless:run http status=200 -->
```http
GET /health
```

Readiness is harder — the database answers **and** carries the revision this image requires
(`driftless/db/schema_version.py`). A revision number is not for anonymous callers, so that one sits
inside the gate, and has three answers with nothing else in them, no DSN, no driver text:

<!-- driftless:run http status=200 stamped=a9c3e7f21d05 -->
```http
GET /health/ready
```
<!-- driftless:run http status=503 stamped=none -->
```http
GET /health/ready
```
<!-- driftless:run text -->
```text
{"detail":"schema behind"}
```

*Behind* is ordinary — deploy the code, then migrate; a restart fixes it. *Ahead* is not: the store
is stamped with a revision this image has never heard of, which no forward migration repairs.

<!-- driftless:run http status=503 stamped=d9b71c04e5aa -->
```http
GET /health/ready
```
<!-- driftless:run text -->
```text
{"detail":"schema ahead"}
```

You will normally never see that one: an image whose store is ahead **refuses to start**, rather than
read and write a schema it does not understand. Readiness answers it only with the override below.

## 6. Back up, upgrade, roll back

`bin/driftless-backup.sh` dumps, restores the dump into a throwaway database and keeps the backup
only if every table's row count matches — a backup never restored is a hope. The timestamp is an argument, so
a timer's run is reproducible; a non-zero exit means it did not verify. A release is that backup,
then pull and rebuild — the order is not yours to remember, the entrypoint migrates before serving.

A backup is a **set**: the dump, the overlay as it stood at the dump, and a manifest naming both
plus where the age private key is escrowed. The dump is age-encrypted to that same key as it is
written, so the set can be copied off this host without copying the database out in the clear.
The key is never in it — it now opens both files, so a copy there makes one stolen archive open
everything. The script proves it works by decrypting before it dumps and restoring through it
afterwards, and refuses to run until `DRIFTLESS_KEY_ESCROW` names your copy.

<!-- driftless:run manual why="pg_dump/pg_restore against a live Postgres, git and Docker" -->
```sh
export PGPASSWORD="$POSTGRES_PASSWORD"
export DRIFTLESS_KEY_ESCROW="<your password-manager entry for the age private key>"
bin/driftless-backup.sh "$(date +%FT%H-%M-%S)"   # ./backups/driftless-<stamp>.*, verified
git pull && docker compose up -d --build && docker compose ps
```

**Rolling back is not the reverse.** Check out the previous tag and the old image will not start:
the store is stamped past it (`SELECT version_num FROM alembic_version` says with what) and the
entrypoint only migrates forward. So: stop the app, **restore the pre-upgrade dump** — the schema
does not walk backwards on its own — then start the old image, which finds a store it knows.

<!-- driftless:run manual why="pg_restore against a live Postgres, and a rebuild" -->
```sh
docker compose stop driftless-app
export PGPASSWORD="$(sops -d --extract '["POSTGRES_PASSWORD"]' deploy/secrets.enc.env)"
age -d -i "$DRIFTLESS_AGE_KEY" <backups/driftless-<stamp>.dump.age \
  | pg_restore -h 127.0.0.1 -p 55432 -U driftless -d driftless --clean --if-exists
git checkout <previous-tag> && docker compose up -d --build
```

`PGPASSWORD` is in that same block deliberately — a recovery is a fresh shell, and `pg_restore`
prompting for a password you have not decrypted yet is where an unrehearsed restore stops.
`--if-exists` keeps every DROP for an object the newer schema added from being an error.
Losing the whole host is the longer procedure — the key comes back from escrow first — and it
is *OPERATIONS.md → Restoring*.

**`pg_restore` exiting 0 means the file parsed, not that the rows arrived.** Ask the store two
questions; the first is the one the image asks itself at boot:

<!-- driftless:run sql stamped=a9c3e7f21d05 -->
```sql
SELECT version_num FROM alembic_version
```
<!-- driftless:run text -->
```text
a9c3e7f21d05
```
<!-- driftless:run sql -->
```sql
SELECT count(*) AS users FROM app_user
```
<!-- driftless:run text -->
```text
"users": 2
```
<!-- driftless:run http status=200 stamped=a9c3e7f21d05 -->
```http
GET /health/ready
```
<!-- driftless:run text -->
```text
{"detail":"ready"}
```

`DRIFTLESS_ALLOW_SCHEMA_AHEAD=1` (exactly `1`) starts the old image against the newer store anyway,
logging a warning naming the stamped revision every start. It is right only for a rollback whose
migrations you have read and found additive — a new table, a nullable column. Unset it the moment
the two agree: left on, a column the old code never writes corrupts data quietly while the dump you
would have restored gets further away every hour.

## 7. Webhook subscriptions

`notify add` subscribes a URL to the audit trail; delivery walks `change_log` rows past the
subscription's cursor, oldest first, signs each POST `X-Driftless-Signature: sha256=<hmac hex>`,
and advances the cursor only on a `2xx` — a failure stops that subscription right there, so the
next run resumes from the same row. Run `notify deliver` from cron or a systemd timer.

<!-- driftless:run cli exit=0 -->
```sh
driftless notify add --url https://example.test/hook --secret shared-webhook-secret --events business --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run cli exit=0 -->
```sh
driftless notify list --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run text -->
```text
active
```
`--dry-run` reports what a run would deliver and sends nothing:

<!-- driftless:run cli exit=0 -->
```sh
driftless notify deliver --dry-run --db-url "$DRIFTLESS_DATABASE_URL"
```
