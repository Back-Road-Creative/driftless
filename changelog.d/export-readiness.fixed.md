- **Nothing in the tree only makes sense on one machine.** `README.md` and `CLAUDE.md`
  sent the reader to a venv at an absolute path inside one user's home directory, which
  is a dead end for every other reader; both now describe building the venv a clone
  needs, and keeping one outside the checkout is documented as the second setup it is
  rather than as this machine's. A workflow comment named the private sibling repository
  its dedupe shape came from — the reason it is shaped that way was the useful half and
  stays. `tests/test_governance_contract.py` described another repository's scanner, its
  file layout and the fact that its check passes without reading anything; the reasoning
  for why this repo checks its own README survives without naming anyone. `.mailmap` is
  deleted: it folded two personal addresses onto a third, so every address in it was one
  the file itself published. Four guards keep it that way — no tracked file names a home
  directory, none names a repository but this one, the changelog carries no authoring
  scaffold, and no `.mailmap` comes back.
- **A changelog fragment carrying markup is refused rather than published twice.**
  `bin/assemble-changelog.py` validated fragment *names* and never their content, so two
  closing tags from an authoring tool folded into `CHANGELOG.md` and from there into the
  v0.1.0 release notes, where a commit cannot reach them. `read_fragments` is the one
  place preview, `--check` and `--release` all pass, so the check sits there and names
  the file and the tag it refused. Code spans and autolinks are removed before the scan,
  so a tag quoted as an example, a `<https://…>` link and `limit > 100` all still read
  as the prose they are.
