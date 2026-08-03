"""The onboarding wizard: process-ordered, agent-drivable project setup.

``engine`` is the pure read side — the next process to work and the whole
process-state map, computed from the store and the clock-free state engine. The
CLI (``driftless wizard``) adds the write side, producing outputs through the same
validated API boundary the HTTP endpoints use, so a loop can stand a project up
end to end without a human.
"""

from driftless.wizard.engine import InputStatus, WizardStep, next_step, status

__all__ = ["InputStatus", "WizardStep", "next_step", "status"]
