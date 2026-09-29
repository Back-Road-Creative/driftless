"""``driftless.naming.humanize``: minor words stay lower-case mid-label, and the
two PMBOK terms of art it cannot get right by rule alone (``monitoring_controlling``,
``make_or_buy_analysis``) are named as explicit overrides."""

from driftless.naming import humanize
from driftless.pmbok.artifact_definitions import ARTIFACTS
from driftless.pmbok.artifacts import ARTIFACT_KINDS
from driftless.pmbok.definitions import TECHNIQUES
from driftless.pmbok.model import KnowledgeArea, ProcessGroup
from driftless.pmbok.tt import FAMILIES as TECHNIQUE_FAMILIES


def test_monitoring_controlling() -> None:
    assert humanize("monitoring_controlling") == "Monitoring and Controlling"


def test_interpersonal_and_team_skills() -> None:
    assert humanize("interpersonal_and_team_skills") == "Interpersonal and Team Skills"


def test_cost_of_quality() -> None:
    assert humanize("cost_of_quality") == "Cost of Quality"


def test_make_or_buy_analysis() -> None:
    assert humanize("make_or_buy_analysis") == "Make-or-Buy Analysis"


def test_minor_word_capitalized_as_first_word() -> None:
    assert humanize("of_mice_and_men") == "Of Mice and Men"


def _labels() -> list[str]:
    labels = [humanize(g.value) for g in ProcessGroup]
    labels += [humanize(a.value) for a in KnowledgeArea]
    labels += [humanize(f) for f in TECHNIQUE_FAMILIES]
    labels += [d.display_name for d in TECHNIQUES.values()]
    labels += [d.display_name for d in ARTIFACTS.values()]
    labels += [humanize(k) for k in ARTIFACT_KINDS]
    return labels


def test_no_label_has_a_mid_label_minor_word_capitalized() -> None:
    for label in _labels():
        for bad in (" And ", " Of ", " Or "):
            assert bad not in label, f"{label!r} contains {bad!r}"
