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
POST /api/v1/stakeholders
Authorization: Bearer $VIEWER_TOKEN
```

Your token authenticates you as a **contributor** — a human account, as far as the store
is concerned, even though you are the one holding it. If you are automating a workflow on
behalf of a `Person` the store should itself record as non-human, create that person with
`"kind": "agent"` and `"agent_token_id"` naming this token (`POST /people`,
`docs/admin-guide.md` → *Agent actors*). That binding gates exactly one write: `POST
/sign-offs` refuses a decision made through an agent-bound token with `403` unless an
operator has set `DRIFTLESS_ALLOW_AGENT_SIGNOFF=1`. Nothing else about your token changes —
every other route you can already reach stays reachable.

## 2. Stand the hierarchy up

**Address every resource as `/api/v1/…`.** That is the canonical path, the only one the
generated schema describes, and what every example below writes. The bare path
(`POST /businesses`) still answers exactly the same endpoint and is not going away without
notice, but it is no longer advertised and new clients should not be built on it.

Two kinds of address are deliberately **not** versioned, so a missing `/api/v1` in the
examples is the rule rather than an oversight. Operating endpoints — `/health`,
`/health/ready`, `/metrics` — keep their own names, because they are how you run the service
rather than resources whose shape you code against. So do the browser's own form posts, like
the wizard's `POST /projects/{id}/wizard/apply` below: they answer a redirect to a page, not
a resource, and are versioned with the page they belong to.

**Retrying a write? Send `Idempotency-Key`.** A POST repeating a spent key returns the original
answer with `Idempotent-Replay: true` instead of creating a second row. If the first attempt never
finished, the retry is refused `409` — it may have landed, so read before re-sending. Reusing one
key on a different endpoint is `422`.

Business → portfolio → project; each answers `201` with the row it created.

<!-- driftless:run http status=201 -->
```http
POST /api/v1/businesses

{"name": "Back Road Creative"}
```
<!-- driftless:run http status=201 -->
```http
POST /api/v1/portfolios

{"name": "Content Brands", "business_id": 1}
```
<!-- driftless:run http status=201 -->
```http
POST /api/v1/projects

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
`driftless/services/wizard_writes.py` (`_PRODUCERS`) and is served nowhere.

<!-- driftless:run http status=201 -->
```http
POST /api/v1/narrative-artifacts

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

`wizard apply --kind … --actor …` writes that row from the CLI instead; `--actor` is required
(it defaults to `cli` if you omit it) and is what the `change_log` row credits, since a CLI run
has no signed-in identity of its own to fall back on. Drive the wizard's own write side and
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
GET /api/v1/narrative-artifacts?format=csv
```
<!-- driftless:run csv -->
```csv
project_id,kind,body,updated_on,id,row_revision
1,assumption_log,Vendor lead times hold at six weeks.,,1,1
```

**A list answers a window, not the table.** A bare `GET` returns at most 500 rows ordered by
primary key. `?limit=` and `?offset=` move that window, and a `?limit=` above 2000 is clamped to
2000 rather than refused. Both encodings carry `X-Total-Count`, `X-Limit` and `X-Offset`, so
compare `X-Total-Count` against the rows you received before treating a page as the whole set —
otherwise a truncated list is indistinguishable from a complete one. Where a list takes `?q=`,
it filters before the window is applied, so the count you get back is the count of matches.

**Page with `?cursor=` rather than `?offset=` when the collection is being written to.** Pass
the id of the last row you saw and you get the rows after it; the answer carries
`X-Next-Cursor` when more remain, and omits that header on the final page — so loop until it
is absent rather than until you see a short page. Every list takes it, because every list is
already ordered by primary key. `?offset=` counts positions, so a row deleted from a page you
already read slides everything down one and your next offset page steps over a row; a cursor
names a row, so a change behind it cannot move the boundary. Send one or the other — `?cursor=`
together with `?offset=` is refused `422` rather than one of them being quietly ignored.

**Every other list also filters, derived off its own schema rather than a hand-kept table.** A
foreign key column scopes to its parent id — `?business_id=`, `?portfolio_id=`, `?program_id=`, `?responsible_department_id=`, `?project_id=`, `?workstream_id=`, `?assignee_id=`, `?department_id=`, `?objective_id=`, `?baseline_id=`, `?task_id=`, `?risk_id=`, `?resulting_baseline_id=`, `?metric_definition_id=`, `?quality_metric_id=`, `?release_id=`, `?service_id=`, `?control_id=`, `?predecessor_task_id=`, `?successor_task_id=`, `?calendar_id=`, `?subject_task_id=`, `?owner_id=`, `?source_stakeholder_id=`, `?requirement_id=`, `?deliverable_id=`, `?backlog_item_id=`, `?parent_id=`, `?resource_type_id=`, `?person_id=`, `?conflict_id=`, `?supersedes_id=` and `?agent_token_id=` are every one of them today — a note or artifact link filed against any record also takes `?record_kind=` and `?record_id=` by equality; and `?status=`/`?rag_status=` filter by equality; `X-Total-Count` reports the filtered count, never the whole table. A name this vocabulary does not recognise is refused `422`, naming it, rather than silently ignored:

<!-- driftless:run http status=200 -->
```http
GET /api/v1/narrative-artifacts?project_id=1
```
<!-- driftless:run json -->
```json
[{"project_id": 1, "kind": "assumption_log"}]
```
<!-- driftless:run http status=422 -->
```http
GET /api/v1/narrative-artifacts?bogus=1
```

**A dated column takes a range, and both ends are inclusive.** Every `Date` column gets a
`_from` and a `_to` derived the same way the filters above are, so `GET /issues?raised_on_from=2026-01-01&raised_on_to=2026-01-31`
is every issue raised in January, 31st included. Give one end and not the other for an open
range. The full set is `?accepted_on_from=`, `?accepted_on_to=`, `?active_from_from=`, `?active_from_to=`, `?active_until_from=`,
`?active_until_to=`, `?actual_finish_from=`, `?actual_finish_to=`,
`?as_of_from=`, `?as_of_to=`, `?assessed_on_from=`, `?assessed_on_to=`,
`?baseline_date_from=`, `?baseline_date_to=`, `?completed_on_from=`, `?completed_on_to=`,
`?created_on_from=`, `?created_on_to=`,
`?done_on_from=`, `?done_on_to=`, `?due_on_from=`, `?due_on_to=`, `?effective_from_from=`, `?effective_from_to=`,
`?end_date_from=`, `?end_date_to=`, `?forecast_finish_from=`, `?forecast_finish_to=`,
`?fulfilled_on_from=`, `?fulfilled_on_to=`,
`?incurred_on_from=`, `?incurred_on_to=`,
`?last_completed_on_from=`, `?last_completed_on_to=`, `?measured_on_from=`, `?measured_on_to=`,
`?next_due_on_from=`, `?next_due_on_to=`, `?on_date_from=`, `?on_date_to=`,
`?observed_on_from=`, `?observed_on_to=`, `?planned_finish_from=`, `?planned_finish_to=`,
`?planned_start_from=`, `?planned_start_to=`, `?raised_on_from=`, `?raised_on_to=`,
`?requested_on_from=`, `?requested_on_to=`,
`?resolved_on_from=`, `?resolved_on_to=`, `?retrospective_held_on_from=`,
`?retrospective_held_on_to=`, `?review_held_on_from=`, `?review_held_on_to=`,
`?start_date_from=`, `?start_date_to=`, `?started_on_from=`, `?started_on_to=`,
`?taken_on_from=`, `?taken_on_to=`, `?target_date_from=`, `?target_date_to=`,
`?updated_on_from=`, `?updated_on_to=`, `?verified_on_from=` and `?verified_on_to=`.
The suffix is appended mechanically, so a column
already ending in `_from` reads doubled (`?effective_from_from=`) — predictable beats pretty,
because the rule stays one you can apply to a column added later without checking a table.

**Timestamps are deliberately not filterable.** `signed_at`, `approved_at`, `created_at`,
`revoked_at`, `expires_at` and `changed_at` record when the system wrote a row, not when
anything happened in your project, and none of them takes a range. Ask a "what changed since"
question through the `ChangeLog`, which is built as a sync cursor; a date bound against a
timestamp compares to midnight, so a `_to` would quietly drop the last day it named.

**The method graph is readable as JSON**, at `GET /map/graph.json` — every process,
technique and artifact node and every `reads`/`produces`/`used_by`/`feeds` edge, the same
tuples `pmbok/graph.py`'s `GRAPH.to_dict()` yields, plus a top-level `source_version`. Each
node also carries `x`/`y` (the same coordinates `/map`'s SVG draws it at), `group`/`area`
(process nodes; `null` otherwise), `family` (technique and artifact nodes; `null` otherwise)
and `href` — its own page, enough to redraw the map without also fetching `/map`. It takes
no credential beyond any other read-only reference page, no `as_of`, and answers the same
bytes on every call — there is no store behind it to change. Read it once to build a local
adjacency map of the whole method rather than walking `/pmbok/{id}` per process.

## 5. What was audited

Every write through a session lands an append-only `change_log` row: table, row id,
operation, old/new values, the **username behind the credential** and the **channel it
came through** (`via`: `web`, `api`, `cli` or `mcp`) — the questions an operator will put
to you. A row written before `via` existed, or through a caller that never set it, reads
`via=NULL`, meaning unknown rather than any one channel. Every row also carries a
`row_hash` chained to the one before it (`prev_hash`), so editing or deleting any row —
even the most recent one — breaks the chain at that point; `verify_chain` walks the table
and reports the first row where it does. It has no endpoint yet, so read it in SQL:

<!-- driftless:run sql -->
```sql
SELECT table_name, row_id, operation, actor, via FROM change_log WHERE table_name IN ('narrative_artifact', 'stakeholder')
```
<!-- driftless:run json -->
```json
[{"table_name": "narrative_artifact", "row_id": "1", "operation": "insert", "actor": "agent", "via": "api"},
 {"table_name": "stakeholder", "row_id": "1", "operation": "insert", "actor": "agent", "via": "api"}]
```

## 6. The same loop over MCP

Everything above is also a tool call, over `driftless mcp serve` (stdio; no extra
install -- the JSON-RPC wire format is implemented in-package). driftless has no
in-product LLM — an
agent proposes a write, the `ChangeLog` records who made it, and a human still signs off
where a `SignOff` row is the process's output. MCP is a second transport onto the exact
same boundary, never a shortcut around it: the generic `create_resource` / `list_resource`
/ `get_resource` / `update_resource` / `delete_resource` tools carry a bearer token through
to the same gated app `/api/v1` answers from, and the `wizard_next` / `wizard_status` /
`wizard_apply` tools call the same `driftless.wizard.engine` and
`driftless.services.wizard_writes.produce` the CLI and the web wizard page already share
— so a write's actor, role gate and validation are unchanged by which transport asked.

`wizard_status` answers the whole process-state map as `[process_id, state]` pairs, the
same shape `driftless wizard status` prints; process 4.1 is still `"produced"` from the
`assumption_log` produced back in §3:

<!-- driftless:run mcp exit=0 -->
```json
{"tool": "wizard_status", "args": {"token": "$DRIFTLESS_TOKEN", "project_id": 1, "as_of": "2026-03-31"}}
```
<!-- driftless:run json -->
```json
[["4.1", "produced"]]
```

`create_resource` takes the same `/api/v1` path and body a `POST` would, and answers the
same status and row:

<!-- driftless:run mcp exit=0 -->
```json
{"tool": "create_resource", "args": {"token": "$DRIFTLESS_TOKEN", "path": "/businesses", "body": {"name": "Agent Ops"}}}
```
<!-- driftless:run json -->
```json
{"status": 201, "body": {"name": "Agent Ops", "id": 2}}
```
