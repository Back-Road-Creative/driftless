"""Canonical resolution of the service database URL — one env name, one default,
so the web/API/alembic path and the report/assess/wizard CLIs can never read
different stores. ``DRIFTLESS_DATABASE_URL`` is canonical; ``PMHUB_DATABASE_URL``
(the pre-rename canonical) and ``PMHUB_DB_URL`` (the CLIs' historical name) are
honoured as deprecated aliases for one deprecation cycle."""

import os
from typing import overload

CANONICAL_ENV = "DRIFTLESS_DATABASE_URL"
LEGACY_ENV = "PMHUB_DATABASE_URL"
DEPRECATED_ENV = "PMHUB_DB_URL"


@overload
def database_url(default: str) -> str: ...


@overload
def database_url(default: None = ...) -> str | None: ...


def database_url(default: str | None = None) -> str | None:
    """The configured database URL: the canonical env var, else the pre-rename
    canonical, else the deprecated CLI alias, else ``default``. Every surface
    resolves through here so a single exported variable points them all at the
    same store. A non-``None`` ``default`` (as the API passes) narrows the
    result to ``str``."""
    return (
        os.environ.get(CANONICAL_ENV)
        or os.environ.get(LEGACY_ENV)
        or os.environ.get(DEPRECATED_ENV)
        or default
    )
