"""
What SQLDesk does with files people have given it.

An uploaded file is the only copy of itself. That one fact decides everything
here: a warehouse answer in `query_results` can be thrown away because the
warehouse still has it, and a stream window can be truncated because it is a
window -- but nobody can re-create a CSV somebody dragged in six months ago
and then deleted from their laptop.

So uploads expire on a clock people can see and stop, and never silently. The
uploader is mailed the day before with a button that keeps the file, and only
somebody who may keep files can press it. The only deletion that happens
without a person involved is one that was announced and not acted on.

The reason this exists at all: until now nothing bounded what SQLDesk stored,
and on 2026-09-28 the development disk reached 100% and took Postgres with it.
"""

import datetime
import logging
import re

from itsdangerous import BadSignature, URLSafeSerializer

from sqldesk import models, settings
from sqldesk.utils import base_url, utcnow

logger = logging.getLogger(__name__)

#: Separate from every other signer's salt, so a token issued for one purpose
#: cannot be spent on another.
SALT = "sqldesk.keep-upload"

#: How long before expiry somebody is told. One day, because the mail has to
#: arrive while there is still something to do about it and a week's notice
#: about a file somebody uploaded last Tuesday is a mail nobody reads.
WARN_WITHIN = datetime.timedelta(days=1)


def _serializer():
    return URLSafeSerializer(settings.SECRET_KEY, salt=SALT)


def keep_token(upload):
    """
    A token that names one upload.

    No expiry on the token itself, deliberately: it is handed out in a mail
    about something that is *about* to expire, and a signature that stopped
    working at the same moment as the thing it was protecting would turn "keep
    this" into "too late" with no way to tell the two apart. Pressing it after
    the file has gone says the file has gone, which is the honest answer.
    """
    return _serializer().dumps({"upload": upload.id})


def keep_link(upload):
    return "{}/uploads/keep/{}".format(base_url(upload.org), keep_token(upload))


def upload_from_token(token):
    """The upload a token names, or None. Never raises on a bad token."""
    try:
        payload = _serializer().loads(token)
    except BadSignature:
        return None
    if not isinstance(payload, dict) or "upload" not in payload:
        return None
    return models.UploadedFile.query.filter(models.UploadedFile.id == payload["upload"]).first()


def bytes_held(org):
    """How much disk this organisation's uploads are using."""
    total = (
        models.db.session.query(models.db.func.coalesce(models.db.func.sum(models.UploadedFile.size), 0))
        .filter(models.UploadedFile.org_id == org.id)
        .scalar()
    )
    return int(total or 0)


def quota_bytes():
    return settings.UPLOAD_QUOTA_MB * 1024 * 1024 if settings.UPLOAD_QUOTA_MB > 0 else 0


def why_this_would_not_fit(org, size):
    """
    Why this upload cannot be accepted, in a sentence, or None.

    With the figures in it. "Quota exceeded" tells somebody they have a problem
    and nothing about how to solve it; the number of unqueried files is the
    sentence that actually helps, because deleting those is almost always the
    answer and nothing else in the product would tell them they exist.
    """
    ceiling = quota_bytes()
    if not ceiling:
        return None
    held = bytes_held(org)
    if held + size <= ceiling:
        return None

    parts = ["This would take the uploads past {}; {} is in use".format(_readable(ceiling), _readable(held))]
    idle = _idle_count(org)
    if idle == 1:
        parts.append("and one upload has not been queried in a month")
    elif idle > 1:
        parts.append("and {} uploads have not been queried in a month".format(idle))
    return ", ".join(parts) + "."


def _idle_count(org):
    month_ago = utcnow() - datetime.timedelta(days=30)
    return models.UploadedFile.query.filter(
        models.UploadedFile.org_id == org.id,
        models.db.or_(
            models.UploadedFile.last_queried_at.is_(None),
            models.UploadedFile.last_queried_at < month_ago,
        ),
        models.UploadedFile.created_at < month_ago,
    ).count()


def _readable(count):
    """Bytes as somebody would say them. Whole units; nobody needs 4.73 GB."""
    for unit, size in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if count >= size:
            value = count / size
            return "{:.1f} {}".format(value, unit) if value < 10 else "{:.0f} {}".format(value, unit)
    return "{} bytes".format(count)


def note_queried(data_source, query_text):
    """
    Record that a query named these uploads.

    Matched on the view name as a whole word, the same rule the runner uses to
    decide what to load. Written only when it changes the answer by more than
    an hour, so a dashboard refreshing every minute does not turn a read-only
    page into one UPDATE per widget per minute.
    """
    if not query_text:
        return
    uploads = models.UploadedFile.query.filter(models.UploadedFile.data_source_id == data_source.id).all()
    if not uploads:
        return

    now = utcnow()
    recently = now - datetime.timedelta(hours=1)
    touched = False
    for upload in uploads:
        if not re.search(r"\b{}\b".format(re.escape(upload.view_name)), query_text, re.IGNORECASE):
            continue
        if upload.last_queried_at is not None and upload.last_queried_at > recently:
            continue
        upload.last_queried_at = now
        # Querying it is as good a reason to bring it back as any, and leaving
        # the flag set would make the storage page say "unloaded" about a file
        # that is registered.
        upload.unloaded_at = None
        touched = True
    if touched:
        models.db.session.commit()
