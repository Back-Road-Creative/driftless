#!/usr/bin/env python3
"""Assemble CHANGELOG.md from one-file-per-change fragments in changelog.d/.

Contributors add ``changelog.d/<id>.<type>.md`` and never touch ``CHANGELOG.md``,
so two PRs in flight cannot conflict on the same lines. Folded into the log at
release. A port of rigscore's ``scripts/assemble-changelog.js``.

    bin/assemble-changelog.py                  # preview the Unreleased section
    bin/assemble-changelog.py --check          # validate fragment names/bodies
    bin/assemble-changelog.py --release 0.2.0 [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import NamedTuple

# Keep a Changelog sections, in the order they render.
FRAGMENT_TYPES = ("added", "changed", "deprecated", "removed", "fixed", "security", "docs")
UNRELEASED = "## [Unreleased]"

# A fragment is copied into CHANGELOG.md verbatim and from there into the GitHub release
# body verbatim, so whatever is in it publishes twice and the second copy is not a file
# anyone can fix with a commit. Markup in a fragment is therefore refused HERE, at the one
# place every caller passes, rather than found afterwards in two published artefacts —
# which is how `</content>` and `</invoke>`, closing tags from an authoring tool, reached
# the v0.1.0 release notes.
#
# What survives is everything a changelog bullet legitimately holds. Code spans are removed
# first, so a tag QUOTED as an example (`<content>`) is prose and passes; autolinks are
# removed next, so <https://example.com> and <nobody@example.com> pass. A tag has to start
# with a letter or `!`, which leaves `a < b` and `limit > 100` alone.
CODE_SPAN = re.compile(r"`+[^`]*`+", re.S)
AUTOLINK = re.compile(r"<[A-Za-z][\w+.-]*:[^<>\s]*>|<[^<>\s@]+@[^<>\s@]+>")
MARKUP = re.compile(r"</?[A-Za-z!][^<>]*>")


def check_fragment_body(body: str, name: str) -> None:
    """Raise unless ``body`` is prose a changelog can publish. Markup never is."""
    prose = AUTOLINK.sub(" ", CODE_SPAN.sub(" ", body))
    if (found := MARKUP.search(prose)) is not None:
        raise ValueError(
            f"{name}: markup {found.group(0)!r} in a changelog fragment. This text is "
            "published verbatim in CHANGELOG.md and in the release notes; write it as "
            "prose, or wrap it in backticks if you mean to show the tag itself."
        )


SortKey = tuple[int, int | str]


class Fragment(NamedTuple):
    """One fragment file: PR-number-first sort key, type, body, and where it lives."""

    sort_key: SortKey
    type: str
    body: str
    path: Path


def parse_fragment_name(name: str) -> tuple[SortKey, str]:
    """Split ``<id>.<type>.md`` into a sort key and a validated type."""
    match = re.fullmatch(r"(.+)\.([a-z]+)\.md", name)
    if match is None:
        raise ValueError(f"{name}: expected <id>.<type>.md (e.g. 27.fixed.md)")
    raw_id, fragment_type = match.group(1), match.group(2)
    if fragment_type not in FRAGMENT_TYPES:
        expected = ", ".join(FRAGMENT_TYPES)
        raise ValueError(f"{name}: unknown type {fragment_type!r} — expected one of {expected}")
    return ((0, int(raw_id)) if raw_id.isdigit() else (1, raw_id)), fragment_type


def read_fragments(directory: Path) -> list[Fragment]:
    """Every fragment in ``directory``, PR numbers first in order, then slugs.

    Raises on a name this cannot parse or a body carrying markup — every caller reads
    fragments through here, so neither reaches CHANGELOG.md by any route.
    """
    fragments: list[Fragment] = []
    for path in directory.iterdir():
        if path.name == "README.md" or path.name.startswith("."):
            continue
        sort_key, fragment_type = parse_fragment_name(path.name)
        body = path.read_text(encoding="utf-8").strip()
        check_fragment_body(body, path.name)
        fragments.append(Fragment(sort_key, fragment_type, body, path))
    return sorted(fragments, key=lambda fragment: fragment.sort_key)


def _split_sections(body: str) -> dict[str, str]:
    """Split ``### Heading`` blocks of an Unreleased body into {type: text}."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.split("\n"):
        heading = re.fullmatch(r"### (.+)", line)
        if heading is not None:
            current = heading.group(1).strip().lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def assemble_unreleased(changelog: str, fragments: list[Fragment]) -> str:
    """Fold fragments into the Unreleased section, returning the full file text."""
    start = changelog.find(UNRELEASED)
    if start == -1:
        raise ValueError(f'CHANGELOG.md has no "{UNRELEASED}" section')
    body_start = start + len(UNRELEASED)
    next_release = changelog.find("\n## ", body_start)
    end = len(changelog) if next_release == -1 else next_release

    sections = _split_sections(changelog[body_start:end])
    for fragment in fragments:
        existing = sections.get(fragment.type)
        sections[fragment.type] = f"{existing}\n{fragment.body}" if existing else fragment.body

    rendered = "\n\n".join(
        f"### {t.capitalize()}\n{sections[t]}" for t in FRAGMENT_TYPES if sections.get(t)
    )
    body = f"\n\n{rendered}\n" if rendered else "\n"
    return changelog[:body_start] + body + changelog[end:]


# GitHub refuses a release body over 125,000 characters (HTTP 422). Mirrors the cap in
# .github/workflows/release.yml, which also reserves room for the truncation notice and
# image footer it appends — that workflow cap still applies and still truncates; this is
# a cheap warning at fold time so an oversize section is caught before the tag exists,
# not after (v0.4.0's ~145 KB section reached the API before this check existed).
RELEASE_BODY_LIMIT = 125_000 - 1_500


def render_release(
    changelog: str,
    fragments: list[Fragment],
    version: str,
    day: str,
    allow_oversize: bool = False,
) -> str:
    """Stamp the assembled Unreleased section as ``version``, and open a fresh one."""
    assembled = assemble_unreleased(changelog, fragments)
    stamped = assembled.replace(UNRELEASED, f"## [{version}] - {day}", 1)
    released = stamped.replace(f"## [{version}]", f"{UNRELEASED}\n\n## [{version}]", 1)
    if not allow_oversize:
        heading = f"## [{version}] - {day}"
        start = released.index(heading) + len(heading)
        next_heading = released.find("\n## ", start)
        section = released[start:] if next_heading == -1 else released[start:next_heading]
        size = len(section.encode("utf-8"))
        if size > RELEASE_BODY_LIMIT:
            raise ValueError(
                f"the {version} release section is {size:,} bytes, over GitHub's "
                f"release-body limit ({RELEASE_BODY_LIMIT:,} bytes, after the room the "
                "workflow reserves for its truncation notice). The workflow will still "
                "truncate it at publish time; pass --allow-oversize to release anyway."
            )
    return released


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    """Run the tool against ``root`` (the checkout it lives in, unless a test says else)."""
    parser = argparse.ArgumentParser(description="Assemble CHANGELOG.md from changelog.d/.")
    parser.add_argument("--check", action="store_true", help="validate fragments and exit")
    parser.add_argument("--release", metavar="VERSION", help="fold fragments in as VERSION")
    parser.add_argument(
        "--allow-oversize",
        action="store_true",
        help="skip the GitHub release-body size check for --release",
    )
    # Parsed as a real date here rather than checked later: releasing unlinks every
    # fragment, and a stamp like `- not-a-date` is only discovered once they are gone.
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="release date (default: today)",
    )
    args = parser.parse_args(argv)

    repo_root = root if root is not None else Path(__file__).resolve().parent.parent
    changelog_path = repo_root / "CHANGELOG.md"
    try:
        fragments = read_fragments(repo_root / "changelog.d")
    except ValueError as error:
        print(f"changelog: {error}", file=sys.stderr)
        return 1

    if args.check:
        print(f"changelog: {len(fragments)} fragment(s) OK")
        return 0

    changelog = changelog_path.read_text(encoding="utf-8")
    day = args.date if args.date is not None else date.today()
    try:
        if args.release is None:
            preview = assemble_unreleased(changelog, fragments)
            start = preview.find(UNRELEASED)
            next_release = preview.find("\n## ", start + len(UNRELEASED))
            print(preview[start:] if next_release == -1 else preview[start:next_release])
            return 0
        # Rendered before anything is written or unlinked: a changelog this cannot fold
        # into is a message, not a traceback over half-removed fragments.
        released = render_release(
            changelog, fragments, args.release, day.isoformat(), args.allow_oversize
        )
    except ValueError as error:
        print(f"changelog: {error}", file=sys.stderr)
        return 1

    changelog_path.write_text(released, encoding="utf-8")
    for fragment in fragments:
        fragment.path.unlink()
    print(f"changelog: released {args.release} ({len(fragments)} fragment(s) folded in, removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
