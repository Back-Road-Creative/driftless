"""The assessment engine: per-output algorithms over the store → threats and actions.

Every knowledge area has a pure evaluator turning calc/records signals into an
``Assessment`` (risk score, RAG status, threats, recommended PMBOK actions). The
engine aggregates them, rolls up Integration, and produces a sign-off-aware
threat feed. Nothing is stored — assessments are computed from the store and an
explicit as-of date, so they cannot drift and regenerate byte-identically.
"""

from driftless.assess.engine import (
    assess_project,
    is_suppressed,
    live_threats,
    top_threats,
)
from driftless.assess.model import Action, Assessment, Threat

__all__ = [
    "Action",
    "Assessment",
    "Threat",
    "assess_project",
    "is_suppressed",
    "live_threats",
    "top_threats",
]
