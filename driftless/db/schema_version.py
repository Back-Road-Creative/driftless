"""The migration revision this code requires, carried as a constant.

A constant rather than a lookup because ``pyproject.toml`` deliberately does not
package ``alembic/`` — a deployed process has no migration scripts to derive the
head from, so a value compiled into the package is the only thing available to
it. That is safe only because it cannot silently drift: the suite
(``tests/test_schema_readiness.py``) walks the real chain with Alembic's own
resolver and asserts it equals this tuple, so the next migration is red until it
is appended here.

The whole chain is listed, not just the head, because readiness has to tell
*behind* from *ahead*. A database stamped with a revision named here is behind
this code and a forward ``alembic upgrade head`` fixes it; a revision absent
from the list means the database has already moved past this image and the code
is the stale half, which no forward migration repairs (see OPERATIONS.md).
"""

from __future__ import annotations

# Base -> head, in chain order. Every entry is an Alembic revision id.
KNOWN_REVISIONS: tuple[str, ...] = (
    "8980cbcb2fbb",  # core schema: hierarchy and delivery  # pragma: allowlist secret
    "7df21247c4ac",  # records: RAID, cost, change log  # pragma: allowlist secret
    "f4a9c2e17b30",  # foundation: org, sign-off, narrative, quality  # pragma: allowlist secret
    "c3d81f60ab27",  # app_user: stored identity  # pragma: allowlist secret
    "b46ef0a1c9d3",  # app_user: session epoch  # pragma: allowlist secret
    "a3f7c95d21e8",  # api_token: per-user credentials  # pragma: allowlist secret
    "d1c84b7e0a92",  # change_log: progress-replay index  # pragma: allowlist secret
    "e5c2a94d7b18",  # change_request: origin process provenance  # pragma: allowlist secret
    "b7d4e21f9c03",  # narrative_artifact: fifteen prose kinds  # pragma: allowlist secret
    "c8f3a1d47e29",  # foreign keys: covering indexes  # pragma: allowlist secret
    "f2c1a7e8b9d0",  # quality: directional metric definitions  # pragma: allowlist secret
    "af4e7b12c9d1",  # scorecard: business-scoped strategic objectives  # pragma: allowlist secret
    "b38d6e9a410f",  # scorecard: objective-owned metric definitions  # pragma: allowlist secret
    "d7f29c5a1e84",  # scorecard: append-only metric observations  # pragma: allowlist secret
    "e8a41d6c2f95",  # scorecard: governed source registry  # pragma: allowlist secret
    "f9b52e7d3a06",  # scorecard: project contribution links  # pragma: allowlist secret
    "7cbe3c7ed36e",  # row_revision: optimistic-concurrency token  # pragma: allowlist secret
    "c19e3eff4b27",  # scorecard: versioned metric definitions  # pragma: allowlist secret
    "ff230d5c1eb0",  # api_token: expiry  # pragma: allowlist secret
    "cd96d900768b",  # cost_entry: reversing corrections, not an edit  # pragma: allowlist secret
    "4c96ce2fdaaf",  # status_snapshot: same-date corrections, latest recorded wins  # pragma: allowlist secret
    "b5e9f37c2a81",  # idempotency_record: one row per spent Idempotency-Key  # pragma: allowlist secret
    "e2a91c4d70b8",  # api_token: last use, so a dead credential is visible  # pragma: allowlist secret
    "dcb8fc906970",  # technique_run: append-only provenance ledger  # pragma: allowlist secret
    "b07e89a3a315",  # agile records: roles, backlog, release, DoD, impediment  # pragma: allowlist secret
    "60b3833f0f32",  # department operations: services, work queue, recurring work, SLAs, controls, incidents, improvements  # pragma: allowlist secret
    "a1c5e8d3f647",  # schedule records: task dependencies, calendars, estimate scenarios  # pragma: allowlist secret
    "0ce50b8b6731",  # risk: threat/opportunity kind, and the risk_response table  # pragma: allowlist secret
    "b2f6a19d4c73",  # scope: requirements, traces, deliverables (the WBS tree), acceptance  # pragma: allowlist secret
    "6c2ec0e6d92d",  # resource: types, RBS, RACI, acquisition, training, assessment, conflict  # pragma: allowlist secret
    "a4e19c7f2b83",  # lesson_learned: one row per lesson raised  # pragma: allowlist secret
    "d4f8b3e19a72",  # project: delivery_mode learns operations  # pragma: allowlist secret
    "e7a3c95f2d41",  # backlog_item: stored flow dates, backfilled  # pragma: allowlist secret
    "e3dad3341548",  # webhook_subscription: cursored delivery of change_log rows  # pragma: allowlist secret
    "a1c4e6f8b2d3",  # email_subscription: digest cadence and last-sent cursor  # pragma: allowlist secret
    "b1f5a2c8e94d",  # artifact_link: a URI reference filed against any record  # pragma: allowlist secret
    "e420bfc8e785",  # note: an append-only note filed against any record  # pragma: allowlist secret
    "0d419319edee",  # task: actual and forecast finish dates  # pragma: allowlist secret
    "ca6fe294b54a",  # app_user: email  # pragma: allowlist secret
    "3c7c1aded10d",  # change_log: via channel  # pragma: allowlist secret
    "d9c3b6a8e1f2",  # change_log: tamper-evident hash chain  # pragma: allowlist secret
    "7b8f97e1c973",  # person: kind and agent binding, sign_off: signed_by_kind  # pragma: allowlist secret
    "452898b6df2a",  # sign_off: baseline subject  # pragma: allowlist secret
    "7642894637a8",  # gate: a stage boundary, sign_off: gate subject  # pragma: allowlist secret
    "a9c3e7f21d05",  # app_user: oidc_subject  # pragma: allowlist secret
)
EXPECTED_REVISION = KNOWN_REVISIONS[-1]  # derived, so head and chain cannot disagree


class SchemaAheadError(RuntimeError):
    """The store is stamped with a revision this image has never heard of.

    Raised at startup (``driftless.api.app.refuse_if_schema_ahead``) rather than
    returned, because there is no forward migration that repairs it and no
    request this image can safely answer while it holds.
    """


def schema_is_ahead(applied: str | None) -> bool:
    """Whether ``applied`` names a revision this image has never heard of.

    The one definition of *ahead*, so the readiness probe and the startup refusal
    cannot come to different conclusions about the same store. Never migrated
    (``None``) is behind, not ahead: ``create_all`` builds an unstamped store and
    that is what dev and the test suite run on.
    """
    return applied is not None and applied not in KNOWN_REVISIONS
