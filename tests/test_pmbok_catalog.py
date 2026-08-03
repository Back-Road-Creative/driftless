"""The ITTO catalog's integrity is pinned here, not left to inspection.

The catalog is reference data authored across ten modules; these property tests
are its contract. They fix the PMBOK-6 counts (49 total, and the per-area and
per-group distributions), that every process is uniquely numbered and validly
placed, and — the load-bearing one — that every input, output and technique a
process names is drawn from the closed ``ARTIFACT_KINDS`` / ``TT_CATALOG`` sets,
so a process can never reference an artifact or technique the rest of the system
does not understand.

The last three tests close the mirror of that rule, on the store's side. A resolver
(``driftless.pmbok.mapping.RESOLVERS``) is what makes an artifact kind *visible*: the
state engine walks a process's outputs, asks the store for each, and a process with no
resolvable output drops out of every completeness figure. So two ways of adding a
resolver do nothing and say nothing — keying it to a name ``ARTIFACT_KINDS`` does not
hold, or to a kind no process names as an output. Both are real and both are correct
today, which is exactly why they are written down as **exact sets** with reasons: the
next one is a decision someone has to make, not a diff nobody notices.
"""

from driftless.pmbok import ARTIFACT_KINDS, TT_CATALOG, catalog, mapping
from driftless.pmbok.model import KnowledgeArea, Process, ProcessGroup

EXPECTED_PER_AREA = {
    KnowledgeArea.INTEGRATION: 7,
    KnowledgeArea.SCOPE: 6,
    KnowledgeArea.SCHEDULE: 6,
    KnowledgeArea.COST: 4,
    KnowledgeArea.QUALITY: 3,
    KnowledgeArea.RESOURCE: 6,
    KnowledgeArea.COMMUNICATIONS: 3,
    KnowledgeArea.RISK: 7,
    KnowledgeArea.PROCUREMENT: 3,
    KnowledgeArea.STAKEHOLDER: 4,
}  # sums to 49

# Resolver keys ARTIFACT_KINDS does not hold, each with the reason the store answers
# for a name the catalog cannot say. Asserted as an exact set below.
RESOLVED_OUTSIDE_THE_VOCABULARY = {
    "status_report": (
        "a status snapshot is a *record*, not a PMBOK artifact. PMBOK's nearest thing is "
        "the work performance report, and docs/pmbok-mapping.md lists that among the "
        "artifacts this tool deliberately never stores — it is computed on read. The "
        "resolver exists so the Communications evaluator and the wizard can ask 'is "
        "reporting current?' under the same as-of and staleness rules as every artifact; "
        "it is reached by name, never through a process's outputs. Putting the name in "
        "ARTIFACT_KINDS would not change that: no process would name it either way"
    ),
}

# Resolver keys no process names as an OUTPUT. Producing one moves no process out of
# NOT_STARTED, so each needs the reason that is correct. Asserted as an exact set below.
RESOLVED_BUT_NEVER_PRODUCED = {
    "enterprise_environmental_factors": (
        "an enterprise input, never a project output: PMBOK processes consume EEFs and "
        "none produces them, so this resolver's whole job is answering the wizard's "
        "'does this input exist yet?' — moving no state is the correct behaviour"
    ),
    "organizational_process_assets": (
        "the same shape: OPAs are an organisational input that every process reads and "
        "no process produces, so it answers input-readiness and never a process's state"
    ),
    "status_report": RESOLVED_OUTSIDE_THE_VOCABULARY["status_report"],
}

EXPECTED_PER_GROUP = {
    ProcessGroup.INITIATING: 2,
    ProcessGroup.PLANNING: 24,
    ProcessGroup.EXECUTING: 10,
    ProcessGroup.MONITORING: 12,
    ProcessGroup.CLOSING: 1,
}  # sums to 49


def test_the_catalog_has_exactly_49_processes() -> None:
    assert len(catalog.PROCESSES) == 49


def test_the_per_area_counts_match_pmbok_6() -> None:
    counts = {area: len(catalog.by_area(area)) for area in KnowledgeArea}
    assert counts == EXPECTED_PER_AREA


def test_the_per_group_counts_match_pmbok_6() -> None:
    counts = {group: len(catalog.by_group(group)) for group in ProcessGroup}
    assert counts == EXPECTED_PER_GROUP


def test_every_process_id_is_unique() -> None:
    ids = [p.id for p in catalog.PROCESSES]
    assert len(ids) == len(set(ids))


def test_every_process_is_validly_placed_and_typed() -> None:
    for p in catalog.PROCESSES:
        assert isinstance(p, Process)
        assert isinstance(p.group, ProcessGroup)
        assert isinstance(p.area, KnowledgeArea)
        assert p.name and p.id


def test_every_input_and_output_is_a_known_artifact_kind() -> None:
    for p in catalog.PROCESSES:
        unknown = (set(p.inputs) | set(p.outputs)) - ARTIFACT_KINDS
        assert not unknown, f"{p.id} {p.name} references unknown artifact kinds: {sorted(unknown)}"


def test_every_technique_is_in_the_tt_catalog() -> None:
    for p in catalog.PROCESSES:
        unknown = set(p.tools_techniques) - TT_CATALOG
        assert not unknown, f"{p.id} {p.name} references unknown techniques: {sorted(unknown)}"


def test_every_process_produces_at_least_one_output() -> None:
    for p in catalog.PROCESSES:
        assert p.outputs, f"{p.id} {p.name} has no outputs"


def test_every_optional_output_is_a_declared_subset_of_outputs() -> None:
    """An optional mark sits on an output the process actually names — marking a
    kind outside ``outputs`` would silently mark nothing."""
    for p in catalog.PROCESSES:
        stray = set(p.optional_outputs) - set(p.outputs)
        assert not stray, f"{p.id} {p.name} marks non-outputs optional: {sorted(stray)}"


def test_every_planning_process_uses_at_least_one_technique() -> None:
    """A planning process with no tools or techniques is almost certainly a stub."""
    for p in catalog.by_group(ProcessGroup.PLANNING):
        assert p.tools_techniques, f"{p.id} {p.name} names no techniques"


def test_every_resolver_names_a_known_artifact_kind_or_states_why_not() -> None:
    """The mirror of the input/output rule: the store must not answer for a name the
    catalog has no way to say, or the two vocabularies drift apart in silence."""
    outside = set(mapping.RESOLVERS) - ARTIFACT_KINDS
    assert outside == set(RESOLVED_OUTSIDE_THE_VOCABULARY), (
        f"{sorted(outside - set(RESOLVED_OUTSIDE_THE_VOCABULARY))} resolve against the "
        "store under a name ARTIFACT_KINDS does not hold, so no process can reference "
        "them and they move no process's state — key the resolver to a catalog kind, or "
        "write down here why it belongs outside. Stale reasons: "
        f"{sorted(set(RESOLVED_OUTSIDE_THE_VOCABULARY) - outside)}"
    )
    assert all(len(reason) > 60 for reason in RESOLVED_OUTSIDE_THE_VOCABULARY.values())


def test_every_resolver_moves_some_process_state_or_states_why_not() -> None:
    """A resolver for a kind no process produces changes no state map. Correct for an
    input-only kind, an oversight for anything else — so the exceptions are named."""
    produced = {kind for p in catalog.PROCESSES for kind in p.outputs}
    inert = set(mapping.RESOLVERS) - produced
    assert inert == set(RESOLVED_BUT_NEVER_PRODUCED), (
        f"{sorted(inert - set(RESOLVED_BUT_NEVER_PRODUCED))} have a resolver but no "
        "process names them as an output, so producing one leaves every process where it "
        "was and the work is invisible to completeness — name the kind as an output in "
        "the catalog, or write down here why it is inert. Stale reasons: "
        f"{sorted(set(RESOLVED_BUT_NEVER_PRODUCED) - inert)}"
    )
    assert all(len(reason) > 60 for reason in RESOLVED_BUT_NEVER_PRODUCED.values())


def test_the_resolver_guards_are_not_vacuous() -> None:
    """Both guards read live code, so an emptied registry or a catalog that named no
    outputs would otherwise pass them forever."""
    assert {"scope_baseline", "risk_register", "issue_log"} <= set(mapping.RESOLVERS)
    produced = {kind for p in catalog.PROCESSES for kind in p.outputs}
    assert {"risk_register", "issue_log"} <= produced


def test_every_artifact_kind_is_tracked_or_carries_a_disposition() -> None:
    """The vocabulary partitions exactly: every kind has a resolver or a recorded reason
    it never will — never both, never neither. This is what makes a silently
    undispositioned 81st kind unrepresentable: adding it to ``ARTIFACT_KINDS`` without
    choosing a side turns this red."""
    tracked = set(mapping.RESOLVERS)
    dispositioned = set(mapping.UNTRACKED_DISPOSITIONS)
    both = tracked & dispositioned
    assert not both, f"tracked kinds must not also carry an untracked disposition: {sorted(both)}"
    outside = dispositioned - ARTIFACT_KINDS
    assert not outside, (
        "dispositions may only name vocabulary kinds — status_report is a resolver key, "
        f"not an artifact kind, and stays out: {sorted(outside)}"
    )
    assert "status_report" not in dispositioned
    neither = ARTIFACT_KINDS - tracked - dispositioned
    assert not neither, (
        f"kinds with no resolver and no recorded disposition: {sorted(neither)} — add a "
        "resolver, or record in mapping.UNTRACKED_DISPOSITIONS what the store consults instead"
    )
    for kind, reason in mapping.UNTRACKED_DISPOSITIONS.items():
        words = reason.split()
        assert len(words) >= 5 and reason == " ".join(words), (
            f"{kind}: disposition must be one line of actionable prose, got {reason!r}"
        )


def test_get_resolves_and_rejects() -> None:
    charter = catalog.get("4.1")
    assert charter.area is KnowledgeArea.INTEGRATION
    assert charter.group is ProcessGroup.INITIATING
    try:
        catalog.get("99.9")
    except KeyError:
        pass
    else:  # pragma: no cover - the assert above should not be reached
        raise AssertionError("get must raise KeyError on an unknown id")
