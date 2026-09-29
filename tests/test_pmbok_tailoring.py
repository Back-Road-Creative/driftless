"""Hybrid tailoring: totality (every Monitoring & Controlling process is mapped in
every profile, exactly once) and the one fixed change boundary."""

from __future__ import annotations

from driftless.models.hierarchy import DELIVERY_MODES
from driftless.pmbok import catalog, tailoring
from driftless.pmbok.model import ProcessGroup

_MC_IDS = frozenset(p.id for p in catalog.by_group(ProcessGroup.MONITORING))


def test_every_delivery_mode_has_a_profile() -> None:
    assert set(tailoring.PROFILES) == set(DELIVERY_MODES)


def test_operations_profile_reads_every_control_on_operations_cadence_except_the_boundary() -> None:
    profile = tailoring.PROFILES["operations"]
    for control in profile.controls:
        if control.process_id in ("4.5", "4.6"):
            assert control.mode is tailoring.ControlMode.PREDICTIVE_BASELINE
        else:
            assert control.mode is tailoring.ControlMode.OPERATIONS_CADENCE


def test_totality_every_profile_covers_every_monitoring_process_exactly_once() -> None:
    for profile in tailoring.PROFILES.values():
        ids = [c.process_id for c in profile.controls]
        assert set(ids) == _MC_IDS, profile.key
        assert len(ids) == len(set(ids)), f"{profile.key} has a duplicate control"


def test_every_control_names_a_process_the_catalog_has() -> None:
    for profile in tailoring.PROFILES.values():
        for control in profile.controls:
            catalog.get(control.process_id)  # raises KeyError if unknown


def test_every_control_carries_a_reason() -> None:
    for profile in tailoring.PROFILES.values():
        for control in profile.controls:
            assert control.reason.strip()


def test_change_boundary_processes_are_always_predictive_in_every_profile() -> None:
    for profile in tailoring.PROFILES.values():
        for process_id in ("4.5", "4.6"):
            control = profile.for_process(process_id)
            assert control is not None
            assert control.mode is tailoring.ControlMode.PREDICTIVE_BASELINE


def test_agile_and_hybrid_are_genuinely_different_readings() -> None:
    agile_modes = {c.process_id: c.mode for c in tailoring.PROFILES["agile"].controls}
    hybrid_modes = {c.process_id: c.mode for c in tailoring.PROFILES["hybrid"].controls}
    assert agile_modes != hybrid_modes
    predictive_modes = {c.process_id: c.mode for c in tailoring.PROFILES["predictive"].controls}
    assert all(m is tailoring.ControlMode.PREDICTIVE_BASELINE for m in predictive_modes.values())


def test_control_tailoring_lookup_and_mode_word() -> None:
    control = tailoring.control_tailoring("6.6", "agile")
    assert control is not None
    assert control.mode is tailoring.ControlMode.ADAPTIVE_COMMITMENT
    assert tailoring.mode_word(control.mode) == "adaptive commitment"


def test_control_tailoring_none_for_a_non_monitoring_process() -> None:
    assert tailoring.control_tailoring("4.1", "predictive") is None


def test_profile_for_unknown_delivery_mode_raises() -> None:
    import pytest

    with pytest.raises(KeyError):
        tailoring.profile_for("nonexistent")
