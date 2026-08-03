"""The ITTO data model: the five process groups, ten knowledge areas, and a Process.

This is reference data, not stored state — a versioned-in-code catalog of the
PMBOK-6 predictive processes, so it lives as frozen dataclasses rather than DB
rows. A ``Process`` sits in exactly one (group, area) cell and names its Inputs,
Tools & Techniques and Outputs by reference: inputs and outputs are
``ARTIFACT_KINDS`` (``driftless.pmbok.artifacts``), tools and techniques are members
of the ``TT_CATALOG`` (``driftless.pmbok.tt``). The catalog's property tests pin that
referential integrity, so a process can never name an artifact kind or technique
the system does not otherwise understand.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProcessGroup(str, Enum):
    """The five PMBOK process groups, in lifecycle order."""

    INITIATING = "initiating"
    PLANNING = "planning"
    EXECUTING = "executing"
    MONITORING = "monitoring_controlling"
    CLOSING = "closing"


class KnowledgeArea(str, Enum):
    """The ten PMBOK knowledge areas."""

    INTEGRATION = "integration"
    SCOPE = "scope"
    SCHEDULE = "schedule"
    COST = "cost"
    QUALITY = "quality"
    RESOURCE = "resource"
    COMMUNICATIONS = "communications"
    RISK = "risk"
    PROCUREMENT = "procurement"
    STAKEHOLDER = "stakeholder"


@dataclass(frozen=True)
class Process:
    """One PMBOK process: a cell of the group×area grid, with its ITTOs by reference.

    ``id`` is the PMBOK-6 clause number (e.g. ``"11.2"``); ``inputs`` and
    ``outputs`` name ``ARTIFACT_KINDS``; ``tools_techniques`` name ``TT_CATALOG``
    members. ``optional_outputs`` is the declared subset of ``outputs`` the
    process only *may* raise (PMBOK's conditional outputs): an optional output
    can never be required for PRODUCED and never carries assessability.
    """

    id: str
    name: str
    group: ProcessGroup
    area: KnowledgeArea
    inputs: tuple[str, ...]
    tools_techniques: tuple[str, ...]
    outputs: tuple[str, ...]
    optional_outputs: tuple[str, ...] = ()
