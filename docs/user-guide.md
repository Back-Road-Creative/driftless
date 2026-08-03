# Using driftless

Every figure here is computed — nothing on a screen was typed by anybody. **Each fenced block
below is opened by `tests/test_docs_user_guide.py`** as a signed-in browser against a real store,
so a screen or label that stops being true fails there. `$USER_PASSWORD` is your own password.

## 1. Signing in

Ask for any page without a session and you land on `/login`. Type the two things:

<!-- driftless:run signin status=200 -->
```text
Username: dana
Password: $USER_PASSWORD
```
<!-- driftless:run text -->
```text
Needs attention
```

You land on the dashboard, signed in for 12 hours. Every refusal reads the same whichever half was
wrong, and 5 failures in 15 minutes buys a wait. **Sign out ends the session on every
device** — your account is revoked, not one cookie. `admin` and `contributor` read and write;
`viewer` reads every page and meets *"That is a read-only account"* on any change.

## 2. The dashboard — is the whole business on track?

<!-- driftless:run page status=200 -->
```text
/?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Cost S-curve — whole business
```

Seven tiles: budget, actual spend, percent complete, share of projects on track, open high risks,
open threats, process completeness. Then the whole-business cost curve, a treemap whose rectangle
*areas* are portfolio budgets, and the rollup table — business to project, each row with its RAG,
budget, actual, percent complete, open high risks, a burn sparkline and the date it last filed a
status (`never` if it never has). Names link: portfolio and program to their rollup, project to its hub.

**Every page takes `?as_of=YYYY-MM-DD`.** Leave it off for today; set it to see the business
exactly as it stood that day. No page reads the clock for anything else.

## 3. Needs attention, and the threat board

The dashboard's right-hand rail ranks everything wanting a decision: assessed threats plus three
data gaps — never filed a status, last status over 14 days old, completeness under 25%. Every red
threat outranks every gap whatever the score. A gap links its fix page; a threat carries sign-off.

<!-- driftless:run page status=200 -->
```text
/threats?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Top threats
```

`/threats` is that ranking in full, 15 cards a page, grouped under the project they belong to and
listing the PMBOK actions the assessment attached. Signing one off — accept, resolved, defer,
reject — records who signed and suppresses it: a decision on the record, not a delete. Both mark
the week-over-week move (▲ worse, ▼ better, – flat, or `new`), the number always beside the arrow.

## 4. The project hub — one project at a glance

<!-- driftless:run page status=200 -->
```text
/projects/1/hub?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
Live threats
```

Process completeness overall and per knowledge area, the earned-value line (EV, CPI, SPI, EAC,
budget), this project's live threats, open risks/issues/change requests, and milestones with a
`slipped` badge on any past its target. The header links process map, wizard, schedule, board and
weekly status. A project with no approved cost baseline says so rather than showing zeros:

<!-- driftless:run page status=200 -->
```text
/projects/3/hub?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
No cost baseline yet — earned value has nothing to measure
```

## 5. Filing the weekly status

<!-- driftless:run page status=200 -->
```text
/projects/1/status?as_of=2026-07-01
```
<!-- driftless:run text -->
```text
stamped from the tasks
```

Pick a RAG — green, amber or red — write a note, save. That is the whole form: **you never type a
percentage.** Completion is computed from the tasks (earned value over budget) and stamped onto the
snapshot, so it can never claim progress the work does not show; each save appends a row, and that append-only series IS the trend line above.

## 6. Reading the numbers

- **RAG** is worst-child-wins: a portfolio is not green while a project under it is red. A fourth
  state, shown as **no data**, means nothing to assess — no baseline, no milestones, no status ever
  filed. It is not a mild amber; it is an empty project.
- **EV** (earned value) is budget × how far the work actually got, at the as-of date.
- **CPI** = EV ÷ actual cost: above 1.0 the work cost less than planned, below 1.0 more.
- **SPI** = EV ÷ planned value: above 1.0 ahead of plan, below 1.0 behind.
- **EAC** = budget ÷ CPI — the likely total cost at this efficiency.
- **`n/a` is never 0.** CPI has no meaning before the first spend, SPI before the baseline
  starts accruing, EAC while CPI is undefined. They read `n/a`, never a flattering zero.
- **Process completeness** is the share of a project's applicable PMBOK processes produced or signed
  off; waived and not-applicable ones are excluded, so an area with nothing to assess reads `n/a`.

## 7. The other screens

<!-- driftless:run page status=200 -->
```text
/projects/1/board
```
<!-- driftless:run page status=200 -->
```text
/projects/1/gantt?as_of=2026-07-01
```
<!-- driftless:run page status=200 -->
```text
/org/heatmap?as_of=2026-07-01&weeks=13
```
<!-- driftless:run page status=200 -->
```text
/org/departments
```
<!-- driftless:run page status=200 -->
```text
/process-map?as_of=2026-07-01
```
<!-- driftless:run page status=200 -->
```text
/pmbok
```
<!-- driftless:run page status=200 -->
```text
/search?q=Fleet
```
<!-- driftless:run text -->
```text
Fleet Modernization
```

**Board** files every task into a column named by its own status — todo, in_progress, blocked, done —
each card carrying workstream, assignee, percent and estimate, the status printed as a word so
"blocked" reads as blocked in greyscale. **Schedule** draws the approved baseline's planned windows
and the milestone diamonds against the as-of as "today", every bar repeated as a table row.
**Capacity** is people × weeks of allocated hours against each person's weekly capacity — 6 weeks
by default, 1 to 26 with `?weeks=`; hours with no approved window land in *Unplaced* rather than
being dropped. **Departments** is headcount and capacity per department. **Process map** is the 49
PMBOK processes as knowledge area × process group, once whole-business (click a cell for the projects
behind it) and once per project, **PMBOK** the same grid as pure reference. **Search** matches
portfolios, programs, projects, workstreams, tasks, risks and issues by name, 10 hits per kind.

## 8. Taking the data with you

Any list address answers `?format=csv` and downloads as a file — the same fields, in the same order:

<!-- driftless:run page status=200 -->
```text
/projects?format=csv
```
<!-- driftless:run text -->
```text
name,portfolio_id,delivery_mode,status_note,program_id,responsible_department_id,id
```

A list hands back at most 500 rows at a time, JSON or CSV. `?limit=` and `?offset=` walk a
longer one a window at a time, and a `?limit=` above 2000 is trimmed to 2000 rather than
refused. Every answer carries its `X-Total-Count`, `X-Limit` and `X-Offset`, so a windowed
list cannot be read as the whole of one.

Dates travel too: `/calendar.ics` subscribes your calendar to every milestone and sprint in the
store, `/projects/{id}/calendar.ics` to one project's — a rename then updates that entry, never duplicates it.

## 9. When a number looks wrong

1. **Check the as-of** — an unexpected figure is usually a page still pinned to a date in its
   address. Drop `?as_of=` to see today.
2. **`n/a` and *no data* are answers, not bugs**; the empty state names what to add.
3. **A stale RAG is a stale status.** The rollup's *Last status* column dates every project's
   most recent snapshot; anything over 14 days old is flagged on the rail.
4. **Percent complete disagrees with the team?** It comes from task progress — fix the percentages
   on the board, never the status form.
5. **Refused?** *"That is a read-only account"* means your role is `viewer`; *"That form expired"*
   means the page sat open too long — reload and resubmit.
6. Still wrong: every write is recorded with its author, so your administrator can trace any figure
   back to the row and the person behind it (`docs/admin-guide.md`).
