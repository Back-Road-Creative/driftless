# Superseded and affirmed decisions

**Status:** accepted (2026-08-13)

## Decision

Some in-code decisions from earlier work stay right as written; others no
longer hold given what Driftless does today. Each entry below quotes the
decision as the code states it, then gives the verdict: **affirmed** (still
right, kept as is), **superseded** (reversed), or **amended** (kept for what
it was right about, extended for what it left out).

## Pagination boundary

`driftless/api/app.py`'s list routes clamp `?limit` to a server ceiling
rather than reject an out-of-range value, and the comment beside the clamp
gives the reason: "Clamped rather than refused: the caller gets the most the
server will serve, plus headers saying what is left, where a 422 is a dead
end." `tests/test_api_list_bounds.py` pins the behaviour — a limit past the
ceiling clamps down, never errors, and the clamp only ever narrows what a
caller asked for.

**Verdict: affirmed.** A limit outside range is still a request the server
can usefully answer with something. Once declarative filters exist on these
routes, though, an *unknown* filter parameter is a different kind of mistake
and gets a different answer: rejected, not clamped. A clamp is right for a
value out of range; it is wrong for a name nobody on the server reads,
because silently ignoring a filter the caller typed is a wrong answer
presented as a right one.

## Administration boundary

`driftless/api/secure.py` states the decision directly: "There is
deliberately no admin-only tier: user management is the `driftless user`
CLI, and a tier nothing needs yet would be a guess." The README's role table
backs it up — `admin` and `contributor` read and write identically; only
`viewer` differs, refused before the route runs.

**Verdict: superseded.** The sign-off ledger — the one write today that is a
governance act rather than an edit, appended by both `POST /sign-offs` and the
`POST /sign-off` browser form that calls it directly rather than assembling
its own row — moves behind an admin-only tier (`secure._PRIVILEGED_PATHS`),
derived and compared as an exact set against the live route table so neither
address can drift out of it unnoticed. Two roles that behave identically on
every OTHER route are still not a boundary there: configuration and user
administration keep the surfaces they already had — the `driftless user` CLI
for the latter, no HTTP write of its own for the former — so nothing beyond
the ledger yet claims a distinction this table does not enforce.

## Snapshot boundary

`bin/driftless-snapshot-pages.py` argues for rendered HTML over a headless
browser: "a decision, not a shortcut... A browser would add a heavyweight CI
dependency whose only new information is font rasterization." The
byte-diffable snapshots this produces are the fast first line for every page
Driftless ships.

**Verdict: amended, not reversed.** The snapshot suite stays exactly that —
the fast, deterministic floor that catches a changed number, a moved
element, or a broken template before anything renders in a browser. What it
cannot answer is what it says about itself: `tests/test_web_responsive.py`'s
own docstring names the gap — "WHAT THIS DOES NOT PROVE: that it *looks*
right at 768px. No test here renders a viewport" — and `tests/test_web_a11y.py`
only "COMPUTES the WCAG ratio" of colour tokens and "asserts on the HTML that
shipped", never on a page a browser has actually laid out. A small rendered
tier is added for exactly what source text cannot answer: viewport layout at
two widths, focus order under keyboard-only navigation, and the
reduced-motion path, over five representative pages, not the whole surface.
The snapshot suite is not replaced by it; the two answer different
questions.

## No-JavaScript boundary

`driftless/web/static/driftless.js` states the contract at its own head:
"Every page works without it: forms POST and the server re-renders the whole
page." The controllers repeat it where a form actually posts —
`driftless/web/status.py`, the weekly-status edit loop, opens with "The page
degrades without JavaScript; `static/driftless.js` only makes the swap feel
instant."

**Verdict: affirmed, as an invariant rather than a goal.** It already holds
— every page in the suite is exercised through `TestClient`, which never
executes JavaScript, so every passing form-submission test already is a
no-JS run of that page. `tests/test_web_swap_script.py` pins the enhancement
layer itself the same way, from both ends, because "the suite runs no
browser and no Node." What this decision changes is only the framing: the
invariant gets a regression floor that fails the day a template starts
depending on the script to function, not a project with a plan and a
deadline.
