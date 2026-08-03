# changelog.d — one file per change

**Do not edit `CHANGELOG.md` in a pull request.** Add a fragment here instead:

```
changelog.d/<id>.<type>.md      e.g. changelog.d/27.fixed.md
```

- `<id>` — the PR (or issue) number; a short kebab-case slug when there is none yet.
- `<type>` — one of `added`, `changed`, `deprecated`, `removed`, `fixed`,
  `security`, `docs`. An unknown type fails `--check` and the test suite
  (`tests/test_assemble_changelog.py`) rather than silently vanishing at release.
- The body is the markdown list item(s) exactly as they should appear under
  `### <Type>`, starting with `- `.
- The body is **prose, not markup**. A fragment is copied into `CHANGELOG.md`
  and from there into the GitHub release notes verbatim, and a release body is
  not a file a later commit can fix, so an HTML or XML tag is refused here
  instead — by name, at `--check` and in the suite. Backtick it if you mean to
  show the tag itself; autolinks like `<https://example.com>` and comparisons
  like `a > b` are unaffected.

Why: every PR used to append to the same `### Added` list, so any two PRs open
at once collided on the same lines. One file per change means two PRs never
touch the same line, so the conflict cannot happen — locally or on GitHub.

Preview what the next release will say, or validate the fragments:

```bash
python3 bin/assemble-changelog.py           # preview
python3 bin/assemble-changelog.py --check   # validate names/bodies
```

Maintainers, at release time — folds every fragment into `CHANGELOG.md` under
the new version heading, opens a fresh `## [Unreleased]`, and deletes the
consumed fragments. Bump `pyproject.toml` / `driftless.__version__` in the same
commit:

```bash
python3 bin/assemble-changelog.py --release 0.2.0
```
