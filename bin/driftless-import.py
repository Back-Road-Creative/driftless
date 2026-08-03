#!/usr/bin/env python3
"""Import business records into a running driftless API from JSON or CSV.

The default JSON mode reads a nested structure of businesses -> portfolios ->
projects -> workstreams -> tasks and creates each level through the API,
carrying the bearer token, so every row is validated and audited on the
ChangeLog exactly like any other write. Real data goes in through the same door
as everything else — never a direct database write.

    bin/driftless-import.py data.json --base-url http://127.0.0.1:8000 --token "$DRIFTLESS_API_TOKEN"

``--csv KIND`` reads one flat record per row instead, for the four bulk kinds
people already keep in spreadsheets (see ``bin/sample-tasks.csv``):

    bin/driftless-import.py rows.csv --csv tasks   # or risks / costs / milestones

Each kind's columns are declared once in ``CSV_KINDS`` below — path, required
columns, optional columns and the coercion for every non-string cell — so a
half-wired kind is not expressible. The whole file is coerced before the first
POST goes out, and business rules stay at the API: this stays a client of the
validated write path, never a second one.

Both importers are pure functions over an injected ``post`` callable, so either
can be driven against a live API or a fake in a test.

Nothing here can roll a batch back — one POST is one row — so a POST that fails
partway raises :class:`PartialImport` naming what landed, and ``--skip N`` re-runs
a CSV from row ``N`` without duplicating it. Every refusal is rc 2 and one line on
stderr, the contract the ``driftless`` subcommands follow, never a traceback.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

Post = Callable[[str, dict[str, Any]], int]
Coerce = Callable[[str], Any]


def _iso_date(cell: str) -> str:
    """Refuse a non-ISO date here, and hand the API the same string back."""
    return date.fromisoformat(cell).isoformat()


class PartialImport(Exception):
    """A POST failed with earlier rows already created: name exactly what landed.

    A mid-file failure cannot be undone from here, so ``counts`` is the
    compensating record — what is now in the store, and what a re-run skips so
    it never duplicates a row.
    """

    def __init__(self, counts: dict[str, int], cause: BaseException) -> None:
        super().__init__(str(cause))
        self.counts = counts
        self.cause = cause


class CsvKind(NamedTuple):
    """One CSV kind: where its rows POST, and how every cell is read."""

    path: str
    required: dict[str, Coerce]
    optional: dict[str, Coerce]


# The parent is always named by its integer FK column, never by name: resolving a
# name would need read calls back against the API and is deliberately out of
# scope, so a CSV carries the ids its author already has. Column names and
# endpoints mirror the request schemas (driftless/api/schemas.py) exactly — a
# value this file lets through is still validated there.
CSV_KINDS: dict[str, CsvKind] = {
    "tasks": CsvKind(
        "/tasks",
        {"name": str, "workstream_id": int},
        {
            "status": str,
            "estimate": float,
            "estimate_unit": str,
            "actual_effort": float,
            "percent_complete": int,
            "assignee_id": int,
        },
    ),
    "risks": CsvKind(
        "/risks",
        {"project_id": int, "description": str, "probability": float, "impact": float},
        {"response": str, "owner": str, "status": str},
    ),
    "costs": CsvKind(
        "/cost-entries",
        {"project_id": int, "category": str, "incurred_on": _iso_date, "amount": float},
        {},
    ),
    "milestones": CsvKind(
        "/milestones",
        {"project_id": int, "name": str, "target_date": _iso_date},
        {"baseline_date": _iso_date, "status": str},
    ),
}


def _payload(kind: CsvKind, number: int, row: Mapping[str, Any]) -> dict[str, Any]:
    """Coerce one row into a POST body, naming the column in every refusal."""
    columns = kind.required | kind.optional
    for column in row:
        if column == "id":
            # The one column an export carries that no kind declares. Silently
            # ignoring it would sell a round-trip that does not exist: this
            # importer only ever POSTs, so the ids would name rows it then
            # duplicates. Name the fix instead of hiding the asymmetry.
            raise ValueError(
                f"row {number}: column 'id' comes from an export — drop it before importing, "
                f"because this importer only ever creates rows, so ids would duplicate what "
                f"they name, not update it"
            )
        if column not in columns:
            raise ValueError(f"row {number}: unknown column {column!r}")
    payload: dict[str, Any] = {}
    for column, coerce in columns.items():
        cell = (row.get(column) or "").strip()
        if not cell:
            # A blank optional cell is omitted, never posted as "" — the API's
            # own default is the one default.
            if column in kind.required:
                raise ValueError(f"row {number}: required column {column!r} is missing or empty")
            continue
        try:
            payload[column] = coerce(cell)
        except ValueError as exc:
            raise ValueError(f"row {number}: column {column!r} value {cell!r} is invalid: {exc}")
    return payload


def import_csv(
    post: Post, kind: str, rows: Iterable[Mapping[str, Any]], skip: int = 0
) -> dict[str, int]:
    """Create one flat record per CSV row via ``post``; return the row count.

    Every row is coerced against the kind's column spec before the first POST is
    issued, so an unknown column, a missing required column or an uncoercible
    cell cannot leave half a file imported. Row numbers count the header as row
    1, matching what a spreadsheet shows.

    ``skip`` drops that many leading rows: :class:`PartialImport` says how many
    landed, and re-running with that number posts only the rest.
    """
    if kind not in CSV_KINDS:
        raise ValueError(f"unknown --csv kind {kind!r}; expected one of {', '.join(CSV_KINDS)}")
    spec = CSV_KINDS[kind]
    payloads = [_payload(spec, number, row) for number, row in enumerate(rows, start=2)]
    if skip > len(payloads):
        raise ValueError(f"--skip {skip} is past the end of a {len(payloads)}-row file")
    for done, payload in enumerate(payloads[skip:], start=skip):
        try:
            post(spec.path, payload)
        except Exception as exc:
            raise PartialImport({kind: done}, exc) from exc
    return {kind: len(payloads)}


def _task_payload(task: Mapping[str, Any], workstream_id: int) -> dict[str, Any]:
    """A JSON task as a POST body, refusing any field it would otherwise drop.

    Both paths read one column set (``CSV_KINDS['tasks']``): a hand-written subset
    here is how ``percent_complete``, ``status`` and ``assignee_id`` went in and
    never arrived, while the CSV path refused that asymmetry out loud.
    """
    columns = CSV_KINDS["tasks"].required | CSV_KINDS["tasks"].optional
    name = task.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("a task is missing its 'name'")
    for field in task:
        if field == "workstream_id":
            raise ValueError(
                f"task {name!r}: field 'workstream_id' comes from the parent workstream — "
                f"drop it, because the task's position in the file already names its parent"
            )
        if field not in columns:
            raise ValueError(
                f"task {name!r}: unknown field {field!r}; a JSON task carries the same fields "
                f"as a --csv tasks row ({', '.join(sorted(columns))})"
            )
    return {"estimate_unit": "hours", **task, "workstream_id": workstream_id}


def import_data(post: Post, data: dict[str, Any]) -> dict[str, int]:
    """Create the hierarchy in ``data`` via ``post``; return per-level counts."""
    counts = {"businesses": 0, "portfolios": 0, "projects": 0, "workstreams": 0, "tasks": 0}

    def create(level: str, payload: dict[str, Any]) -> int:
        """POST one row, tally it, and name what landed if the POST fails."""
        try:
            row_id = post("/" + level, payload)
        except Exception as exc:
            raise PartialImport(dict(counts), exc) from exc
        counts[level] += 1
        return row_id

    for business in data.get("businesses", []):
        business_id = create("businesses", {"name": business["name"]})
        for portfolio in business.get("portfolios", []):
            portfolio_id = create(
                "portfolios", {"name": portfolio["name"], "business_id": business_id}
            )
            for project in portfolio.get("projects", []):
                project_id = create(
                    "projects",
                    {
                        "name": project["name"],
                        "portfolio_id": portfolio_id,
                        "delivery_mode": project.get("delivery_mode", "predictive"),
                    },
                )
                for workstream in project.get("workstreams", []):
                    workstream_id = create(
                        "workstreams", {"name": workstream["name"], "project_id": project_id}
                    )
                    for task in workstream.get("tasks", []):
                        create("tasks", _task_payload(task, workstream_id))
    return counts


def _http_poster(base_url: str, token: str) -> Post:
    """A ``post`` that calls the real API with a bearer token."""

    def post(path: str, payload: dict[str, Any]) -> int:
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json", "authorization": f"Bearer {token}"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:  # noqa: S310 - operator-supplied URL
            result: dict[str, Any] = json.load(response)
        return int(result["id"])

    return post


def main(argv: list[str] | None = None, post: Post | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import business records into driftless.")
    parser.add_argument("data", help="path to the JSON file, or the CSV file with --csv")
    parser.add_argument(
        "--csv",
        choices=sorted(CSV_KINDS),
        help="read the file as a flat CSV of this record kind instead of nested JSON",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default=os.environ.get("DRIFTLESS_API_TOKEN", ""))
    parser.add_argument(
        "--skip", type=int, default=0, metavar="N", help="with --csv, skip the first N rows"
    )
    args = parser.parse_args(argv)

    post = post or _http_poster(args.base_url, args.token)
    path = Path(args.data)
    try:
        if args.csv:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = csv.DictReader(handle, restkey="(extra cells)")
                counts = import_csv(post, args.csv, rows, skip=args.skip)
        else:
            counts = import_data(post, _read_json(path))
    except PartialImport as partial:
        # The record a re-run needs: those rows are in the store already.
        print(f"error: {partial}", file=sys.stderr)
        print("landed: " + json.dumps(partial.counts, sort_keys=True), file=sys.stderr)
        print("resume: " + _resume_hint(partial, args.csv), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print("Imported: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    """Read the JSON file, naming the file itself rather than only a byte offset."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not valid JSON for this importer: expected an object")
    return data


def _resume_hint(partial: PartialImport, kind: str | None) -> str:
    """How to re-run without duplicating the rows ``partial`` says already landed."""
    if kind is not None:
        return f"re-run the same file with --skip {partial.counts[kind]} to import only the rest"
    return "those rows are already in the store; trim the JSON to what is left before re-running"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
