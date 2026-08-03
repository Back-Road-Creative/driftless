# Driving driftless from an agent

Get a credential, ask the wizard what the project needs next, write it, read it back, export
it. **Every fenced block below is executed by `tests/test_docs_agent_guide.py`** against a
real app and a throwaway store, so a status, field or column that stops being true fails
there and not in your integration. Requests carry `Authorization: Bearer $DRIFTLESS_TOKEN`
and `Content-Type: application/json` unless the block says otherwise.

## 1. A credential of your own

`$DRIFTLESS_API_TOKEN`, the shared bearer of `OPERATIONS.md`, is the bootstrap credential:
full write access, no role, writes recorded with **no actor**. Mint against an account
instead — the password arrives on stdin, never argv:

<!-- driftless:run cli exit=0 -->
```sh
echo "$AGENT_PASSWORD" | driftless user add --username agent --role contributor --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run cli exit=0 capture=DRIFTLESS_TOKEN -->
```sh
driftless token add --username agent --label agent-loop --db-url "$DRIFTLESS_DATABASE_URL"
```

`add` prints `dfl_…` on stdout alone and stores only its digest, so that is the one moment
the plaintext exists. A token also carries its owner's role, enforced at the gate before any
route — so a viewer's token reads every surface and is refused every write, body unread:

<!-- driftless:run cli exit=0 -->
```sh
echo "$AGENT_PASSWORD" | driftless user add --username reader --role viewer --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run cli exit=0 capture=VIEWER_TOKEN -->
```sh
driftless token add --username reader --label read-only --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run http status=403 -->
```http
POST /stakeholders
Authorization: Bearer $VIEWER_TOKEN
```

## 2. Stand the hierarchy up

Business → portfolio → project; each answers `201` with the row it created.

<!-- driftless:run http status=201 -->
```http
POST /businesses

{"name": "Back Road Creative"}
```
<!-- driftless:run http status=201 -->
```http
POST /portfolios

{"name": "Content Brands", "business_id": 1}
```
<!-- driftless:run http status=201 -->
```http
POST /projects

{"name": "Aurora", "portfolio_id": 1, "delivery_mode": "predictive"}
```

## 3. The wizard loop

`wizard next` prints the next PMBOK process this project has not finished and the store can
help with: its `inputs` (each a `kind` and whether it is `present`), its `tools_techniques`
and `outputs`, and `producible` — the ones the wizard itself can write, so an output the store
computes rather than stores is never offered. `--as-of` is determinism, not taste.

<!-- driftless:run cli exit=0 -->
```sh
driftless wizard next --project Aurora --as-of 2026-03-31 --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run json -->
```json
{"process_id": "4.1", "name": "Develop Project Charter", "group": "initiating",
 "state": "not_started", "producible": ["assumption_log"],
 "inputs": [{"kind": "business_case", "present": false}]}
```

Write that output through the API, so the row is validated **and** attributed to your
token's owner. `producible` names artifact kinds, not routes — `assumption_log` is a
`/narrative-artifacts` kind, `stakeholder_register` a `/stakeholders` row; that map lives in
`driftless/wizard/cli.py` (`_PRODUCERS`) and is served nowhere.

<!-- driftless:run http status=201 -->
```http
POST /narrative-artifacts

{"project_id": 1, "kind": "assumption_log", "body": "Vendor lead times hold at six weeks."}
```

Ask again: 4.1 is satisfied and the loop has moved on. Repeat until `next` prints `null`
(`wizard status` prints every catalog process and its state at once instead of one step).

<!-- driftless:run cli exit=0 -->
```sh
driftless wizard next --project Aurora --as-of 2026-03-31 --db-url "$DRIFTLESS_DATABASE_URL"
```
<!-- driftless:run json -->
```json
{"process_id": "13.1", "name": "Identify Stakeholders",
 "producible": ["stakeholder_register"]}
```

`wizard apply --kind …` writes that row from the CLI instead, but a CLI run has no signed-in
identity, so its `change_log` row carries `actor=null`. Drive the wizard's own write side and
keep the name: `POST /projects/{id}/wizard/apply` takes the browser's form encoding, and a
request authenticated by a **bearer token needs no CSRF pair** — the pair guards *ambient*
cookies, which a token is not. It answers `303` back to the wizard page, which your client
follows. A cookie request still pairs, and a viewer's token is still refused.

<!-- driftless:run http status=200 -->
```http
POST /projects/1/wizard/apply
Content-Type: application/x-www-form-urlencoded

kind=stakeholder_register&as_of=2026-03-31&name=Ada+Lovelace
```

Post the fields the kind is made of — no producer invents a missing one, so a nameless
stakeholder is refused `422` rather than filed (the presence checks only count rows, and a
placeholder would mark that output produced for good). `risk_register` takes `description`,
`probability`, `impact`; `cost_baseline` `category`, `planned_amount`; `milestone_list` `name`,
`target_date`; `quality_report` `metric`, `target_value`, `actual_value`; `agreements`
`vendor`; `issue_log`/`change_log` `description`; the baselines `planned_cost`;
`status_report` `rag_status`; the prose kinds `body`.

## 4. Read it back, and export

Every list endpoint answers `?format=csv` as well as JSON — its own response fields in
declaration order, header first, CRLF rows, defaults filled in; `/{id}` reads one row:

<!-- driftless:run http status=200 -->
```http
GET /narrative-artifacts?format=csv
```
<!-- driftless:run csv -->
```csv
project_id,kind,body,updated_on,id
1,assumption_log,Vendor lead times hold at six weeks.,,1
```

**A list answers a window, not the table.** A bare `GET` returns at most 500 rows ordered by
primary key. `?limit=` and `?offset=` move that window, and a `?limit=` above 2000 is clamped to
2000 rather than refused. Both encodings carry `X-Total-Count`, `X-Limit` and `X-Offset`, so
compare `X-Total-Count` against the rows you received before treating a page as the whole set —
otherwise a truncated list is indistinguishable from a complete one. Where a list takes `?q=`,
it filters before the window is applied, so the count you get back is the count of matches.

## 5. What was audited

Every write through a session lands an append-only `change_log` row: table, row id,
operation, old/new values, and the **username behind the credential** — the question an
operator will put to you. It has no endpoint yet, so read it in SQL:

<!-- driftless:run sql -->
```sql
SELECT table_name, row_id, operation, actor FROM change_log WHERE table_name IN ('narrative_artifact', 'stakeholder')
```
<!-- driftless:run json -->
```json
[{"table_name": "narrative_artifact", "row_id": "1", "operation": "insert", "actor": "agent"},
 {"table_name": "stakeholder", "row_id": "1", "operation": "insert", "actor": "agent"}]
```
