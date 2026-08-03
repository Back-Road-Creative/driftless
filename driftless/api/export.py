"""CSV rendering for the list endpoints — the export half of import/export.

The columns are the response model's own fields, in declaration order, so the
export and the API's public shape stay the same object: a field added to a
schema appears in the export with no edit here. Cells are dumped in JSON mode,
which makes the two formats the same data in two encodings rather than two
renderings — a date is the ISO string the JSON body carries, an unset field an
empty cell. Nothing reads a clock, so a fixed store exports byte-identically.

Export and import meet exactly: for each of ``bin/driftless-import.py``'s four
CSV kinds the exported columns minus ``id`` are that kind's declared
``required | optional`` columns — asserted in ``tests/test_api_export.py``
against both sides rather than restated here as a list that could drift. ``id``
is the one column the importer refuses, deliberately: it is POST-only, so a file
re-imported with its ids would copy every row rather than update it.

A CELL IS NEVER A FORMULA. Names and descriptions are typed by one user and the
export is opened by another, in a spreadsheet, which runs any cell beginning ``=
+ - @`` (or a tab/CR hiding one) the moment the file opens — so an exported cell
carries whatever command its author put in a project name. Every such cell is
marked literal here with the spreadsheet's own text prefix, ``'``, rather than at
the routes: ``?format=csv`` is registered on every list route and on search, and
a rule written once in the renderer cannot be forgotten by the next one. A value
that PARSES AS A NUMBER is left exactly as it is, so ``-42.5`` stays a negative
number a reader can total, not a quoted string — nothing a spreadsheet reads as a
number is a formula, so the two rules cannot collide.
"""

import csv
import io
from typing import Any, Literal

from fastapi import Response
from pydantic import BaseModel

Format = Literal["json", "csv"]
FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")
TEXT_MARK = "'"  # a spreadsheet's own "read this cell as text"


def _is_number(text: str) -> bool:
    """Whether a spreadsheet would read ``text`` as a number rather than a formula."""
    try:
        float(text)
    except ValueError:
        return False
    return True


def _cell(value: Any) -> str:
    """One cell: ``None`` is empty — a reader must not have to decode ``None``.

    A formula lead on anything but a number is marked literal, never dropped: the
    text stays readable, it just stops being executable."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(FORMULA_LEADS) and not _is_number(text):
        return TEXT_MARK + text
    return text


def csv_response(out: type[BaseModel], rows: list[Any], name: str) -> Response:
    """Render ``rows`` as CSV under ``out``'s fields, header row first."""
    columns = list(out.model_fields)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        dumped = out.model_validate(row).model_dump(mode="json")
        writer.writerow([_cell(dumped[column]) for column in columns])
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="{name}.csv"'},
    )
