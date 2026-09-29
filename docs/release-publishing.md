# Publishing a release

Development and publication happen in two different repositories, and confusing
them ships work where nobody can read it.

- The **archive** is private: every branch, every pull request, every review. It
  is the `origin` a development clone has, and its history is never published.
- **`Back-Road-Creative/driftless`** is public. One snapshot of the tree per
  release, and the only place a reader looks. The tag, the release object, the
  CI run and the GHCR image are all made **there**.

History does not move between them. The public tree is re-snapshotted per
release, which is what keeps the branch history private while the artefacts a
reader needs — a tag they can check out, notes, an image they can pull — are
public. It is also why a tag pushed only to the archive is not a release: the
release object it produces sits behind the same wall the history does.

`.github/workflows/release.yml` carries no repository guard, so it also runs
here: pushing a `vX.Y.Z` tag to the archive creates an archive-side GitHub
release exactly as described above, just one nobody outside this repository
can see. Check `gh release list --repo Back-Road-Creative/driftless` for which
tags have actually reached the public repository — that list only grows, so
naming it here would go stale the next time it does.

## The leak scan — the last gate before anything is public

Because the public tree is a fresh `git archive` snapshot each release, not a
shared history, nothing here is ever removed from the public side except by
the next snapshot deleting it — a leaked file published once stays reachable
in the public repository's own history forever, even after a later release
drops it. The scan below is the same one, run in three places, each catching
what the last one could not:

1. **This repo's own CI** (`ci.yml`'s `quality` job) runs it on every pull
   request into `master` or `staging`, every push to `staging`, and the nightly
   run, under the name this tree publishes as (`Back-Road-Creative/driftless`)
   rather than the name it is checked out as. Caught here it costs an edit to a
   branch nobody outside this repository has seen yet.
2. **The release workflow's `Leak-scan the snapshot before it is published`
   step** runs it again on the exact tree the mirror step commits — the same
   `git archive` of the tag, staged the same way — and a finding fails that
   step, so the mirror step never starts and nothing reaches the public
   repository at all. This is the one place in the pipeline it is fully
   authoritative: everything upstream of it can be wrong and this step still
   stops the publish. It is a step of its own so the scanner never runs beside
   the public push token: the workflow's shell reads the public-repo list and
   the scanner runs with no token in its environment.
3. **The public repository's own `leak-scan.yml`** answers a pull request or a
   push to any branch there — a defence against something reaching the public
   repository by a path other than this one's release workflow (a direct push,
   a manually opened PR), not the primary gate.

Both callers in this repository fetch the scanner at the commit pinned as
`LEAK_SCAN_REF` in `ci.yml` and in the release scan step (a test holds the two
equal), never the shared repository's moving `main`. Moving the pin is a pull
request here, reviewed like any other code that runs in the release job. A line
the scanner flags but that is safe to publish goes in
`.github/leak-scan-allowlist.json`, one entry per flagged line: its `match` is
that line's whole flagged text, so the entry cannot exempt a new line that only
shares a word with it.

`leak-scan.yml` has to live in THIS repository, not only the public one,
because of the same asymmetry the snapshot mechanism exists to manage: the
public tree is deleted and rebuilt from this tree's own files every release, so
a workflow that exists only on the public side is exactly the kind of file that
disappears the moment a snapshot does not carry it forward — and a workflow
this repository never runs cannot catch anything before publish, only after.

This was, until the automation below existed, a documented manual procedure with
no script on purpose: it ran a few times a year, each run wanted a human looking
at the diff before the push, and a script would have been one more thing to keep
true. Sections 1-4 below are still the fallback when the automation is skipped
(no token installed) or when a run needs a human's eyes before it ships — the
human review point moves to the archive-side pull request and tag, not away
entirely.

## Before you start

- The changelog fold has merged to the archive's `master`
  (`bin/assemble-changelog.py --release <version>`), `pyproject.toml` and
  `driftless/__init__.py` carry that version, and its CI is green on that commit.
- You can push to `Back-Road-Creative/driftless`.

## 1. Snapshot the tree

`git archive` writes exactly the tracked tree at one commit, so the snapshot
cannot pick up an untracked file the archive happens to have. The `git rm` first
is what makes a **deletion** propagate: without it a file dropped since the last
release would survive in the public tree forever.

```sh
ARCHIVE=/path/to/archive-checkout           # the private repository
PUBLIC=/path/to/public-checkout             # Back-Road-Creative/driftless
VERSION=0.2.0
SHA="$(git -C "$ARCHIVE" rev-parse master)"

cd "$PUBLIC" && git switch master && git pull --ff-only
git rm -rq .
git -C "$ARCHIVE" archive "$SHA" | tar -x -C "$PUBLIC"
git add -A
git status                                  # read this before committing
```

Before committing that snapshot, re-run `git archive` against the source
commit and diff its file list against the checkout you just wrote — this
catches a partial `git rm -rq .` or a stale `$PUBLIC` checkout while it is
still local and nothing has been tagged yet. The `grep` drops the `dir/` entries
`tar -tf` lists and `git ls-files` never does:

```sh
diff <(git -C "$ARCHIVE" archive "$SHA" | tar -tf - | grep -v '/$' | sort) \
     <(cd "$PUBLIC" && git ls-files | sort)
```

Then run the leak scan the release workflow runs, on the same snapshot, with the
scanner at the same pinned commit (`LEAK_SCAN_REF` in `.github/workflows/ci.yml`).
Nothing is committed until it prints `clean.`:

```sh
TOOL="$(mktemp -d)"
git -C "$TOOL" init -q
git -C "$TOOL" fetch -q --depth 1 https://github.com/Back-Road-Creative/.github.git <LEAK_SCAN_REF>
git -C "$TOOL" checkout -q FETCH_HEAD
python3 "$TOOL/scripts/leak_scan.py" --repo-root "$PUBLIC" --self-name Back-Road-Creative/driftless
```

## 2. Commit, push, tag

The tag goes on the public repository and nowhere else. Pushing it is what
starts everything: `release.yml` publishes the notes it reads out of
`CHANGELOG.md`, and `docker-publish.yml` builds and pushes the image — twice
over, since `release.yml` dispatches it as well for the case where the tag was
not pushed by a person; its concurrency group collapses the two to one image.

Two things `release.yml` refuses or adjusts on its own: the tag must name the
version `pyproject.toml` and `driftless/__init__.py` declare, and notes longer
than GitHub's 125,000-character release-body limit are cut at a line boundary
with a notice naming the full `CHANGELOG.md` section (v0.4.0's section was
145 KB and the API answered 422). If a tag's push run failed, do not re-run it:
a re-run uses the tag's own copy of the workflow. Dispatch the current one
for the existing tag instead — this edits the release if the earlier run
already published one, rather than failing with "release already exists":

```sh
gh workflow run release.yml --repo Back-Road-Creative/driftless --ref master -f tag="v${VERSION}"
```

Otherwise, the normal path:

```sh
git commit -m "release: v${VERSION} (source ${SHA})"
git push origin master
git tag -a "v${VERSION}" -m "v${VERSION}"
git push origin "v${VERSION}"
```

## 3. Check that a stranger can get it

Each of these is a different failure, which is why all three are asked:

```sh
gh release view "v${VERSION}" --repo Back-Road-Creative/driftless
gh run list --repo Back-Road-Creative/driftless --workflow docker-publish.yml --limit 3
docker pull "ghcr.io/back-road-creative/driftless:${VERSION}"
```

A GHCR package is not world-readable just because the repository is. On the
**first** publish, check the package's visibility under the organisation's
Packages and make it public if it is not — a private package fails everyone
else's `docker pull` with a message that reads like a tag that was never
pushed.

Nothing above has run yet: `Back-Road-Creative/driftless` holds no tags and no
releases, so the first time this procedure is followed is the first time
`docker-publish.yml` runs at all. Expect to fix something on that run, and fix
it in the archive.

## 4. Update the public showcase

Back Road Creative's public site carries a static demo built from Driftless by
`bin/driftless-showcase.py --source v<version>` (`docs/testing-and-quality-gates.md`),
not from whatever `master` happens to hold at showcase time — a bundle left
unregenerated silently drifts from what the tag actually shipped. Once the tag
above is pushed and `docker-publish.yml` has gone green, from the
`headlessmode` checkout:

```sh
SITE_BIN="$PWD/bin"   # the headlessmode checkout's bin/, not this repository's
bash "$SITE_BIN/driftless-bundle-regen.sh" "v${VERSION}"
bash "$SITE_BIN/driftless-prod-smoke.sh" "v${VERSION}"
```

## Automated snapshot and showcase asset

`.github/workflows/release.yml`, run from the **archive** side on every pushed
tag, now performs sections 1, 2 and 4 above by itself, whenever a fine-grained
push token for the public repository is installed as the archive secret
`DRIFTLESS_PUBLIC_TOKEN` (contents: write, releases: write, and
pull-requests: write for the master pull request below; scoped to
`Back-Road-Creative/driftless` alone — nothing else, and never an
organization-wide token).

**The mechanism is still the snapshot, not a shared-history push.** History
still does not move between the two repositories: the workflow clones the
public repository fresh, `git rm -rq .` + `git archive <tag> | tar -x` +
`git add -A` — the exact commands section 1 gives a human to run by hand — then
commits that snapshot on top of the public `master` and pushes it to a
`release/<tag>` branch, tags it, and publishes the release and asset from the
tag. It never runs `git push` against the archive's own ref, so no branch, pull
request or commit message from this repository is ever transmitted to the
public one; the public repository's history grows by one snapshot commit per
release, same as it always has.

**Public `master` moves only through a pull request a person merges.** The
self-hosted runner's `git` refuses every push to `main`/`master`, with no
override, so the workflow's last act is to open a pull request from
`release/<tag>` to `master`. The site reads the tag's release asset, not
`master`, so the release is complete for readers before that merge. Opening the
pull request is allowed to fail: if the token lacks pull-requests: write, the
run ends with a `::warning::` carrying the compare link to open it by hand. A
re-dispatch replaces the `release/<tag>` branch and reuses a tag already on the
public repository rather than moving it.

The workflow also builds the showcase bundle with `bin/driftless-showcase.py
--source <tag>` — the same generator `driftless-bundle-regen.sh` calls,
validated the same way that script validates a bundle before trusting it — and
uploads it as `driftless-showcase-<tag>.tar.gz` on both the archive's own
release (always) and the public one (when the token is installed). The site's
`product-sync.yml` reads that asset instead of a private-repo checkout, so `repo`
in the site's `data/systems.json` continues to name a repository a reader can
actually open.

The generator imports the `driftless` package, so the workflow first installs
this checkout's `.[dev]` set, constrained by `requirements.lock`, into a throwaway
venv under `$RUNNER_TEMP` (uv when the runner has it, `python3 -m venv` otherwise —
the same install `ci.yml`'s Tests job runs) and runs the
generator with that venv's interpreter. The runner's own `python3` has never
installed the package; running the generator with it fails on
`ModuleNotFoundError` before any asset exists.
The pages render through `fastapi.testclient`, which needs `httpx` from the `dev`
extra, and an install that ignores the lock can resolve a newer `starlette` that
refuses to import at all.

**When the token is absent** the mirror step is skipped with a visible
`::warning::` and the run still succeeds — the archive-side release and its
asset are published either way. Sections 1-4 above remain the fallback for that
case, and for the rare run that wants a human looking at the diff before
anything reaches the public repository; the review point for the automated path
is the archive-side pull request and tag rather than a manual push step.

`driftless-bundle-regen.sh` wraps the `driftless-showcase.py` invocation and
commits the refreshed bundle; `driftless-prod-smoke.sh` is the production
smoke run against it. Both are tracked in the `headlessmode` repository.
