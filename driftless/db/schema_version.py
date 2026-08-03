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
