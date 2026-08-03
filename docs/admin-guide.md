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

`user list` prints username, role, state and creation date, never the digest. `disable` deactivates
a login **and** revokes every cookie and token it holds; `enable` restores it, never those cookies.

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
POST /businesses
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
POST /businesses
Authorization: Bearer $OPS_TOKEN
```

Revocation is immediate — no expiry to wait out — by the id `token list` prints beside its owner,
label and state:

<!-- driftless:run cli exit=0 -->
```sh
driftless token revoke 1 --db-url "$DRIFTLESS_DATABASE_URL"
```

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

<!-- driftless:run http status=200 stamped=c8f3a1d47e29 -->
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
plus where the age private key is escrowed. The key is never in it — it decrypts the overlay
beside it, so a copy there makes one stolen archive open everything. The script proves it works
by decrypting before it dumps, and refuses to run until `DRIFTLESS_KEY_ESCROW` names your copy.

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
pg_restore -h 127.0.0.1 -p 55432 -U driftless -d driftless --clean --if-exists \
  backups/driftless-<stamp>.dump
git checkout <previous-tag> && docker compose up -d --build
```

`PGPASSWORD` is in that same block deliberately — a recovery is a fresh shell, and `pg_restore`
prompting for a password you have not decrypted yet is where an unrehearsed restore stops.
`--if-exists` keeps every DROP for an object the newer schema added from being an error.
Losing the whole host is the longer procedure — the key comes back from escrow first — and it
is *OPERATIONS.md → Restoring*.

**`pg_restore` exiting 0 means the file parsed, not that the rows arrived.** Ask the store two
questions; the first is the one the image asks itself at boot:

<!-- driftless:run sql stamped=c8f3a1d47e29 -->
```sql
SELECT version_num FROM alembic_version
```
<!-- driftless:run text -->
```text
c8f3a1d47e29
```
<!-- driftless:run sql -->
```sql
SELECT count(*) AS users FROM app_user
```
<!-- driftless:run text -->
```text
"users": 2
```
<!-- driftless:run http status=200 stamped=c8f3a1d47e29 -->
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
