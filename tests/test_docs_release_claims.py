"""Docs must not claim, in the present tense, that a container image is
already pushed to GHCR — no public tag exists yet (2026-09-02). A claim is
only true once it names the *public* repository as the thing being pushed to.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

UNCONDITIONAL_PUSH_CLAIM = re.compile(r"pushes .*ghcr|is pushed to ghcr", re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    # Good enough for prose docs: split on sentence-ending punctuation followed
    # by whitespace. A false split just makes the check stricter, never looser.
    return re.split(r"(?<=[.!?])\s+", text)


def _offending_sentences(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [
        sentence
        for sentence in _sentences(text)
        if UNCONDITIONAL_PUSH_CLAIM.search(sentence) and "public" not in sentence.lower()
    ]


def test_no_unconditional_ghcr_push_claim_in_readme() -> None:
    offenders = _offending_sentences(REPO_ROOT / "README.md")
    assert not offenders, f"unconditional ghcr-push claim(s) in README.md: {offenders}"


def test_no_unconditional_ghcr_push_claim_in_operations() -> None:
    offenders = _offending_sentences(REPO_ROOT / "OPERATIONS.md")
    assert not offenders, f"unconditional ghcr-push claim(s) in OPERATIONS.md: {offenders}"


def test_no_unconditional_ghcr_push_claim_in_changelog() -> None:
    offenders = _offending_sentences(REPO_ROOT / "CHANGELOG.md")
    assert not offenders, f"unconditional ghcr-push claim(s) in CHANGELOG.md: {offenders}"


def test_release_publishing_doc_has_pre_tag_diff_step() -> None:
    text = (REPO_ROOT / "docs" / "release-publishing.md").read_text(encoding="utf-8")
    step_1 = text.split("## 1.", 1)[1].split("## 2.", 1)[0]
    step_3 = text.split("## 3.", 1)[1].split("## 4.", 1)[0]
    assert "git archive" in step_1, (
        "the public-tree-vs-source diff belongs in step 1, before anything is tagged"
    )
    assert "git archive" not in step_3, (
        "step 3 is post-publish checks only; the diff runs before the tag exists"
    )


def test_release_publishing_doc_names_showcase_regen_scripts() -> None:
    text = (REPO_ROOT / "docs" / "release-publishing.md").read_text(encoding="utf-8")
    assert "driftless-bundle-regen" in text
    assert "driftless-prod-smoke" in text


def test_release_publishing_doc_names_the_public_mirror_token_and_its_scope() -> None:
    """The automated mirror (release.yml) needs a reader to know the secret's name
    and that it is scoped narrowly -- never an organization-wide credential."""
    text = (REPO_ROOT / "docs" / "release-publishing.md").read_text(encoding="utf-8")

    assert "DRIFTLESS_PUBLIC_TOKEN" in text
    assert "fine-grained" in text.lower() or "scoped" in text.lower()


def test_release_publishing_doc_still_says_history_never_moves_between_the_repos() -> None:
    """Automating the snapshot must not quietly drop the privacy guarantee the
    manual procedure exists to keep: the public repository never receives this
    repository's own commit history, only a fresh snapshot commit per release."""
    text = (REPO_ROOT / "docs" / "release-publishing.md").read_text(encoding="utf-8")

    assert "History does not move between them" in text or "history does not move" in text.lower()
    assert "snapshot" in text.lower()
