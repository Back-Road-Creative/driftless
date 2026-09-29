"""Every ``TT_CATALOG`` member must be reachable from a process, or be an
explicitly named Driftless extension.

``TT_CATALOG`` is also the vocabulary the recommendation engine draws
``Action.pmbok_tt`` from (see ``driftless.pmbok.tt``'s module docstring), so a
member no process ever names is a technique a reader can never be routed to —
dead vocabulary at best, and at worst a name an evaluator recommends by hand
with no ITTO backing it. This test computes reachability from the live
catalog rather than a hardcoded list of names, so a newly orphaned member
turns it red the moment it is added, not the moment someone notices.
"""

from driftless.pmbok import catalog
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.tt import EXTENSION_REASONS, EXTENSIONS, TT_CATALOG


def test_every_catalog_member_reaches_a_process_or_is_a_named_extension() -> None:
    reachable = set().union(*(p.tools_techniques for p in catalog.PROCESSES))
    unrouted = TT_CATALOG - reachable - EXTENSIONS
    assert not unrouted, (
        f"{sorted(unrouted)} are in TT_CATALOG but no process names them and they "
        "carry no extension marker — attach each to the process(es) that use it per "
        "PMBOK-6, or add it to EXTENSIONS with a reason the edition does not tie it "
        "to a process"
    )


def test_extensions_are_a_subset_of_the_catalog() -> None:
    """An extension marker on a name outside the catalog would mark nothing."""
    assert EXTENSIONS <= TT_CATALOG


def test_critical_chain_method_is_a_named_extension() -> None:
    """PMBOK-6 does not tie this technique to a process ITTO table; Driftless adds
    it to the vocabulary anyway because the product needs it, and marks it as an
    extension rather than silently expanding the edition's vocabulary."""
    assert "critical_chain_method" in TT_CATALOG
    assert "critical_chain_method" in EXTENSIONS


def test_no_extension_is_reachable_from_a_process() -> None:
    """An extension marker that outlives the gap it covers stops meaning anything: the
    moment a process names the technique, PMBOK-6 does tie it to an ITTO table, and
    leaving it here would strip the edition string off a definition that has earned it.
    Walks every member rather than checking the one extension that exists today."""
    reachable = set().union(*(p.tools_techniques for p in catalog.PROCESSES))
    stale = sorted(EXTENSIONS & reachable)
    assert not stale, (
        f"{stale} are marked as Driftless extensions but a process names them — "
        "PMBOK-6 ties each to a process after all, so delete the EXTENSIONS entry "
        "and let the definition carry the edition it has earned"
    )


def test_no_extension_cites_a_pmbok_clause() -> None:
    """A definition sourced as an extension says no PMBOK-6 clause defines it, so it may
    not also cite one — the contradiction is invisible to the provenance tests, which
    never look at ``further_reading``. Walks every member, not the one extension today."""
    contradictory = sorted(
        f"{key}: {TECHNIQUES[key].further_reading}"
        for key in EXTENSIONS
        if TECHNIQUES[key].further_reading
    )
    assert not contradictory, (
        "these are marked as Driftless extensions — no PMBOK-6 clause defines them — "
        "yet they cite one; drop the EXTENSIONS entry if the clause is real, or drop "
        "the citation:\n" + "\n".join(contradictory)
    )


def test_every_extension_names_a_real_technique_and_a_reason() -> None:
    """An extension is an exemption from the edition's vocabulary, so it carries a
    written reason a test can require — not a comment nothing reads."""
    for key, reason in sorted(EXTENSION_REASONS.items()):
        assert key in TT_CATALOG, f"{key} is marked an extension but is not in TT_CATALOG"
        assert reason.strip(), f"{key} is marked an extension with no reason given"
