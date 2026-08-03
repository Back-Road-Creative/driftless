# driftless — repo-root instructions

## Merging

JP merges manually; agents never merge — open the PR and stop.

A pull request lands only on a **complete green** CI run. Red, pending and
incomplete all refuse, and nothing merges an unfinished run. More than one ready
PR merges in one sitting, in an order that keeps overlapping branches apart.

## Service venv and tests

- Build the venv the clone needs, per README *Development*: `python3 -m venv .venv`
  then `.venv/bin/pip install ".[dev]"`. Nothing here is committed, so a checkout
  starts without one.
- Invoke through `.venv/bin/python -m pytest`, never the console scripts in the
  venv's `bin/`: a moved or copied venv leaves their shebangs pointing at a path
  that no longer exists and they exit 127. A `pytest` found on `PATH` outside the
  venv dies in `tests/conftest.py` on `import sqlalchemy` with rc=4 — reads like a
  missing dependency and is not one.
- Coverage floor: read `--cov-fail-under` out of `pyproject.toml`'s
  `[tool.pytest.ini_options] addopts`. Never restate it here — this line carried a
  number the setting had already left behind, at a line reference that had moved,
  and a stale floor reads as a green suite that is not.
- The passing-test count moves every merge — measure it fresh, never hardcode
  it in a doc, check, or PR description.
- Diff cap ≤300 SUM (insertions+deletions): `git diff --numstat
  origin/master...HEAD | awk '{i+=$1;d+=$2} END {print i+d}'` — never
  `--shortstat`.

## Compose-gate

Per-PR CI runs against master as it was at PR-open and does not re-run when
master moves, so several green PRs can still break together on merge — the
compose files and the guards that parse them are a common casualty. Before more
than one PR is merged in a sitting, merge the ready branches into one worktree
and run the full suite there: that is the only run that sees the combination.
