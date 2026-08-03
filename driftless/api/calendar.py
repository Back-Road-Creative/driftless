"""RFC 5545 iCalendar: the dates this store already holds, subscribable from any client.

AN EVENT is one of the two records carrying a date of its own, always ALL-DAY: a
milestone on its ``target_date``, a sprint across its window, ``DTEND`` the day *after*
the last one covered (RFC 5545's end is exclusive). A milestone is a commitment, not a
meeting, so a timed event would invent an hour nobody agreed to. NOT a task, even though
a task has a planned window: that window lives on a ``BaselineLine``, ONE plan version's
promise about it, so a re-baselined project holds several windows for the same task and
no non-arbitrary one to publish — the feed would emit the task twice or silently pick a
version, and a subscriber could not tell which. Not a baseline (a plan header is not a
date), not a cost entry (an amount is not a meeting).

SCOPE IS IN THE PATH, never a query parameter: ``/calendar.ics`` is the whole store and
``/projects/{id}/calendar.ics`` one project. A client subscribes to a URL once and
refetches it for years, so a ``?project_id=`` filter would let one subscription quietly
come to mean something else.

UID is ``{kind}-{primary key}@driftless`` — durable, unique per kind, globally unique
through the domain part. A client matches UID to decide *update* versus *add*, so a UID
taken from a row's position in the feed, a render-time counter or the name would make
every rename or insert a duplicate, which nobody can undo in a subscriber's calendar.

DTSTAMP READS NO CLOCK: neither record carries an ``updated_on``, and a wall clock would
change every byte of every fetch, defeating caching and this project's byte-identity
discipline. It is midnight UTC on the event's own start. No as-of is threaded either — a
calendar is the whole dated record, not a view of it at a moment.

ESCAPING AND FOLDING are written here, not pulled in: a dependency is declared only when
a phase needs one and CI pip-audits every one (``driftless/auth/passwords.py`` makes the
same call for hashing). §3.3.11 escapes backslash, semicolon, comma and newline in every
TEXT value — backslash first, or the escapes the others introduce get escaped twice;
§3.1 folds past 75 OCTETS onto continuations starting with one space, never mid-UTF-8.
A CR IS NOT ESCAPABLE — §3.3.11 has one break escape, ``\\n`` — and a name may hold one,
so CRLF and bare CR are first folded into that one break. Left alone, a CR inside a name
ends the SUMMARY line early and everything after it becomes a property of the attacker's
choosing in every subscriber's calendar.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from driftless.models import Milestone, Sprint

MEDIA_TYPE = "text/calendar; charset=utf-8"
PRODID = "-//Back Road Creative//driftless//EN"
OCTET_LIMIT = 75  # RFC 5545 §3.1, excluding the line break
_ESCAPES = (("\\", "\\\\"), (";", "\\;"), (",", "\\,"), ("\n", "\\n"))  # backslash FIRST
_BREAKS = (("\r\n", "\n"), ("\r", "\n"))  # CRLF and bare CR: one break, then escapable
_DAY = timedelta(days=1)


def escape(value: str) -> str:
    """``value`` as an RFC 5545 TEXT value, its line breaks normalised to the one §3.3.11
    can escape — a CR left in would frame a line rather than sit inside a value."""
    for char, replacement in _BREAKS:
        value = value.replace(char, replacement)
    for char, replacement in _ESCAPES:
        value = value.replace(char, replacement)
    return value


def fold(line: str) -> str:
    """``line`` folded at :data:`OCTET_LIMIT` octets, never inside a character."""
    raw = line.encode()
    if len(raw) <= OCTET_LIMIT:
        return line
    chunks: list[str] = []
    start = 0
    while start < len(raw):
        end = min(start + OCTET_LIMIT - bool(chunks), len(raw))  # a continuation's space costs 1
        while end < len(raw) and raw[end] & 0xC0 == 0x80:  # a continuation octet: step back
            end -= 1
        chunks.append(raw[start:end].decode())
        start = end
    return "\r\n ".join(chunks)


def feed(db: Session, name: str, project_id: int | None = None) -> Response:
    """One project's ``VCALENDAR`` (or the whole store's), escaped, folded, CRLF-joined.
    One statement per dated kind whatever the store holds — no row-by-row walk — ordered
    by id, so the bytes are a pure function of the rows."""
    milestones = select(Milestone).order_by(Milestone.id)
    sprints = select(Sprint).order_by(Sprint.id)
    if project_id is not None:
        milestones = milestones.where(Milestone.project_id == project_id)
        sprints = sprints.where(Sprint.project_id == project_id)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "METHOD:PUBLISH",  # CALSCALE is omitted: GREGORIAN is the default and the only one
        f"X-WR-CALNAME:{escape(name)}",  # what the subscription is called in the client
    ]
    dated = [
        (f"milestone-{row.id}@driftless", row.name, row.target_date, row.target_date + _DAY)
        for row in db.scalars(milestones)
    ] + [
        (f"sprint-{row.id}@driftless", row.name, row.start_date, row.end_date + _DAY)
        for row in db.scalars(sprints)
    ]
    for uid, summary, start, end in dated:  # ``end`` is the day AFTER the last one covered
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{start:%Y%m%d}T000000Z",
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{end:%Y%m%d}",
            f"SUMMARY:{escape(summary)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return Response("".join(f"{fold(line)}\r\n" for line in lines), media_type=MEDIA_TYPE)
