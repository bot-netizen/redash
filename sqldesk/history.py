"""
What a query said before, and putting it back.

Every edit has written a row to `changes` since long before this fork, and
nothing has ever shown them. The rows were there, the page was not -- so this
is mostly a reader, with one real repair underneath it: a query's edits were
not being recorded at all. Only its creation and its archiving were (see
`handlers/queries.py`), which is why the table looked well kept and held almost
nothing.

Three decisions worth stating, because each one could have gone another way:

- **A version is a whole snapshot, not a difference.** `record_changes` writes
  every tracked field on every version, so showing version 4 is reading one row
  rather than replaying four, and restoring it cannot drift.
- **Versions are numbered by position, not by `object_version`.** The column a
  query's `version` lives in is for optimistic locking and does not move when a
  query is edited, so every row would be "version 1". Position is derived from
  `changes.id`, which is the order they were written in.
- **A restore is a new version.** It never rewrites history and never deletes a
  row: restoring version 2 writes version 7 that happens to say what 2 said.
  Anything else would mean the page could not be trusted to show what happened.
"""

from sqldesk.models import Change

#: What a version shows, in the order it reads. Keys are **column** names,
#: which is what `changes` is keyed by -- `query_text` is stored in a column
#: called `query`, and the records say `query`.
FIELDS = (
    ("name", "Name"),
    ("description", "Description"),
    ("query", "SQL"),
    ("options", "Options"),
    ("schedule", "Schedule"),
    ("tags", "Tags"),
    ("data_source_id", "Data source"),
    ("is_draft", "Draft"),
    ("is_archived", "Archived"),
)

#: What a restore puts back: what the query *says*, not where it lives or who
#: owns it. Deliberately not `data_source_id` -- moving a query to another
#: source is a decision about where it runs, needs its own access check, and is
#: a surprising thing for a button called Restore to do. Not `is_draft` or
#: `is_archived` either: publishing and archiving have their own buttons, and
#: an undo that quietly unpublished a query would be a bug report.
RESTORABLE = ("name", "description", "query", "options", "schedule", "tags")

#: The one column whose name is not its attribute's name.
ATTRIBUTES = {"query": "query_text"}

#: How many versions a page asks for. Enough to cover a day of heavy editing;
#: beyond it the answer is the table itself, not a longer page.
LIMIT = 50


def _rows(obj, limit):
    """
    The newest `limit` records for this object, newest first, plus one.

    The extra row is what the oldest one on the page is compared against, so
    "what changed" is answered for every row shown rather than for all but the
    last.
    """
    return (
        Change.query.filter(Change.object_id == obj.id, Change.object_type == obj.__tablename__)
        .order_by(Change.id.desc())
        .limit(limit + 1)
        .all()
    )


def snapshot(row):
    """What the object said at this version: `{column: value}`."""
    change = row.change or {}
    taken = {}
    for name, _ in FIELDS:
        held = change.get(name)
        if isinstance(held, dict) and "current" in held:
            taken[name] = held["current"]
    return taken


def _what_changed(newer, older):
    """
    The labels of the fields that differ between two snapshots.

    Computed by comparing the two, not read from the `previous` half of the
    record: rows written before that half was fixed hold the new value in it,
    and a history that quietly lies about older rows is worse than one that
    says less.
    """
    if older is None:
        return ["Created"]
    return [label for name, label in FIELDS if newer.get(name) != older.get(name)]


def versions(obj, limit=LIMIT):
    """
    This object's versions, newest first.

    `number` counts from the first version ever recorded, so it does not change
    when more are added or when the page is shortened.
    """
    rows = _rows(obj, limit)
    total = Change.query.filter(Change.object_id == obj.id, Change.object_type == obj.__tablename__).count()
    shown = rows[:limit]
    snapshots = [snapshot(row) for row in rows]

    out = []
    for index, row in enumerate(shown):
        older = snapshots[index + 1] if index + 1 < len(snapshots) else None
        out.append(
            {
                "id": row.id,
                "number": total - index,
                "at": row.created_at,
                "by": _who(row),
                "changed": _what_changed(snapshots[index], older),
                "values": snapshots[index],
            }
        )
    return out


def _who(row):
    """The person who made the change, or None -- a user can be deleted."""
    if row.user is None:
        return None
    return {"id": row.user.id, "name": row.user.name, "email": row.user.email}


def version(obj, change_id):
    """One of this object's versions, or None. Never another object's."""
    return Change.query.filter(
        Change.id == change_id,
        Change.object_id == obj.id,
        Change.object_type == obj.__tablename__,
    ).first()


def restore(obj, row):
    """
    Put back what this version said, and report which fields moved.

    Does not record the new version itself: the caller knows who is doing it,
    and whether what it wants to put back is allowed.
    """
    taken = snapshot(row)
    moved = []
    for name, label in FIELDS:
        if name not in RESTORABLE or name not in taken:
            continue
        attribute = ATTRIBUTES.get(name, name)
        if getattr(obj, attribute) != taken[name]:
            setattr(obj, attribute, taken[name])
            moved.append(label)
    return moved
